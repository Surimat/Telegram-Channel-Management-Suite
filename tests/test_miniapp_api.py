"""API tests for the Mini App authentication endpoints (PHASE 9).

We register a manager bot with a known token (sealed via the real security
layer), then sign ``initData`` exactly as Telegram does and exercise
``/api/v1/miniapp/*`` through the ASGI app.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.db.models.bot import BotKind
from backend.app.db.session import get_session, init_models
from backend.app.main import create_app
from backend.app.services.bot_service import BotService

MANAGER_TOKEN = "111111:MINIAPP-TEST-TOKEN"


def sign(fields: dict[str, object], bot_token: str = MANAGER_TOKEN) -> str:
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    payload = dict(fields)
    payload["hash"] = digest
    return urlencode(payload)


def init_data(telegram_id: int = 777, now: float | None = None) -> str:
    return sign(
        {
            "auth_date": int(now if now is not None else time.time()),
            "query_id": "AA",
            "user": json.dumps(
                {"id": telegram_id, "first_name": "Owner", "username": "owner"}
            ),
        }
    )


async def _add_manager(token: str = MANAGER_TOKEN) -> None:
    from tests.conftest import make_fake_provider_factory

    async for session in get_session():
        await BotService(
            session, provider_factory=make_fake_provider_factory()
        ).add_bot(token, kind=BotKind.MANAGER)
        await session.commit()
        break


@pytest_asyncio.fixture
async def miniapp_client(monkeypatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("MINIAPP_ENABLED", "true")
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "777")
    from backend.app.api.deps import get_provider_factory
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await init_models()
    await _add_manager()
    app = create_app()
    from tests.conftest import make_fake_provider_factory

    app.dependency_overrides[get_provider_factory] = lambda: make_fake_provider_factory()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    reset_settings_cache()


async def test_config_reports_available(miniapp_client: AsyncClient) -> None:
    resp = await miniapp_client.get("/api/v1/miniapp/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["available"] is True


async def test_auth_sets_session_cookie(miniapp_client: AsyncClient) -> None:
    resp = await miniapp_client.post("/api/v1/miniapp/auth", json={"init_data": init_data()})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["authenticated"] is True
    assert body["is_admin"] is True
    assert body["user"]["id"] == 777
    assert "tcms_miniapp" in resp.cookies


async def test_auth_rejects_tampered(miniapp_client: AsyncClient) -> None:
    resp = await miniapp_client.post(
        "/api/v1/miniapp/auth", json={"init_data": init_data().replace("owner", "hacker")}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_auth_rejects_non_owner(miniapp_client: AsyncClient) -> None:
    resp = await miniapp_client.post(
        "/api/v1/miniapp/auth", json={"init_data": init_data(telegram_id=999)}
    )
    assert resp.status_code == 401
    # The friendly message must not leak internals.
    message = resp.json()["error"]["message"]
    assert "владельц" in message.lower()


async def test_me_roundtrip(miniapp_client: AsyncClient) -> None:
    unauth = await miniapp_client.get("/api/v1/miniapp/me")
    assert unauth.json()["authenticated"] is False

    await miniapp_client.post("/api/v1/miniapp/auth", json={"init_data": init_data()})
    me = await miniapp_client.get("/api/v1/miniapp/me")
    assert me.json()["authenticated"] is True
    assert me.json()["telegram_id"] == 777


async def test_logout_clears_session(miniapp_client: AsyncClient) -> None:
    await miniapp_client.post("/api/v1/miniapp/auth", json={"init_data": init_data()})
    await miniapp_client.post("/api/v1/miniapp/logout")
    me = await miniapp_client.get("/api/v1/miniapp/me")
    assert me.json()["authenticated"] is False


async def test_response_never_leaks_token_or_initdata(miniapp_client: AsyncClient) -> None:
    data = init_data()
    resp = await miniapp_client.post("/api/v1/miniapp/auth", json={"init_data": data})
    text = resp.text
    assert MANAGER_TOKEN not in text
    assert data not in text
    assert "hash" not in text
