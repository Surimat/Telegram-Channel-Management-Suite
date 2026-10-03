"""API tests: health, system status, settings, events, queue."""

from __future__ import annotations


async def test_health(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_health_deep(client) -> None:
    resp = await client.get("/health/deep")
    assert resp.status_code == 200
    body = resp.json()
    assert "checks" in body
    assert body["checks"]["database"] == "ok"


async def test_system_status_plain_language(client) -> None:
    resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] in {"ok", "warning", "error"}
    keys = {c["key"] for c in body["checks"]}
    assert "database" in keys
    # Manager bot not configured -> warning with friendly advice.
    manager = next(c for c in body["checks"] if c["key"] == "manager_bot")
    assert manager["status"] == "warning"
    assert "BotFather" in manager["how_to_fix"]


async def test_system_setup_endpoint(client) -> None:
    resp = await client.get("/api/v1/system/setup")
    assert resp.status_code == 200
    checks = resp.json()
    assert isinstance(checks, list)
    assert any(c["key"] == "filesystem" for c in checks)


async def test_shutdown_allowed_locally_in_dev(client, monkeypatch) -> None:
    # Ensure the deferred signal can never affect the test runner.
    import backend.app.api.v1.system as system_module

    monkeypatch.setattr(system_module.os, "kill", lambda *a, **k: None)
    resp = await client.post("/api/v1/system/shutdown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "shutting_down"


async def test_settings_crud(client) -> None:
    resp = await client.patch("/api/v1/settings", json={"values": {"reaction_delay_min": "45"}})
    assert resp.status_code == 200
    resp = await client.get("/api/v1/settings")
    assert resp.status_code == 200
    values = {s["key"]: s["value"] for s in resp.json()}
    assert values["reaction_delay_min"] == "45"


async def test_events_empty_then_resolve_404(client) -> None:
    resp = await client.get("/api/v1/events")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    resp = await client.post("/api/v1/events/does-not-exist/resolve")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"


async def test_queue_retry_404(client) -> None:
    resp = await client.post("/api/v1/queue/nope/retry")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_api_404_not_shadowed_by_spa(client) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
