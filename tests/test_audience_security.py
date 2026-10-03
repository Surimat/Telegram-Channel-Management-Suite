"""Audience security tests (PHASE 5).

Guarantees that the audience subsystem never leaks secrets or raw PII through
API responses, exports, logs/events, or error messages (decisions D-010/D-025).
"""

from __future__ import annotations

import pytest


async def _seed_scan(client) -> None:
    from backend.app.db.session import session_scope
    from backend.app.providers.fake_audience import FakeAudienceProvider
    from backend.app.providers.fake_session import FakeAudienceScenario, make_fake_users
    from backend.app.services.audience_service import AudienceService

    resp = await client.post("/api/v1/audience/sources", json={"reference": "@sec"})
    sid = resp.json()["id"]
    provider = FakeAudienceProvider(
        FakeAudienceScenario(participants=make_fake_users(20), page_size=10)
    )
    await client.post(f"/api/v1/audience/sources/{sid}/scan")
    async with session_scope() as session:
        service = AudienceService(session, audience_provider=provider)
        for _ in range(100):
            await service.run_scan_chunk()
            source = await service.get_source(sid)
            if source.scan_status.value in {"completed", "failed", "cancelled", "paused"}:
                break


async def test_api_never_returns_phone_or_secret(audience_client) -> None:
    await _seed_scan(audience_client)
    users = (await audience_client.get("/api/v1/audience/users")).json()
    for item in users["items"]:
        # Masked field only; no raw phone, no session string, no token.
        assert item.get("phone_masked", "") == ""
        blob = str(item).lower()
        assert "session" not in blob
        assert "token" not in blob
        assert "api_hash" not in blob


async def test_export_default_excludes_pii(audience_client) -> None:
    await _seed_scan(audience_client)
    export = await audience_client.post("/api/v1/audience/export", json={"format": "csv"})
    body = export.json()
    assert body["includes_pii"] is False
    assert "phone_masked" not in body["fields"]

    from pathlib import Path

    content = Path(body["path"]).read_text(encoding="utf-8")
    assert "phone_masked" not in content.splitlines()[0]


async def test_export_pii_blocked_when_disabled(audience_client) -> None:
    await _seed_scan(audience_client)
    resp = await audience_client.post(
        "/api/v1/audience/export", json={"format": "csv", "include_pii": True}
    )
    assert resp.status_code == 400
    assert "персональн" in resp.json()["error"]["message"].lower()


async def test_events_do_not_contain_secrets(audience_client) -> None:
    from sqlalchemy import select

    from backend.app.db.models.event import Event
    from backend.app.db.session import session_scope

    await _seed_scan(audience_client)
    async with session_scope() as session:
        rows = (await session.execute(select(Event))).scalars().all()
        for event in rows:
            blob = f"{event.message} {event.details} {event.explanation}".lower()
            assert "api_hash" not in blob
            assert "session" not in blob


async def test_error_messages_are_human_readable(audience_client) -> None:
    # Missing source → friendly 404 with a fix hint, no stack trace.
    resp = await audience_client.get("/api/v1/audience/sources/missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["message"]
    assert "Traceback" not in body["error"]["message"]


@pytest.mark.parametrize("reference", ["@x"])
async def test_source_type_detection(audience_client, reference) -> None:
    from backend.app.db.session import session_scope
    from backend.app.services.audience_service import AudienceService

    async with session_scope() as session:
        service = AudienceService(session)
        kind, username, tid = await service.detect_source_type("https://t.me/durov")
        assert kind == "channel" and username == "durov" and tid is None

        kind, username, tid = await service.detect_source_type("123456")
        assert kind == "entity" and username == "" and tid == 123456
