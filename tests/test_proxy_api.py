"""API tests for proxy profiles (v1.1 connection routes).

Exercises the real router/service over a temporary SQLite DB. Asserts the
password is never returned and the non-bypass notice is present.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

PROXIES = "/api/v1/proxies"


@pytest_asyncio.fixture
async def proxy_client() -> AsyncClient:
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_create_list_and_no_secret_returned(proxy_client: AsyncClient) -> None:
    resp = await proxy_client.post(
        PROXIES,
        json={
            "name": "Домашний",
            "kind": "socks5",
            "host": "127.0.0.1",
            "port": 1080,
            "username": "user",
            "password": "s3cret",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_password"] is True
    assert "password" not in body
    assert "s3cret" not in resp.text

    listed = await proxy_client.get(PROXIES)
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload["items"]) == 1
    assert "не отменяет" in payload["notice"]


async def test_invalid_kind_rejected(proxy_client: AsyncClient) -> None:
    resp = await proxy_client.post(
        PROXIES, json={"kind": "ftp", "host": "127.0.0.1", "port": 21}
    )
    assert resp.status_code == 400


async def test_update_clears_password(proxy_client: AsyncClient) -> None:
    created = await proxy_client.post(
        PROXIES, json={"kind": "http", "host": "10.0.0.1", "port": 8080, "password": "x"}
    )
    pid = created.json()["id"]
    updated = await proxy_client.put(
        f"{PROXIES}/{pid}", json={"host": "10.0.0.2", "password": ""}
    )
    assert updated.status_code == 200
    assert updated.json()["host"] == "10.0.0.2"
    assert updated.json()["has_password"] is False


async def test_delete(proxy_client: AsyncClient) -> None:
    created = await proxy_client.post(
        PROXIES, json={"kind": "socks5", "host": "127.0.0.1", "port": 1080}
    )
    pid = created.json()["id"]
    assert (await proxy_client.delete(f"{PROXIES}/{pid}")).status_code == 204
    assert (await proxy_client.delete(f"{PROXIES}/{pid}")).status_code == 404


async def test_bind_and_unbind_account(proxy_client: AsyncClient) -> None:
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.repositories.sessions import SessionRepository
    from backend.app.db.session import session_scope

    async with session_scope() as db:
        db.add(
            UserSession(
                telegram_user_id=555, username="bound", status=SessionStatus.ONLINE, api_id="1"
            )
        )
    async with session_scope() as db:
        accounts, _ = await SessionRepository(db).list()
        account_id = accounts[0].id

    created = await proxy_client.post(
        PROXIES, json={"kind": "socks5", "host": "127.0.0.1", "port": 1080}
    )
    pid = created.json()["id"]

    bound = await proxy_client.post(
        f"{PROXIES}/bind", json={"account_id": account_id, "profile_id": pid}
    )
    assert bound.status_code == 200
    assert bound.json()["proxy_id"] == pid

    unbound = await proxy_client.post(
        f"{PROXIES}/bind", json={"account_id": account_id, "profile_id": ""}
    )
    assert unbound.json()["proxy_id"] == ""


async def test_check_reports_honestly(proxy_client: AsyncClient) -> None:
    created = await proxy_client.post(
        PROXIES, json={"kind": "socks5", "host": "127.0.0.1", "port": 1}
    )
    pid = created.json()["id"]
    resp = await proxy_client.post(f"{PROXIES}/{pid}/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] in {"error", "timeout"}
    assert body["how_to_fix"]
