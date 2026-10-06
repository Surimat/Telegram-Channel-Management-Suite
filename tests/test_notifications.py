"""Tests for the Notification Center (v1.4).

The center is exercised end-to-end against the real service, repositories and a
deterministic fake bot provider — no Telegram account, no network. A fake toast
destination records deliveries without touching the OS.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.db.models.notification import (
    NotificationDestination,
    NotificationStatus,
)
from backend.app.db.session import init_models, session_scope
from backend.app.manager.bus import Notification, reset_notification_bus
from backend.app.services.notification_destinations import DeliveryResult
from backend.app.services.notification_service import NotificationCenterService


class _RecordingToast:
    """A fake Windows-toast destination that records deliveries."""

    def __init__(self, *, ok: bool = True, unavailable: bool = False) -> None:
        self.ok = ok
        self.unavailable = unavailable
        self.delivered: list[tuple[str, str]] = []

    async def deliver(self, text: str, *, title: str = "") -> DeliveryResult:
        self.delivered.append((title, text))
        if self.unavailable:
            return DeliveryResult(ok=False, unavailable=True, message="нет")
        return DeliveryResult(ok=self.ok, message="" if self.ok else "ошибка")


async def _service(**kwargs) -> NotificationCenterService:
    session = kwargs.pop("session")
    return NotificationCenterService(session, **kwargs)


@pytest_asyncio.fixture(autouse=True)
async def _ensure_schema() -> None:
    """Create all tables for the temporary DB before each test."""
    await init_models()


async def test_submit_records_and_delivers_via_toast() -> None:
    toast = _RecordingToast()
    async with session_scope() as session:
        svc = NotificationCenterService(session, toast=toast)
        # Route the system category to the toast for this test.
        await svc.update_settings(routing={"system": [NotificationDestination.WINDOWS_TOAST]})
        record = await svc.submit(
            Notification(category="system", event_key="app.started", message="Привет")
        )
        assert record.status is NotificationStatus.SENT
        assert toast.delivered and "Привет" in toast.delivered[0][1]
        rows, total = await svc.history()
        assert total == 1
        assert rows[0].category == "system"


async def test_disabled_category_is_skipped() -> None:
    toast = _RecordingToast()
    async with session_scope() as session:
        svc = NotificationCenterService(session, toast=toast)
        await svc.update_settings(
            categories={"system": False},
            routing={"system": [NotificationDestination.WINDOWS_TOAST]},
        )
        record = await svc.submit(
            Notification(category="system", event_key="x", message="не надо")
        )
        assert record.status is NotificationStatus.SKIPPED
        assert toast.delivered == []


async def test_quiet_hours_postpone_non_urgent() -> None:
    toast = _RecordingToast()
    # Force quiet hours to cover the current hour by using a fixed clock.
    now = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    async with session_scope() as session:
        svc = NotificationCenterService(session, toast=toast)
        await svc.update_settings(
            routing={"system": [NotificationDestination.WINDOWS_TOAST]},
            quiet_hours_enabled=True,
            quiet_hours_start=0,
            quiet_hours_end=8,
            quiet_hours_tz="UTC",
        )
        record = await svc.submit(
            Notification(category="system", event_key="a", message="инфо"), now=now
        )
        assert record.status is NotificationStatus.POSTPONED
        assert record.postponed_until is not None
        assert toast.delivered == []
        # An urgent notification is delivered immediately even in quiet hours.
        urgent = await svc.submit(
            Notification(category="system", event_key="b", message="беда", priority="error"),
            now=now,
        )
        assert urgent.status is NotificationStatus.SENT
        assert toast.delivered


async def test_quiet_hours_release_after_window() -> None:
    toast = _RecordingToast()
    now = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    async with session_scope() as session:
        svc = NotificationCenterService(session, toast=toast)
        await svc.update_settings(
            routing={"system": [NotificationDestination.WINDOWS_TOAST]},
            quiet_hours_enabled=True,
            quiet_hours_start=0,
            quiet_hours_end=8,
            quiet_hours_tz="UTC",
        )
        await svc.submit(
            Notification(category="system", event_key="a", message="инфо"), now=now
        )
        # Before the window ends nothing is delivered.
        assert await svc.deliver_due_postponed(now=now) == 0
        # After the window ends the postponed item is delivered.
        later = now + timedelta(hours=6)
        assert await svc.deliver_due_postponed(now=later) == 1
        assert toast.delivered


async def test_aggregation_merges_identical_notifications() -> None:
    toast = _RecordingToast()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    async with session_scope() as session:
        svc = NotificationCenterService(session, toast=toast)
        await svc.update_settings(routing={"system": [NotificationDestination.WINDOWS_TOAST]})
        first = await svc.submit(
            Notification(category="system", event_key="poll", message="сбой"), now=now
        )
        await svc.submit(
            Notification(category="system", event_key="poll", message="сбой"),
            now=now + timedelta(seconds=5),
        )
        # The first record now reports two similar events; the second was merged.
        refreshed = await svc.records.get(first.id)
        assert refreshed is not None and refreshed.aggregate_count == 2
        rows, total = await svc.history()
        assert total == 2
        assert any(r.status is NotificationStatus.AGGREGATED for r in rows)
        # Urgent notifications are never aggregated.
        urgent = await svc.submit(
            Notification(category="system", event_key="poll2", message="беда", priority="error"),
            now=now,
        )
        urgent2 = await svc.submit(
            Notification(category="system", event_key="poll2", message="беда", priority="error"),
            now=now + timedelta(seconds=5),
        )
        assert urgent.status is NotificationStatus.SENT
        assert urgent2.status is NotificationStatus.SENT


async def test_no_destination_marks_skipped() -> None:
    async with session_scope() as session:
        svc = NotificationCenterService(session)
        await svc.update_settings(routing={"system": [NotificationDestination.NONE]})
        record = await svc.submit(
            Notification(category="system", event_key="x", message="никуда")
        )
        assert record.status is NotificationStatus.SKIPPED


async def test_missing_telegram_provider_records_failed_delivery() -> None:
    async with session_scope() as session:
        svc = NotificationCenterService(session)  # no resolvers, no toast
        await svc.update_settings(
            routing={"system": [NotificationDestination.TELEGRAM_OWNER]}
        )
        record = await svc.submit(
            Notification(category="system", event_key="x", message="нет бота")
        )
        assert record.status is NotificationStatus.FAILED
        deliveries = await svc.deliveries.list_for_notification(record.id)
        assert deliveries and deliveries[0].status is NotificationStatus.SKIPPED


async def test_flush_pending_drains_the_bus() -> None:
    toast = _RecordingToast()
    reset_notification_bus()
    async with session_scope() as session:
        svc = NotificationCenterService(session, toast=toast)
        await svc.update_settings(routing={"system": [NotificationDestination.WINDOWS_TOAST]})
        from backend.app.manager.bus import publish

        publish(category="system", event_key="app.started", message="запущено")
        publish(category="system", event_key="app.stopped", message="остановлено")
        assert await svc.flush_pending() == 2
        assert len(toast.delivered) == 2
    reset_notification_bus()


def test_quiet_hours_window_logic() -> None:
    async def _check() -> None:
        async with session_scope() as session:
            svc = NotificationCenterService(session)
            cfg = await svc.load_settings()
            # Directly construct a settings object to test the pure window logic.
            from backend.app.services.notification_service import NotificationSettings

            wrapped = NotificationSettings(
                enabled=True,
                categories={},
                routing={},
                quiet_hours_enabled=True,
                quiet_hours_start=23,
                quiet_hours_end=8,
                quiet_hours_tz="UTC",
                aggregation_enabled=True,
            )
            assert svc.in_quiet_hours(
                wrapped, now=datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
            )
            assert svc.in_quiet_hours(wrapped, now=datetime(2026, 1, 1, 3, 0, tzinfo=UTC))
            assert not svc.in_quiet_hours(
                wrapped, now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
            )
            assert cfg.enabled is True

    import asyncio

    asyncio.run(_check())


# --- API ---------------------------------------------------------------------


@pytest_asyncio.fixture
async def notification_client() -> AsyncClient:
    from backend.app.api.deps import get_provider_factory
    from backend.app.main import create_app
    from backend.app.providers.fake_bot import FakeTelegramBotProvider

    await init_models()
    app = create_app()
    app.dependency_overrides[get_provider_factory] = lambda: (
        lambda token, *, provider_name="auto", settings=None: FakeTelegramBotProvider(token)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_api_settings_and_test_notification(
    notification_client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()

    resp = await notification_client.get("/api/v1/notifications/settings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True
    assert any(c["key"] == "system" for c in body["categories"])

    updated = await notification_client.put(
        "/api/v1/notifications/settings",
        json={"categories": {"system": False}},
    )
    assert updated.status_code == 200
    system = next(c for c in updated.json()["categories"] if c["key"] == "system")
    assert system["enabled"] is False

    # A test notification for a disabled category is skipped, never an error.
    sent = await notification_client.post(
        "/api/v1/notifications/test", json={"category": "system", "priority": "info"}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "skipped"


async def test_api_history_and_dashboard(notification_client: AsyncClient) -> None:
    listing = await notification_client.get("/api/v1/notifications")
    assert listing.status_code == 200
    assert "items" in listing.json()

    dashboard = await notification_client.get("/api/v1/notifications/dashboard")
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert "status_counts" in body
    assert "category_counts" in body
    # The token never leaks through the API.
    assert "token" not in dashboard.text.lower()


async def test_bus_category_routing_is_stable() -> None:
    from backend.app.manager.bus import CATEGORIES, category_for_module

    assert "accounts" in CATEGORIES
    assert category_for_module("sessions.session_service") == "accounts"
    assert category_for_module("editorial") == "content"
    assert category_for_module("mesh") == "workers"


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_notification_bus()
    yield
    reset_notification_bus()
