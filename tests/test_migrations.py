"""Tests for the versioned database migration layer (hardening).

Covers the three installation kinds and the safety guarantees:

* fresh install — baseline migration creates the schema;
* existing ``create_all`` install — adopted at head without touching tables,
  and existing rows survive;
* data preserved across an upgrade;
* a pre-migration backup is written before pending work is applied;
* status reporting never raises (unknown on inspection failure).

The tests use the isolated temp database from ``conftest`` and drive the
guarded runner directly (``backend.app.db.migrate``).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from backend.app.db import migrate
from backend.app.db.models.setting import Setting
from backend.app.db.session import dispose_engine, init_models, session_scope


def test_fresh_database_reports_fresh_then_upgrades() -> None:
    """A brand-new database is ``fresh``; upgrade creates the schema."""

    async def _run() -> None:
        status = await migrate.database_status()
        assert status.state == migrate.DB_STATE_FRESH
        assert status.pending  # the baseline is waiting

        result = await migrate.upgrade_database()
        assert result.state == migrate.DB_STATE_UPDATED
        # The baseline was actually applied.
        assert result.applied == [status.head_revision]

        after = await migrate.database_status()
        assert after.state == migrate.DB_STATE_READY
        assert after.current_revision == after.head_revision

        # Alembic's marker table now exists.
        engine = migrate.get_engine()
        async with engine.connect() as conn:
            names = await conn.run_sync(
                lambda c: __import__("sqlalchemy").inspect(c).get_table_names()
            )
        assert "alembic_version" in names

    asyncio.run(_run())


def test_existing_create_all_database_is_adopted_without_data_loss() -> None:
    """A pre-Alembic DB (built by ``create_all``) is stamped, data survives."""

    async def _run() -> None:
        # Simulate an old install: schema via create_all + a user row.
        await init_models()
        async with session_scope() as session:
            session.add(Setting(key="legacy_check", value="keep-me"))
        await dispose_engine()

        status = await migrate.database_status()
        # Tables exist but no alembic marker → reported ready (adoptable).
        assert status.state == migrate.DB_STATE_READY

        result = await migrate.upgrade_database()
        assert result.state == migrate.DB_STATE_UPDATED
        assert result.applied == []  # nothing re-created

        async with session_scope() as session:
            value = (
                await session.execute(
                    text("SELECT value FROM settings WHERE key='legacy_check'")
                )
            ).scalar_one_or_none()
            version = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
        assert value == "keep-me"
        assert version == status.head_revision

    asyncio.run(_run())


def test_pre_migration_backup_is_written_for_pending_upgrade() -> None:
    """Pending migrations write a safety backup; fresh DBs do not need one."""

    async def _run() -> None:
        # Fresh database: nothing to back up.
        assert migrate.create_pre_migration_backup() is None

        # Build schema, then pretend a new revision is pending by clearing the
        # marker table (forces the upgrade path to run).
        await init_models()
        await dispose_engine()
        assert migrate.create_pre_migration_backup() is not None

    asyncio.run(_run())


def test_status_reports_unknown_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """An inspection failure is reported, never raised."""

    async def _run() -> None:
        def _boom() -> str:
            raise RuntimeError("no migrations dir")

        monkeypatch.setattr(migrate, "_head_revision", _boom)
        status = await migrate.database_status()
        assert status.state == migrate.DB_STATE_UNKNOWN
        assert "no migrations dir" in status.error

    asyncio.run(_run())
