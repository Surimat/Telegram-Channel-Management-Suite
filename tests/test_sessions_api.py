"""Sessions API tests via the fake session provider (PHASE 4).

The full HTTP flow runs without Telegram. Tests assert that no secret (api_hash,
session contents, full phone) ever appears in an API response.
"""

from __future__ import annotations

API = "/api/v1/sessions"


async def test_sessions_empty(session_client) -> None:
    resp = await session_client.get(API)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_summary_empty(session_client) -> None:
    resp = await session_client.get(f"{API}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0


async def test_auth_start_code_finish_flow(session_client) -> None:
    start = await session_client.post(
        f"{API}/auth/start",
        json={"api_id": "123456", "api_hash": "SECRET-HASH-XYZ", "phone": "+79991234567"},
    )
    assert start.status_code == 200
    body = start.json()
    assert body["next_step"] == "code"
    assert body["account_id"]
    assert body["phone_masked"] == "+7999***4567"
    # Secrets never leak into responses.
    assert "SECRET-HASH-XYZ" not in start.text

    code = await session_client.post(
        f"{API}/{body['account_id']}/code", json={"code": "12345"}
    )
    assert code.status_code == 200
    assert code.json()["done"] is True

    listing = await session_client.get(API)
    assert listing.status_code == 200
    accounts = listing.json()
    assert len(accounts) == 1
    account = accounts[0]
    assert account["status"] == "online"
    assert account["username"] == "fake_user"
    assert account["has_api_hash"] is True
    # No secret material in the serialized list.
    assert "SECRET-HASH-XYZ" not in listing.text
    assert "+79991234567" not in listing.text  # full phone hidden


async def test_auth_bad_code_friendly_error(session_client) -> None:
    start = await session_client.post(
        f"{API}/auth/start",
        json={"api_id": "123456", "api_hash": "h", "phone": "+79990000001"},
    )
    account_id = start.json()["account_id"]
    resp = await session_client.post(f"{API}/{account_id}/code", json={"code": "00000"})
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["message"]
    assert err["hint"]


async def test_auth_start_validation_error(session_client) -> None:
    resp = await session_client.post(
        f"{API}/auth/start", json={"api_id": "abc", "api_hash": "h", "phone": "+7999"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["hint"]


async def test_health_enable_disable_delete(session_client, tmp_path) -> None:
    source = tmp_path / "importme.session"
    source.write_bytes(b"SESSION-BYTES")

    imported = await session_client.post(
        f"{API}/import",
        json={
            "api_id": "123456",
            "api_hash": "HASH-SECRET",
            "phone": "+79991234567",
            "session_file_path": str(source),
        },
    )
    assert imported.status_code == 201
    account_id = imported.json()["id"]
    assert imported.json()["status"] == "online"
    assert "HASH-SECRET" not in imported.text

    health = await session_client.post(f"{API}/{account_id}/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    disabled = await session_client.post(f"{API}/{account_id}/disable")
    assert disabled.json()["enabled"] is False
    assert disabled.json()["status"] == "disabled"

    enabled = await session_client.post(f"{API}/{account_id}/enable")
    assert enabled.json()["enabled"] is True

    deleted = await session_client.delete(f"{API}/{account_id}")
    assert deleted.status_code == 204
    assert (await session_client.get(API)).json() == []


async def test_import_missing_file_friendly_error(session_client) -> None:
    resp = await session_client.post(
        f"{API}/import",
        json={
            "api_id": "123456",
            "api_hash": "h",
            "session_file_path": "/does/not/exist.session",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["hint"]


async def test_logout_requires_reauth(session_client, tmp_path) -> None:
    source = tmp_path / "s.session"
    source.write_bytes(b"x")
    imported = await session_client.post(
        f"{API}/import",
        json={"api_id": "1", "api_hash": "h", "session_file_path": str(source)},
    )
    account_id = imported.json()["id"]
    logged = await session_client.post(f"{API}/{account_id}/logout")
    assert logged.status_code == 200
    assert logged.json()["status"] == "auth_required"
    assert logged.json()["auth_step"] == "idle"
    # The session file reference is never returned by the API.
    assert "session_ref" not in logged.text


async def test_get_unknown_account_404(session_client) -> None:
    resp = await session_client.get(f"{API}/does-not-exist")
    assert resp.status_code == 404


async def test_health_deep_includes_session_checks(session_client) -> None:
    resp = await session_client.get("/health/deep")
    assert resp.status_code == 200
    checks = resp.json()["checks"]
    assert "telethon" in checks
    assert "sessions_dir" in checks
