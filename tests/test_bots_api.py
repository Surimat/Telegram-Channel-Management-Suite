"""Bots API tests, using the fake provider (no real credentials)."""

from __future__ import annotations


async def test_bots_empty_list(bot_client) -> None:
    resp = await bot_client.get("/api/v1/bots")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_add_list_and_summary(bot_client) -> None:
    resp = await bot_client.post(
        "/api/v1/bots", json={"token": "123456:ABC-DEF", "kind": "manager"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "manager"
    assert body["has_token"] is True
    # The token never appears anywhere in the response payload.
    assert "ABC-DEF" not in resp.text

    listed = await bot_client.get("/api/v1/bots")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    summary = await bot_client.get("/api/v1/bots/summary")
    assert summary.status_code == 200
    assert summary.json()["manager_connected"] is True


async def test_add_bot_invalid_token_returns_friendly_error(bot_client) -> None:
    resp = await bot_client.post("/api/v1/bots", json={"token": "bad-token"})
    assert resp.status_code == 400
    body = resp.json()["error"]
    # Friendly message plus an actionable hint, never a stack trace.
    assert body["message"]
    assert body["hint"]


async def test_get_unknown_bot_404(bot_client) -> None:
    resp = await bot_client.get("/api/v1/bots/does-not-exist")
    assert resp.status_code == 404


async def test_health_enable_disable_delete_flow(bot_client) -> None:
    created = await bot_client.post("/api/v1/bots", json={"token": "222:XYZ"})
    bot_id = created.json()["id"]

    health = await bot_client.post(f"/api/v1/bots/{bot_id}/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    disabled = await bot_client.post(f"/api/v1/bots/{bot_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = await bot_client.post(f"/api/v1/bots/{bot_id}/enable")
    assert enabled.json()["enabled"] is True

    removed = await bot_client.delete(f"/api/v1/bots/{bot_id}")
    assert removed.status_code == 204

    missing = await bot_client.get(f"/api/v1/bots/{bot_id}")
    assert missing.status_code == 404


async def test_invalid_kind_rejected(bot_client) -> None:
    resp = await bot_client.get("/api/v1/bots?kind=nonsense")
    assert resp.status_code == 422


async def test_managed_bot_preview_and_flow(bot_client) -> None:
    await bot_client.post("/api/v1/bots", json={"token": "333:MANAGER", "kind": "manager"})

    preview = await bot_client.get("/api/v1/bots/managed/preview?username=newchild")
    assert preview.status_code == 200
    link = preview.json()["create_link"]
    assert link.startswith("https://t.me/newbot/")
    assert "newchild" in link

    registered = await bot_client.post(
        "/api/v1/bots/managed/register",
        json={"user_id": 9090, "username": "childbot", "owner_username": "owner"},
    )
    assert registered.status_code == 201
    managed_id = registered.json()["id"]
    assert registered.json()["has_token"] is False

    fetched = await bot_client.post(f"/api/v1/bots/{managed_id}/managed/token")
    assert fetched.status_code == 200
    assert fetched.json()["has_token"] is True

    managed_list = await bot_client.get("/api/v1/bots/managed/all")
    assert managed_list.status_code == 200
    assert any(b["id"] == managed_id for b in managed_list.json())


async def test_system_status_reports_manager_after_add(bot_client) -> None:
    await bot_client.post("/api/v1/bots", json={"token": "444:MGR", "kind": "manager"})
    resp = await bot_client.get("/api/v1/system/status")
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["checks"]}
    assert checks["manager_bot"]["status"] == "ok"
    assert "managed_bots" in checks
