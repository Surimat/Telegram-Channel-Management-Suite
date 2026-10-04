"""Tests for bot↔channel bindings and channel reaction capabilities.

Exercises the real service + API against the deterministic fake bot provider, so
no Telegram account or network is needed.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

BINDINGS = "/api/v1/bindings"
CAPABILITIES = "/api/v1/capabilities"


@pytest_asyncio.fixture
async def product_client() -> AsyncClient:
    """Client with both bot and session providers wired to deterministic fakes."""
    from backend.app.api.deps import get_provider_factory, get_session_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.providers.fake_bot import FakeTelegramBotProvider
    from backend.app.providers.fake_session import FakePermissionScenario
    from tests.conftest import make_fake_session_factory

    await init_models()
    app = create_app()

    def _bot_factory(token, *, provider_name="auto", settings=None):
        return FakeTelegramBotProvider(token)

    app.dependency_overrides[get_provider_factory] = lambda: _bot_factory
    app.dependency_overrides[get_session_provider_factory] = lambda: make_fake_session_factory(
        permission=FakePermissionScenario(can_invite=True)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_channel(client: AsyncClient, reference: str = "@demo") -> str:
    resp = await client.post("/api/v1/channels", json={"reference": reference})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_bot(client: AsyncClient, token: str = "111:AAA") -> str:
    resp = await client.post("/api/v1/bots", json={"token": token, "kind": "managed"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_connect_check_and_delete_binding(product_client: AsyncClient) -> None:
    channel_id = await _make_channel(product_client)
    bot_id = await _make_bot(product_client)

    created = await product_client.post(
        BINDINGS, json={"bot_id": bot_id, "channel_id": channel_id, "function": "reactions"}
    )
    assert created.status_code == 201, created.text
    binding = created.json()
    assert binding["status"] == "not_connected"
    assert binding["invite_link"].startswith("https://t.me/")
    # The token never leaks.
    assert "AAA" not in created.text

    checked = await product_client.post(f"{BINDINGS}/{binding['id']}/check")
    assert checked.status_code == 200
    body = checked.json()
    assert body["status"] == "ready"
    assert body["can_set_reactions"] is True
    assert body["present"] is True

    listed = await product_client.get(BINDINGS)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["status"] == "ready"

    deleted = await product_client.delete(f"{BINDINGS}/{binding['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


async def test_check_channel_bindings(product_client: AsyncClient) -> None:
    channel_id = await _make_channel(product_client, "@multi")
    bot_id = await _make_bot(product_client)
    await product_client.post(
        BINDINGS, json={"bot_id": bot_id, "channel_id": channel_id}
    )
    checks = await product_client.post(f"{BINDINGS}/channel/{channel_id}/check")
    assert checks.status_code == 200
    assert len(checks.json()) == 1


async def test_binding_unknown_bot_returns_404(product_client: AsyncClient) -> None:
    channel_id = await _make_channel(product_client, "@x")
    resp = await product_client.post(
        BINDINGS, json={"bot_id": "missing", "channel_id": channel_id}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"]


async def test_capability_probe_returns_emoji_set(product_client: AsyncClient) -> None:
    channel_id = await _make_channel(product_client, "@caps")
    bot_id = await _make_bot(product_client)
    await product_client.post(BINDINGS, json={"bot_id": bot_id, "channel_id": channel_id})

    view = await product_client.get(f"{CAPABILITIES}/{channel_id}")
    assert view.status_code == 200
    assert view.json()["status"] == "unknown"

    probed = await product_client.post(f"{CAPABILITIES}/{channel_id}/probe")
    assert probed.status_code == 200
    body = probed.json()
    assert "👍" in body["available"]
    assert body["status"] == "ok"
    assert body["reactions_limit"] >= 1


async def test_capability_probe_without_bot_is_honest(product_client: AsyncClient) -> None:
    channel_id = await _make_channel(product_client, "@no-bot")
    probed = await product_client.post(f"{CAPABILITIES}/{channel_id}/probe")
    assert probed.status_code == 200
    body = probed.json()
    assert body["status"] == "unavailable"
    assert body["available"] == []
    assert body["message"]
