"""Tests for the Mini App setup helper (post-1.0 hardening).

The owner points the manager bot's chat menu button at a public HTTPS URL so the
suite opens straight from Telegram. We exercise the validation branches and the
success path through the real service + a recording fake provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.db.models.bot import BotKind
from backend.app.db.session import get_session, init_models
from backend.app.main import create_app
from backend.app.miniapp.service import MiniAppService
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.services.bot_service import BotService

MANAGER_TOKEN = "222222:MINIAPP-SETUP-TOKEN"


class _RecordingFactory:
    """Provider factory that records every provider it builds (for assertions)."""

    def __init__(self) -> None:
        self.providers: list[FakeTelegramBotProvider] = []

    def __call__(self, token, *, provider_name="auto", settings=None):
        provider = FakeTelegramBotProvider(token)
        self.providers.append(provider)
        return provider


async def _add_manager(token: str = MANAGER_TOKEN) -> None:
    async for session in get_session():
        await BotService(
            session, provider_factory=lambda t, **k: FakeTelegramBotProvider(t)
        ).add_bot(token, kind=BotKind.MANAGER)
        await session.commit()
        break


@pytest_asyncio.fixture
async def setup_client(monkeypatch) -> AsyncIterator[tuple[AsyncClient, _RecordingFactory]]:
    monkeypatch.setenv("MINIAPP_ENABLED", "true")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await init_models()
    await _add_manager()
    app = create_app()
    from backend.app.api.deps import get_provider_factory

    factory = _RecordingFactory()
    app.dependency_overrides[get_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory
    reset_settings_cache()


async def test_setup_rejects_empty_url(setup_client) -> None:
    client, _ = setup_client
    resp = await client.post("/api/v1/miniapp/setup", json={"public_url": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "адрес" in body["message"].lower()


async def test_setup_rejects_non_https(setup_client) -> None:
    client, _ = setup_client
    resp = await client.post("/api/v1/miniapp/setup", json={"public_url": "http://example.com"})
    body = resp.json()
    assert body["ok"] is False
    assert "https" in body["message"].lower()


async def test_setup_registers_menu_button_and_settings(setup_client) -> None:
    client, factory = setup_client
    resp = await client.post(
        "/api/v1/miniapp/setup", json={"public_url": "https://tcms.example.com/"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True

    # The trailing slash is normalised and pushed to the bot's menu button.
    assert factory.providers, "a provider should have been built"
    assert factory.providers[-1].menu_button == ("Открыть панель", "https://tcms.example.com")

    # The public URL + enabled flag are persisted for the config endpoint.
    from backend.app.services.settings_service import SettingsService

    async for session in get_session():
        assert await SettingsService(session).get_typed("miniapp_enabled") is True
        assert (
            await SettingsService(session).get_typed("miniapp_public_url")
            == "https://tcms.example.com"
        )
        break


async def test_setup_requires_manager_bot(monkeypatch) -> None:
    monkeypatch.setenv("MINIAPP_ENABLED", "true")
    from backend.app.api.deps import get_provider_factory
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await init_models()
    app = create_app()
    app.dependency_overrides[get_provider_factory] = lambda: _RecordingFactory()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/miniapp/setup", json={"public_url": "https://tcms.example.com"}
        )
    reset_settings_cache()
    body = resp.json()
    assert body["ok"] is False
    assert "бот" in body["message"].lower()


async def test_setup_service_reports_provider_error() -> None:
    from backend.app.providers.errors import TelegramProviderError

    class _FailingFactory(_RecordingFactory):
        def __call__(self, token, *, provider_name="auto", settings=None):
            provider = FakeTelegramBotProvider(
                token, fail_with=TelegramProviderError("Telegram недоступен.")
            )
            self.providers.append(provider)
            return provider

    await init_models()
    await _add_manager()
    async for session in get_session():
        result = await MiniAppService(
            session, provider_factory=_FailingFactory()
        ).setup("https://tcms.example.com")
        break
    assert result.ok is False
    assert result.message
