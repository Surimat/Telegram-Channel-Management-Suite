"""Backup / restore service tests (PHASE 10)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from backend.app.db.models.reaction import ReactionProfile, ReactionRule
from backend.app.db.session import init_models, session_scope
from backend.app.services.backup_service import BackupError, BackupService


async def _seed(session) -> None:  # type: ignore[no-untyped-def]
    from backend.app.services.settings_service import SettingsService

    await SettingsService(session).set("demo_key", "demo-value")
    session.add(
        ReactionProfile(name="Тестовый профиль", allowed_emoji='["👍"]', enabled=True)
    )
    session.add(ReactionRule(name="donation rule", category="donation", keywords='["спасибо"]'))


@pytest.mark.asyncio
async def test_create_and_list_backup() -> None:
    await init_models()
    async with session_scope() as session:
        service = BackupService(session)
        entry = await service.create_backup(note="test")

        assert entry.filename.endswith(".tcmsbak")
        assert entry.kind == "full"
        assert entry.includes_sessions is False
        assert entry.size_bytes > 0

        listed = service.list_backups()
        assert [e.filename for e in listed] == [entry.filename]

        target = service.backup_dir() / entry.filename
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
        assert "manifest.json" in names
        assert "data/app.db" in names
        assert not any(n.startswith("sessions/") for n in names)


@pytest.mark.asyncio
async def test_backup_restore_round_trip() -> None:
    await init_models()
    async with session_scope() as session:
        await _seed(session)
        service = BackupService(session)
        entry = await service.create_backup()

    # Wipe the settings table, then restore and confirm the value is back.
    async with session_scope() as session:
        from sqlalchemy import delete

        from backend.app.db.models.setting import Setting

        await session.execute(delete(Setting))
        assert await BackupService(session).export_config()  # still exports

    async with session_scope() as session:
        result = await BackupService(session).restore_backup(entry.filename)
        assert result.restored is True
        assert result.source == entry.filename
        assert result.safety_backup
        assert result.includes_sessions is False

    async with session_scope() as session:
        from backend.app.services.settings_service import SettingsService

        assert await SettingsService(session).get_typed("demo_key") == "demo-value"


@pytest.mark.asyncio
async def test_restore_creates_safety_backup() -> None:
    await init_models()
    async with session_scope() as session:
        service = BackupService(session)
        entry = await service.create_backup()
    async with session_scope() as session:
        service = BackupService(session)
        before = len(service.list_backups())
        result = await service.restore_backup(entry.filename)
        after = service.list_backups()
    # Original + safety backup.
    assert len(after) >= before + 1
    assert result.safety_backup != entry.filename
    assert (service.backup_dir() / result.safety_backup).is_file()


@pytest.mark.asyncio
async def test_restore_missing_file_raises() -> None:
    await init_models()
    async with session_scope() as session:
        with pytest.raises(BackupError):
            await BackupService(session).restore_backup("nope.tcmsbak")


@pytest.mark.asyncio
async def test_restore_rejects_non_backup_zip(tmp_path: Path) -> None:
    await init_models()
    async with session_scope() as session:
        service = BackupService(session)
        bad = service.backup_dir() / "bad.tcmsbak"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("readme.txt", "not a backup")
        with pytest.raises(BackupError):
            await service.restore_backup("bad.tcmsbak")


@pytest.mark.asyncio
async def test_path_traversal_rejected() -> None:
    await init_models()
    async with session_scope() as session:
        service = BackupService(session)
        with pytest.raises(BackupError):
            service._safe_member_path("../outside.tcmsbak")


@pytest.mark.asyncio
async def test_config_export_import_round_trip() -> None:
    await init_models()
    async with session_scope() as session:
        await _seed(session)
        exported = await BackupService(session).export_config()

    import json

    payload = json.loads(exported)
    assert payload["kind"] == "config"
    assert "bots" in payload["excluded_tables"]
    assert "user_sessions" in payload["excluded_tables"]
    assert payload["tables"]["reaction_rules"]
    # No secret-bearing tables present.
    assert "bots" not in payload["tables"]
    assert "user_sessions" not in payload["tables"]

    async with session_scope() as session:
        counts = await BackupService(session).import_config(exported, replace=True)
    assert counts["settings"] >= 1
    assert counts["reaction_rules"] >= 1
    assert counts["reaction_profiles"] >= 1


@pytest.mark.asyncio
async def test_import_config_rejects_garbage() -> None:
    await init_models()
    async with session_scope() as session:
        with pytest.raises(BackupError):
            await BackupService(session).import_config(b"not json")
        with pytest.raises(BackupError):
            await BackupService(session).import_config(b'{"kind": "other"}')


@pytest.mark.asyncio
async def test_retention_prunes_old_backups() -> None:
    await init_models()
    async with session_scope() as session:
        service = BackupService(session)
        service.settings.backup_retention = 2
        for i in range(4):
            await service.create_backup(note=f"n{i}")
        remaining = service.list_backups()
    assert len(remaining) == 2
