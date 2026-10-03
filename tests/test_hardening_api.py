"""API tests for the permission probe and manager endpoints (post-1.0).

The full HTTP flow runs against the fake providers, so no Telegram is needed.
"""

from __future__ import annotations

PERM = "/api/v1/permissions"
MANAGER = "/api/v1/manager"


async def _create_account(client) -> str:
    start = await client.post(
        "/api/v1/sessions/auth/start",
        json={"api_id": "123456", "api_hash": "SECRET-HASH", "phone": "+79991234567"},
    )
    account_id = start.json()["account_id"]
    await client.post(f"/api/v1/sessions/{account_id}/code", json={"code": "12345"})
    return account_id


async def test_permission_check_ok(permission_client) -> None:
    account_id = await _create_account(permission_client)
    resp = await permission_client.post(
        f"{PERM}/check", json={"account_id": account_id, "target": "@chan"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["can_invite"] is True
    assert body["status_label"]
    assert "SECRET-HASH" not in resp.text


async def test_permission_check_empty_target(permission_client) -> None:
    account_id = await _create_account(permission_client)
    resp = await permission_client.post(
        f"{PERM}/check", json={"account_id": account_id, "target": "  "}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["message"]
    assert err["hint"]


async def test_permission_check_unknown_account(permission_client) -> None:
    resp = await permission_client.post(
        f"{PERM}/check", json={"account_id": "nope", "target": "@chan"}
    )
    assert resp.status_code == 404


async def test_permission_latest_and_history(permission_client) -> None:
    account_id = await _create_account(permission_client)
    await permission_client.post(
        f"{PERM}/check", json={"account_id": account_id, "target": "@chan"}
    )
    latest = await permission_client.get(f"{PERM}/latest")
    assert latest.status_code == 200
    assert latest.json()["status"] == "ok"
    history = await permission_client.get(f"{PERM}/history")
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1


async def test_permission_latest_empty(permission_client) -> None:
    resp = await permission_client.get(f"{PERM}/latest")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_manager_status_without_bot(manager_client) -> None:
    resp = await manager_client.get(f"{MANAGER}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["status_label"] == "не подключён"
    assert body["how_to_fix"]


async def test_manager_status_with_bot(manager_client) -> None:
    from backend.app.core.config import get_settings
    from backend.app.core.security import seal_secret
    from backend.app.db.models.bot import Bot, BotKind
    from backend.app.db.session import session_scope

    settings = get_settings()
    async with session_scope() as db:
        db.add(
            Bot(
                kind=BotKind.MANAGER,
                username="my_manager_bot",
                telegram_id=1,
                token_encrypted=seal_secret("123:abc", settings),
                provider_name="fake",
                enabled=True,
            )
        )
        await db.flush()
    resp = await manager_client.get(f"{MANAGER}/status")
    body = resp.json()
    assert body["connected"] is True
    assert body["username"] == "my_manager_bot"
    assert "123:abc" not in resp.text


async def test_manager_notifications_defaults(manager_client) -> None:
    resp = await manager_client.get(f"{MANAGER}/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    keys = {c["key"] for c in body["categories"]}
    assert {"system", "telegram", "reactions", "audience", "invites", "ai"} <= keys
    assert all(c["enabled"] for c in body["categories"])


async def test_manager_notifications_update(manager_client) -> None:
    resp = await manager_client.put(
        f"{MANAGER}/notifications",
        json={"enabled": True, "categories": {"ai": False}},
    )
    assert resp.status_code == 200
    body = resp.json()
    by_key = {c["key"]: c["enabled"] for c in body["categories"]}
    assert by_key["ai"] is False
    assert by_key["system"] is True
