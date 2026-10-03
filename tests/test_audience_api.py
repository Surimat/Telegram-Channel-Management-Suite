"""Audience API tests (PHASE 5) — run against the fake provider, no network."""

from __future__ import annotations

import pytest


async def _create_source(client, reference="@testsource") -> str:
    resp = await client.post("/api/v1/audience/sources", json={"reference": reference})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _scan_and_wait(client, source_id: str) -> None:
    # The API starts a durable job; in tests the scheduler is disabled, so drive
    # the scan synchronously through the service (with the same fake audience
    # data the API's provider override serves) to completion.
    from backend.app.db.session import session_scope
    from backend.app.providers.fake_audience import FakeAudienceProvider
    from backend.app.providers.fake_session import FakeAudienceScenario, make_fake_users
    from backend.app.services.audience_service import AudienceService

    provider = FakeAudienceProvider(
        FakeAudienceScenario(participants=make_fake_users(120), page_size=50)
    )
    await client.post(f"/api/v1/audience/sources/{source_id}/scan")
    async with session_scope() as session:
        service = AudienceService(session, audience_provider=provider)
        for _ in range(200):
            await service.run_scan_chunk()
            source = await service.get_source(source_id)
            if source.scan_status.value in {"completed", "failed", "cancelled", "paused"}:
                break


async def test_create_list_and_get_source(audience_client) -> None:
    sid = await _create_source(audience_client)
    resp = await audience_client.get("/api/v1/audience/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == sid

    one = await audience_client.get(f"/api/v1/audience/sources/{sid}")
    assert one.status_code == 200
    assert one.json()["scan_status"] == "idle"


async def test_create_source_requires_reference(audience_client) -> None:
    resp = await audience_client.post("/api/v1/audience/sources", json={"reference": "  "})
    assert resp.status_code == 400
    assert "error" in resp.json()


async def test_update_and_delete_source(audience_client) -> None:
    sid = await _create_source(audience_client)
    resp = await audience_client.patch(
        f"/api/v1/audience/sources/{sid}", json={"title": "Новое имя", "enabled": False}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Новое имя"
    assert resp.json()["enabled"] is False

    resp = await audience_client.delete(f"/api/v1/audience/sources/{sid}")
    assert resp.status_code == 204
    assert (await audience_client.get(f"/api/v1/audience/sources/{sid}")).status_code == 404


async def test_source_404(audience_client) -> None:
    assert (await audience_client.get("/api/v1/audience/sources/nope")).status_code == 404


async def test_check_source(audience_client) -> None:
    sid = await _create_source(audience_client)
    resp = await audience_client.post(f"/api/v1/audience/sources/{sid}/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["participants_count"] == 120


async def test_scan_preview(audience_client) -> None:
    sid = await _create_source(audience_client)
    resp = await audience_client.post(f"/api/v1/audience/sources/{sid}/scan/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_id"] == sid
    assert body["account_label"]
    assert body["notes"]


async def test_full_scan_flow_and_users(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)

    progress = await audience_client.get(
        f"/api/v1/audience/sources/{sid}/scan/progress"
    )
    body = progress.json()
    assert body["scan_status"] == "completed"
    assert body["completeness"] == "complete"
    assert body["discovered"] == 120

    users = await audience_client.get("/api/v1/audience/users", params={"limit": 10})
    assert users.status_code == 200
    assert users.json()["total"] == 120
    assert len(users.json()["items"]) == 10


async def test_users_search_and_filter(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)

    resp = await audience_client.get(
        "/api/v1/audience/users", params={"search": "user10"}
    )
    # user10, user100..user109 all match "user10".
    assert resp.json()["total"] == 11

    resp = await audience_client.get(
        "/api/v1/audience/users", params={"has_username": True}
    )
    assert resp.json()["total"] == 120


async def test_tags_endpoints(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)
    users = (await audience_client.get("/api/v1/audience/users", params={"limit": 3})).json()
    ids = [u["id"] for u in users["items"]]

    resp = await audience_client.post(
        "/api/v1/audience/tags/assign", json={"user_ids": ids, "tags": ["vip"]}
    )
    assert resp.json()["updated"] == 3

    tags = (await audience_client.get("/api/v1/audience/tags")).json()
    assert any(t["name"] == "vip" for t in tags)

    # Filter by tag.
    resp = await audience_client.get("/api/v1/audience/users", params={"tag": "vip"})
    assert resp.json()["total"] == 3

    resp = await audience_client.post(
        "/api/v1/audience/tags/rename", json={"old": "vip", "new": "important"}
    )
    assert resp.json()["updated"] == 3

    resp = await audience_client.request(
        "DELETE", "/api/v1/audience/tags/important"
    )
    assert resp.json()["updated"] == 3


async def test_user_detail(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)
    users = (await audience_client.get("/api/v1/audience/users")).json()
    uid = users["items"][0]["id"]

    resp = await audience_client.get(f"/api/v1/audience/users/{uid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"]
    assert "score_components" in body
    # No raw phone leaks into responses.
    assert "phone" not in body or body.get("phone_masked", "") == ""


async def test_dashboard_and_presets(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)

    dash = (await audience_client.get("/api/v1/audience/dashboard")).json()
    assert dash["unique_users"] == 120
    assert dash["sources_total"] == 1

    presets = (await audience_client.get("/api/v1/audience/filters/presets")).json()
    assert any(p["key"] == "active" for p in presets)


async def test_export_and_import(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)

    preview = await audience_client.post(
        "/api/v1/audience/export/preview", json={"format": "csv"}
    )
    assert preview.status_code == 200
    assert preview.json()["count"] == 120
    assert "telegram_user_id" in preview.json()["fields"]

    export = await audience_client.post("/api/v1/audience/export", json={"format": "csv"})
    assert export.status_code == 200
    assert export.json()["row_count"] == 120
    assert export.json()["includes_pii"] is False

    csv_data = "telegram_user_id,username\n999001,imported_one\n999002,imported_two\n"
    imp = await audience_client.post(
        "/api/v1/audience/import", json={"data": csv_data, "format": "csv"}
    )
    assert imp.json()["created"] == 2


async def test_bulk_status(audience_client) -> None:
    sid = await _create_source(audience_client)
    await _scan_and_wait(audience_client, sid)
    users = (await audience_client.get("/api/v1/audience/users", params={"limit": 2})).json()
    ids = [u["id"] for u in users["items"]]
    resp = await audience_client.post(
        "/api/v1/audience/users/bulk-status", json={"user_ids": ids, "status": "blocked"}
    )
    assert resp.json()["updated"] == 2


@pytest.mark.parametrize("bad", ["unknown-ish"])
async def test_bulk_status_rejects_unknown(audience_client, bad) -> None:
    resp = await audience_client.post(
        "/api/v1/audience/users/bulk-status", json={"user_ids": ["x"], "status": bad}
    )
    assert resp.status_code == 400


async def test_scan_lifecycle_endpoints(audience_client) -> None:
    sid = await _create_source(audience_client)
    await audience_client.post(f"/api/v1/audience/sources/{sid}/scan")
    pause = await audience_client.post(f"/api/v1/audience/sources/{sid}/scan/pause")
    assert pause.json()["scan_status"] == "paused"
    resume = await audience_client.post(f"/api/v1/audience/sources/{sid}/scan/resume")
    assert resume.json()["scan_status"] == "scanning"
    cancel = await audience_client.post(f"/api/v1/audience/sources/{sid}/scan/cancel")
    assert cancel.json()["scan_status"] == "cancelled"
