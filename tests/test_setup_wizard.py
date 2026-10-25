"""End-to-end Setup Wizard tests (D-128).

These seed *real* rows in the temporary SQLite DB and exercise the real service
and API. Nothing is mocked: the step status is the stored result of the server's
own check, so a step that was never run stays ``unchecked`` and a failed step is
never reported as ready.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.core.config import get_settings, reset_settings_cache
from backend.app.core.security import seal_secret
from backend.app.db.base import new_id, utcnow
from backend.app.db.models.binding import BindingStatus, BotChannelBinding
from backend.app.db.models.bot import Bot, BotKind
from backend.app.db.models.channel import Channel, ChannelKind, ChannelStatus
from backend.app.db.models.content import (
    ContentItem,
    ContentItemStatus,
    ContentSource,
    ContentSourceKind,
    Publication,
    PublicationStatus,
)
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.session import init_models, session_scope
from backend.app.services.content_service import content_hash, source_hash
from backend.app.services.setup_wizard import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_UNCHECKED,
    STATUS_VERIFIED,
    STEP_KEYS,
    SetupWizardService,
)

API = "/api/v1/setup-wizard"


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


async def _seed_channel(
    *,
    status: ChannelStatus = ChannelStatus.VERIFIED,
    modules: str | None = None,
    verified: bool = True,
) -> str:
    channel_id = new_id()
    async with session_scope() as session:
        session.add(
            Channel(
                id=channel_id,
                reference="@wiz",
                username="wiz",
                title="Канал мастера",
                kind=ChannelKind.CHANNEL,
                status=status,
                is_default=True,
                last_verified_at=utcnow() if verified else None,
                **({"modules": modules} if modules is not None else {}),
            )
        )
    return channel_id


async def _seed_binding(channel_id: str, status: BindingStatus) -> None:
    async with session_scope() as session:
        bot_id = new_id()
        session.add(Bot(id=bot_id, kind=BotKind.MANAGED, username="wiz_bot", title="Bot"))
        session.add(
            BotChannelBinding(
                id=new_id(),
                bot_id=bot_id,
                channel_id=channel_id,
                status=status,
            )
        )


async def _seed_source_and_item() -> str:
    source_id = new_id()
    item_id = new_id()
    async with session_scope() as session:
        session.add(
            ContentSource(
                id=source_id,
                kind=ContentSourceKind.MANUAL,
                title="Источник",
                reference="manual:wiz",
                enabled=True,
            )
        )
        session.add(
            ContentItem(
                id=item_id,
                source_id=source_id,
                title="Материал",
                text="Текст",
                status=ContentItemStatus.READY,
            )
        )
    return item_id


async def _run(key: str) -> object:
    async with session_scope() as session:
        return await SetupWizardService(session).run_step(key)


def _step(view, key):  # type: ignore[no-untyped-def]
    return next(s for s in view.steps if s.key == key)


async def test_state_starts_unchecked() -> None:
    async with session_scope() as session:
        view = await SetupWizardService(session).state()
    assert [s.key for s in view.steps] == list(STEP_KEYS)
    assert all(s.status == STATUS_UNCHECKED and not s.verified for s in view.steps)
    assert view.ready is False
    assert view.current_step == "app"
    assert view.progress_percent == 0
    assert view.test_publication_available is False


async def test_opening_the_page_does_not_mark_steps_done() -> None:
    # Real data exists, but the steps were never run: nothing may read as done.
    channel_id = await _seed_channel()
    await _seed_binding(channel_id, BindingStatus.READY)
    await _seed_source_and_item()
    async with session_scope() as session:
        view = await SetupWizardService(session).state()
    assert all(not s.verified for s in view.steps)


async def test_app_step_verifies_on_real_checks() -> None:
    view = await _run("app")
    step = _step(view, "app")
    assert step.verified is True
    assert step.status == STATUS_VERIFIED
    assert step.verified_at is not None


async def test_channel_step_pending_without_a_channel() -> None:
    view = await _run("channel")
    step = _step(view, "channel")
    assert step.status == STATUS_PENDING
    assert step.verified is False
    assert step.how_to_fix


async def test_channel_step_verifies_after_a_real_verification() -> None:
    await _seed_channel(status=ChannelStatus.VERIFIED, verified=True)
    view = await _run("channel")
    assert _step(view, "channel").verified is True


async def test_channel_step_pending_when_never_verified() -> None:
    await _seed_channel(status=ChannelStatus.NEW, verified=False)
    view = await _run("channel")
    step = _step(view, "channel")
    assert step.status == STATUS_PENDING
    assert step.verified is False


async def test_bot_step_fails_when_permission_missing() -> None:
    channel_id = await _seed_channel()
    await _seed_binding(channel_id, BindingStatus.NEEDS_PERMISSION)
    view = await _run("bot")
    step = _step(view, "bot")
    assert step.status == STATUS_FAILED
    assert step.verified is False


async def test_bot_step_verifies_with_a_ready_binding() -> None:
    channel_id = await _seed_channel()
    await _seed_binding(channel_id, BindingStatus.READY)
    view = await _run("bot")
    assert _step(view, "bot").verified is True


async def test_bot_step_requires_a_rerun_after_a_fix() -> None:
    channel_id = await _seed_channel()
    await _seed_binding(channel_id, BindingStatus.NEEDS_PERMISSION)
    first = await _run("bot")
    assert _step(first, "bot").verified is False

    # Fix the state and run the step again — only then does it become verified.
    async with session_scope() as session:
        from sqlalchemy import select

        binding = (
            await session.execute(
                select(BotChannelBinding).where(
                    BotChannelBinding.channel_id == channel_id
                )
            )
        ).scalars().first()
        assert binding is not None
        binding.status = BindingStatus.READY
    second = await _run("bot")
    assert _step(second, "bot").verified is True


async def test_modules_step_pending_until_configured() -> None:
    channel_id = await _seed_channel()
    pending = await _run("modules")
    assert _step(pending, "modules").status == STATUS_PENDING

    async with session_scope() as session:
        channel = await session.get(Channel, channel_id)
        assert channel is not None
        channel.modules = '{"reactions": true, "audience": false}'
    verified = await _run("modules")
    assert _step(verified, "modules").verified is True


async def test_content_step_requires_a_ready_material() -> None:
    async with session_scope() as session:
        session.add(
            ContentSource(
                id=new_id(),
                kind=ContentSourceKind.MANUAL,
                title="Источник",
                reference="manual:only",
                enabled=True,
            )
        )
    pending = await _run("content")
    assert _step(pending, "content").status == STATUS_PENDING

    await _seed_source_and_item()
    verified = await _run("content")
    assert _step(verified, "content").verified is True


async def test_queue_step_fails_on_a_failed_job() -> None:
    async with session_scope() as session:
        session.add(
            Job(id=new_id(), kind="content.posting", status=JobStatus.FAILED)
        )
    view = await _run("queue")
    step = _step(view, "queue")
    assert step.status == STATUS_FAILED
    assert step.verified is False


async def test_queue_step_verifies_when_empty() -> None:
    view = await _run("queue")
    assert _step(view, "queue").verified is True


async def test_readiness_requires_a_real_publication() -> None:
    channel_id = await _seed_channel(modules='{"reactions": true}')
    await _seed_binding(channel_id, BindingStatus.READY)

    pending = await _run("readiness")
    assert _step(pending, "readiness").status == STATUS_PENDING
    assert _step(pending, "readiness").verified is False

    item_id = await _seed_source_and_item()
    async with session_scope() as session:
        session.add(
            Publication(
                id=new_id(),
                item_id=item_id,
                channel_id=channel_id,
                channel_username="wiz",
                status=PublicationStatus.PUBLISHED,
            )
        )
    verified = await _run("readiness")
    assert _step(verified, "readiness").verified is True
    # Every step was verified by a real check, so the wizard reports ready.
    for key in STEP_KEYS:
        await _run(key)
    async with session_scope() as session:
        final = await SetupWizardService(session).state()
    assert final.ready is True
    assert final.progress_percent == 100


async def test_unknown_step_is_rejected(client: AsyncClient) -> None:
    resp = await client.post(f"{API}/steps/ghost/run", json={})
    assert resp.status_code == 404


async def test_api_state_and_run(client: AsyncClient) -> None:
    state = await client.get(API)
    assert state.status_code == 200
    body = state.json()
    assert body["total_steps"] == len(STEP_KEYS)
    assert body["ready"] is False

    run = await client.post(f"{API}/steps/app/run", json={})
    assert run.status_code == 200
    step = next(s for s in run.json()["steps"] if s["key"] == "app")
    assert step["verified"] is True
    assert step["status"] == STATUS_VERIFIED


async def test_test_publication_requires_explicit_confirmation(client: AsyncClient) -> None:
    resp = await client.post(f"{API}/test-publication", json={"confirmed": False})
    assert resp.status_code == 400


async def test_test_publication_refused_until_steps_verified(client: AsyncClient) -> None:
    resp = await client.post(f"{API}/test-publication", json={"confirmed": True})
    assert resp.status_code == 409


async def test_test_publication_publishes_an_already_prepared_item(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wizard's own test publication must publish the prepared material.

    Regression: the test publication used to re-grab the source and take
    ``item_ids[0]``; once the source was up to date a re-grab returned only a
    duplicate, so the wizard asked the owner to prepare content and then refused
    its own test publication with a 409. It must fall back to the prepared item.
    """
    monkeypatch.setenv("OFFLINE_MODE", "true")
    reset_settings_cache()
    settings = get_settings()

    channel_id = await _seed_channel(modules='{"reactions": true}')
    bot_id = new_id()
    async with session_scope() as session:
        session.add(
            Bot(
                id=bot_id,
                kind=BotKind.MANAGED,
                username="wiz_pub_bot",
                title="Bot",
                token_encrypted=seal_secret("111:AAA", settings),
            )
        )
        session.add(
            BotChannelBinding(
                id=new_id(),
                bot_id=bot_id,
                channel_id=channel_id,
                function="posting",
                status=BindingStatus.READY,
            )
        )
        source = ContentSource(
            id=new_id(),
            kind=ContentSourceKind.MANUAL,
            title="Источник",
            reference="Готовый текст для теста",
            enabled=True,
        )
        session.add(source)
        await session.flush()
        text = "Готовый текст для теста"
        session.add(
            ContentItem(
                id=new_id(),
                source_id=source.id,
                title="Материал",
                text=text,
                cleaned_text=text,
                status=ContentItemStatus.READY,
                source_hash=source_hash("manual", source.reference),
                content_hash=content_hash(text),
            )
        )

    for key in STEP_KEYS:
        await _run(key)

    resp = await client.post(f"{API}/test-publication", json={"confirmed": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    # The UI re-runs the readiness gate after the confirmed test publication.
    await _run("readiness")
    async with session_scope() as session:
        final = await SetupWizardService(session).state()
    assert _step(final, "readiness").verified is True
    assert final.ready is True


async def test_state_never_leaks_secrets(client: AsyncClient) -> None:
    # APP_SECRET_KEY is set by the test environment; it must never appear.
    resp = await client.get(API)
    assert "test-secret-key-value" not in resp.text
