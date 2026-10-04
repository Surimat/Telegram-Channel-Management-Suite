"""Tests for product surfaces: backup destinations, promotion wizard, auto-update.

The update flow is tested with an injected transport (no network), and the wizard
against real system state so its statuses never lie.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.core.versioning import is_newer, parse_sha256, parse_version, pick_asset

DESTINATIONS = "/api/v1/backup/destinations"
PROMOTION = "/api/v1/promotion"
UPDATE = "/api/v1/update"


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- destinations ------------------------------------------------------------
async def test_local_destination_is_created_automatically(client: AsyncClient) -> None:
    resp = await client.get(DESTINATIONS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    kinds = {i["kind"] for i in body["items"]}
    assert "local" in kinds
    assert any(k["name"] == "local" for k in body["available_kinds"])


async def test_add_check_and_delete_remote_destination(client: AsyncClient) -> None:
    created = await client.post(
        DESTINATIONS, json={"kind": "telegram", "config": {"chat_id": "12345"}}
    )
    assert created.status_code == 201, created.text
    dest = created.json()
    assert dest["kind"] == "telegram"
    # Credentials/tokens are never returned.
    assert "token" not in created.text

    checked = await client.post(f"{DESTINATIONS}/{dest['id']}/check")
    assert checked.status_code == 200

    deleted = await client.delete(f"{DESTINATIONS}/{dest['id']}")
    assert deleted.status_code == 200


async def test_local_destination_cannot_be_deleted(client: AsyncClient) -> None:
    listed = await client.get(DESTINATIONS)
    local = next(i for i in listed.json()["items"] if i["kind"] == "local")
    resp = await client.delete(f"{DESTINATIONS}/{local['id']}")
    assert resp.status_code == 400
    assert resp.json()["error"]["message"]


async def test_duplicate_destination_rejected(client: AsyncClient) -> None:
    first = await client.post(DESTINATIONS, json={"kind": "yandex_disk"})
    assert first.status_code == 201
    second = await client.post(DESTINATIONS, json={"kind": "yandex_disk"})
    assert second.status_code == 400


# --- promotion wizard --------------------------------------------------------
async def test_wizard_reflects_real_state(client: AsyncClient) -> None:
    presets = await client.get(f"{PROMOTION}/presets")
    assert presets.status_code == 200
    ids = {p["id"] for p in presets.json()}
    assert {"minimal", "bot_only", "basic", "advanced", "professional"} <= ids

    state = await client.get(PROMOTION)
    assert state.status_code == 200
    body = state.json()
    # No channel and no bot yet → the first two steps are todo, not done.
    by_key = {s["key"]: s for s in body["steps"]}
    assert by_key["channel"]["status"] == "todo"
    assert by_key["manager_bot"]["status"] == "todo"
    # Without a session, session-only steps are optional, not required.
    assert body["has_session"] is False
    assert body["mode"] == "bot_only"


async def test_wizard_session_steps_become_optional_without_session(client: AsyncClient) -> None:
    state = (await client.get(PROMOTION)).json()
    # Default preset is bot_only; no session-gated step is required.
    for step in state["steps"]:
        if step["requires_session"]:
            assert step["status"] == "optional"


async def test_wizard_preset_switch(client: AsyncClient) -> None:
    resp = await client.post(f"{PROMOTION}/preset", json={"preset": "professional"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "professional"
    keys = {s["key"] for s in body["steps"]}
    assert "backup" in keys and "update" in keys


async def test_wizard_finish_and_dismiss(client: AsyncClient) -> None:
    finished = await client.post(f"{PROMOTION}/finish")
    assert finished.status_code == 200
    assert finished.json()["completed"] is True

    dismissed = await client.post(f"{PROMOTION}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["dismissed"] is True


# --- update service (pure + injected transport) ------------------------------
def test_version_comparison() -> None:
    assert is_newer("v1.0.5", "1.0.4") is True
    assert is_newer("1.0.4", "1.0.4") is False
    assert is_newer("v1.1.0-rc1", "1.0.4") is False
    assert is_newer("garbage", "1.0.4") is False
    assert parse_version("v2.3.4") is not None
    assert parse_version("2.3") is None


def test_pick_asset_and_checksum() -> None:
    assets = [
        {"name": "notes.txt", "browser_download_url": "u1"},
        {"name": "tcms-v1.0.5.zip", "browser_download_url": "u2"},
        {"name": "tcms-v1.0.5.zip.sha256", "browser_download_url": "u3"},
    ]
    picked = pick_asset(assets)
    assert picked is not None and picked["name"] == "tcms-v1.0.5.zip"
    assert parse_sha256("deadbeef " + "a" * 64 + "  file") == "a" * 64


class _FakeTransport:
    """Returns canned responses per URL; records calls (no network)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, body):
        from backend.app.services.backup_backends.http import HttpResponse

        self.calls.append((method, url))
        status, payload = self.routes.get(url, (404, b""))
        if isinstance(payload, dict):
            import json

            payload = json.dumps(payload).encode()
        return HttpResponse(status=status, body=payload, headers={})


@pytest.mark.asyncio
async def test_update_check_download_and_verify() -> None:
    import hashlib

    from backend.app.db.session import init_models, session_scope
    from backend.app.services.update_service import UpdateService

    await init_models()
    archive = b"PK\x03\x04fake-zip-bytes"
    digest = hashlib.sha256(archive).hexdigest()
    release = {
        "tag_name": "v99.0.0",
        "html_url": "https://example/release",
        "body": "notes",
        "assets": [
            {"name": "tcms.zip", "browser_download_url": "https://dl/zip"},
            {"name": "tcms.zip.sha256", "browser_download_url": "https://dl/sha"},
        ],
    }
    transport = _FakeTransport(
        {
            "https://api.github.com/repos/o/r/releases/latest": (200, release),
            "https://dl/zip": (200, archive),
            "https://dl/sha": (200, digest.encode()),
        }
    )
    async with session_scope() as session:
        service = UpdateService(
            session, transport=transport, app_version="1.0.4"
        )
        # Force a known repo regardless of ambient settings.
        service.settings.auto_update_repo = "o/r"
        status = await service.check()
        assert status.update_available is True
        assert status.latest_version == "v99.0.0"

        downloaded = await service.download()
        assert downloaded.state == "downloaded"
        assert downloaded.staged_file.endswith(".zip")
        assert downloaded.staged_sha256 == digest


@pytest.mark.asyncio
async def test_update_download_rejects_bad_checksum() -> None:
    from backend.app.db.session import init_models, session_scope
    from backend.app.services.update_service import UpdateService

    await init_models()
    transport = _FakeTransport(
        {
            "https://dl/zip": (200, b"tampered"),
            "https://dl/sha": (200, ("b" * 64).encode()),
        }
    )
    async with session_scope() as session:
        service = UpdateService(session, transport=transport, app_version="1.0.4")
        status = await service.download(url="https://dl/zip", sha256_url="https://dl/sha")
        assert status.state == "error"
        assert "целостност" in status.message


async def test_update_status_endpoint_defaults_off(client: AsyncClient) -> None:
    resp = await client.get(UPDATE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["current_version"]


async def test_update_toggle(client: AsyncClient) -> None:
    resp = await client.post(f"{UPDATE}/enabled", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
