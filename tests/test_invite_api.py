"""Invite API tests (PHASE 6).

Run the full HTTP slice against the fake session provider: preview → create →
confirm → tasks → pause/stop. No secrets must ever appear in responses.
"""

from __future__ import annotations


async def test_preview_endpoint(invite_client) -> None:
    resp = await invite_client.post("/api/v1/invites/preview", json={"target": "@target"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_candidates"] == 5
    assert data["requires_confirmation"] is True
    assert data["explanation"]


async def test_preview_requires_target(invite_client) -> None:
    resp = await invite_client.post("/api/v1/invites/preview", json={"target": ""})
    assert resp.status_code == 400
    assert resp.json()["error"]["message"]


async def test_create_requires_confirmation_before_start(invite_client) -> None:
    resp = await invite_client.post(
        "/api/v1/invites",
        json={"target": "@target", "per_account_delay_min": 0, "per_account_delay_max": 0},
    )
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "draft"
    assert job["total_tasks"] == 5
    assert job["confirmed_at"] is None

    # Tasks are planned but nothing has run yet.
    tasks = await invite_client.get(f"/api/v1/invites/{job['id']}/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["total"] == 5


async def test_full_run_via_api(invite_client) -> None:
    created = await invite_client.post(
        "/api/v1/invites",
        json={"target": "@target", "per_account_delay_min": 0, "per_account_delay_max": 0},
    )
    job_id = created.json()["id"]

    confirmed = await invite_client.post(f"/api/v1/invites/{job_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "running"
    assert confirmed.json()["confirmed_at"] is not None

    # Simulate the scheduler: the durable handler drives the run.
    from backend.app.db.session import session_scope
    from backend.app.providers.fake_session import FakeSessionProvider
    from backend.app.services.invite_service import InviteService

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return FakeSessionProvider()

    for _ in range(50):
        async with session_scope() as session:
            action, _ = await InviteService(
                session, session_provider_factory=_factory
            ).run_tick(job_id)
        if action in {"done", "paused"}:
            break

    final = await invite_client.get(f"/api/v1/invites/{job_id}")
    body = final.json()
    assert body["status"] == "completed"
    assert body["invited_count"] == 5

    listed = await invite_client.get("/api/v1/invites")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


async def test_pause_and_stop_via_api(invite_client) -> None:
    created = await invite_client.post("/api/v1/invites", json={"target": "@target"})
    job_id = created.json()["id"]
    await invite_client.post(f"/api/v1/invites/{job_id}/confirm")

    paused = await invite_client.post(f"/api/v1/invites/{job_id}/pause")
    assert paused.json()["status"] == "paused"

    resumed = await invite_client.post(f"/api/v1/invites/{job_id}/resume")
    assert resumed.json()["status"] == "running"

    stopped = await invite_client.post(f"/api/v1/invites/{job_id}/stop")
    assert stopped.json()["status"] == "stopped"


async def test_unknown_job_returns_friendly_404(invite_client) -> None:
    resp = await invite_client.get("/api/v1/invites/does-not-exist")
    assert resp.status_code == 404
    assert "не найдено" in resp.json()["error"]["message"].lower()


async def test_responses_never_leak_secrets(invite_client) -> None:
    created = await invite_client.post("/api/v1/invites", json={"target": "@target"})
    body = created.text
    for needle in ("api_hash", "session", "token", "password", "+7"):
        assert needle not in body.lower()

    listed = await invite_client.get("/api/v1/invites")
    assert "api_hash" not in listed.text.lower()


async def test_summary_endpoint(invite_client) -> None:
    resp = await invite_client.get("/api/v1/invites/summary")
    assert resp.status_code == 200
    assert "by_status" in resp.json()


async def test_invalid_status_filter(invite_client) -> None:
    resp = await invite_client.get("/api/v1/invites", params={"status": "bogus"})
    assert resp.status_code == 400
