"""API tests for Owner Auth + Config Sync (v1.6).

Exercises the real routers over a temporary SQLite DB. Verifies the local-first
guard (open until an owner profile enables protection), the token requirement,
and that no endpoint ever echoes a secret.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

OWNER = "/api/v1/owner"


@pytest_asyncio.fixture
async def owner_client() -> AsyncClient:
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_open_until_owner_creates_profile(owner_client: AsyncClient) -> None:
    # No owner: the guard is a pass-through.
    status = await owner_client.get(f"{OWNER}/status")
    assert status.status_code == 200
    body = status.json()
    assert body["exists"] is False
    assert body["auth_required"] is False
    # A normal API route is reachable without a token.
    assert (await owner_client.get("/api/v1/settings")).status_code == 200


async def test_setup_returns_token_and_protects_api(owner_client: AsyncClient) -> None:
    resp = await owner_client.post(
        f"{OWNER}/setup",
        json={"secret": "owner pass", "method": "password", "display_name": "Хозяин"},
    )
    assert resp.status_code == 201
    token = resp.json()["token"]
    assert token.startswith("owner.")
    # The secret never appears in the response.
    assert "owner pass" not in resp.text

    # Now the API is protected: no token → 401.
    assert (await owner_client.get("/api/v1/settings")).status_code == 401

    # With the token the call succeeds.
    ok = await owner_client.get("/api/v1/settings", headers={"X-Owner-Token": token})
    assert ok.status_code == 200

    # Status stays reachable without a token (allowlist).
    assert (await owner_client.get(f"{OWNER}/status")).status_code == 200


async def test_wrong_login_does_not_issue_token(owner_client: AsyncClient) -> None:
    await owner_client.post(f"{OWNER}/setup", json={"secret": "right pass"})
    bad = await owner_client.post(f"{OWNER}/login", json={"secret": "wrong"})
    assert bad.status_code == 401
    assert "token" not in bad.text


async def test_login_and_logout(owner_client: AsyncClient) -> None:
    await owner_client.post(f"{OWNER}/setup", json={"secret": "right pass"})
    login = await owner_client.post(f"{OWNER}/login", json={"secret": "right pass"})
    assert login.status_code == 200
    token = login.json()["token"]
    logout = await owner_client.post(f"{OWNER}/logout", headers={"X-Owner-Token": token})
    assert logout.status_code == 200


async def test_sync_status_and_configure(owner_client: AsyncClient) -> None:
    setup = await owner_client.post(f"{OWNER}/setup", json={"secret": "right pass"})
    headers = {"X-Owner-Token": setup.json()["token"]}

    status = await owner_client.get(f"{OWNER}/sync/status", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["owner_ready"] is True
    assert "не копируются" in body["no_live_db_note"]

    configured = await owner_client.post(
        f"{OWNER}/sync/configure", json={"provider": "local"}, headers=headers
    )
    assert configured.status_code == 200
    assert configured.json()["provider"] == "local"


async def test_sync_requires_owner_profile(owner_client: AsyncClient) -> None:
    # No owner: sync upload cannot derive a key.
    resp = await owner_client.post(f"{OWNER}/sync/upload", json={"secret": "x"})
    assert resp.status_code in (401, 409)


async def test_protection_can_be_turned_off(owner_client: AsyncClient) -> None:
    setup = await owner_client.post(f"{OWNER}/setup", json={"secret": "right pass"})
    headers = {"X-Owner-Token": setup.json()["token"]}
    off = await owner_client.post(
        f"{OWNER}/protection", json={"enabled": False}, headers=headers
    )
    assert off.status_code == 200
    assert off.json()["enabled"] is False
    # API is open again.
    assert (await owner_client.get("/api/v1/settings")).status_code == 200
