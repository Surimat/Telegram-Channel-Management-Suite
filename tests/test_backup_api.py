"""Backup API tests (PHASE 10).

Verifies create/list/download/restore/delete plus config export/import, and that
no secret-bearing table or session content ever appears in a response.
"""

from __future__ import annotations

import json

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

BACKUP_BASE = "/api/v1/backup"

_FORBIDDEN = ("api_hash", "token", "password", "phone", "session_encrypted")


@pytest_asyncio.fixture
async def backup_client() -> AsyncClient:
    from backend.app.db.models.reaction import ReactionProfile, ReactionRule
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app
    from backend.app.services.settings_service import SettingsService

    await init_models()
    async with session_scope() as session:
        await SettingsService(session).set("demo_key", "demo-value")
        session.add(ReactionProfile(name="P", allowed_emoji='["👍"]'))
        session.add(ReactionRule(name="R", category="news", keywords='["новость"]'))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_info_is_plain_language(backup_client: AsyncClient) -> None:
    resp = await backup_client.get(f"{BACKUP_BASE}/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["what_it_does"]
    assert "bots" in body["excluded_tables"]
    assert "user_sessions" in body["excluded_tables"]


async def test_create_list_download_delete(backup_client: AsyncClient) -> None:
    created = await backup_client.post(f"{BACKUP_BASE}", json={"note": "api-test"})
    assert created.status_code == 201
    entry = created.json()
    assert entry["filename"].endswith(".tcmsbak")
    assert entry["includes_sessions"] is False
    assert entry["size_bytes"] > 0

    listed = await backup_client.get(BACKUP_BASE)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    assert any(i["filename"] == entry["filename"] for i in body["items"])

    download = await backup_client.get(
        f"{BACKUP_BASE}/download", params={"filename": entry["filename"]}
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert download.content[:2] == b"PK"

    removed = await backup_client.delete(f"{BACKUP_BASE}/{entry['filename']}")
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True


async def test_restore_endpoint(backup_client: AsyncClient) -> None:
    created = (await backup_client.post(BACKUP_BASE, json={})).json()
    resp = await backup_client.post(
        f"{BACKUP_BASE}/restore", params={"filename": created["filename"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["restored"] is True
    assert body["source"] == created["filename"]
    assert body["safety_backup"]


async def test_restore_missing_returns_friendly_error(backup_client: AsyncClient) -> None:
    resp = await backup_client.post(
        f"{BACKUP_BASE}/restore", params={"filename": "missing.tcmsbak"}
    )
    assert resp.status_code == 400
    assert "error" in resp.json()


async def test_config_export_import(backup_client: AsyncClient) -> None:
    exported = await backup_client.get(f"{BACKUP_BASE}/config/export")
    assert exported.status_code == 200
    payload = json.loads(exported.content)
    assert payload["kind"] == "config"
    assert "bots" not in payload["tables"]
    assert "user_sessions" not in payload["tables"]

    resp = await backup_client.post(
        f"{BACKUP_BASE}/config/import",
        files={"file": ("config.json", exported.content, "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"]["reaction_rules"] >= 1


async def test_no_secret_leak_in_backup_responses(backup_client: AsyncClient) -> None:
    created = await backup_client.post(BACKUP_BASE, json={})
    listed = await backup_client.get(BACKUP_BASE)
    info = await backup_client.get(f"{BACKUP_BASE}/info")
    blob = (created.text + listed.text + info.text).lower()
    for word in _FORBIDDEN:
        assert word not in blob, f"leaked {word!r}"


async def test_path_traversal_rejected_by_download(backup_client: AsyncClient) -> None:
    resp = await backup_client.get(
        f"{BACKUP_BASE}/download", params={"filename": "../app.db"}
    )
    assert resp.status_code == 400
