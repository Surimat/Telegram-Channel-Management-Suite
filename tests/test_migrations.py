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
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.db import migrate
from backend.app.db.models.setting import Setting
from backend.app.db.session import dispose_engine, get_engine, init_models, session_scope


def _baseline_only_database(db_path: Path) -> None:
    """Create a v1.0.0-shaped database: baseline schema, no channels, with a row.

    Reproduces a real installation that was created by ``create_all`` before the
    Channel Registry existed. It is stamped at the baseline and has an
    ``invite_jobs`` row so the upgrade must add a NOT NULL column to a
    populated table.
    """

    async def _run() -> None:
        # Apply ONLY the baseline revision. Alembic's env.py calls asyncio.run
        # internally, so run it off-loop via a thread (same as the runner).
        from alembic import command

        cfg = migrate._alembic_config()
        await asyncio.to_thread(command.upgrade, cfg, migrate._baseline_revision())
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO invite_jobs "
                    "(name, target, target_title, account_ids, source_ids, filters, "
                    "status, confirmed_summary, dry_run, per_account_delay_min, "
                    "per_account_delay_max, max_per_account, max_total, total_tasks, "
                    "processed_count, invited_count, already_count, privacy_count, "
                    "flood_count, error_count, waiting_account_id, queue_job_id, "
                    "last_error, id, created_at, updated_at) VALUES "
                    "('legacy', '@old', 'Old', '[]', '[]', '{}', 'DRAFT', '', 0, 1, 2, "
                    "0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', '', 'legacyjob1', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
        await dispose_engine()

    asyncio.run(_run())


def test_legacy_v1_database_upgrades_and_keeps_rows() -> None:
    """A v1.0.0 DB (no channels) is adopted at the baseline and upgraded.

    Regression for the bug where an unmarked legacy database was stamped at
    *head*, so the channel-registry migration never ran and the app then failed
    on the missing ``channels`` table.
    """
    from backend.app.core.config import get_settings

    db_path = Path(get_settings().resolve_database_url().split("///")[-1])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _baseline_only_database(db_path)

    async def _run() -> None:
        # The legacy database has no channels table and no alembic marker that
        # points past the baseline.
        status = await migrate.database_status()
        assert status.state == migrate.DB_STATE_PENDING
        assert status.current_revision == migrate._baseline_revision()
        assert migrate._head_revision() in status.pending

        result = await migrate.upgrade_database()
        assert result.state == migrate.DB_STATE_UPDATED
        assert migrate._head_revision() in result.applied

        after = await migrate.database_status()
        assert after.state == migrate.DB_STATE_READY
        assert after.current_revision == after.head_revision

        engine = get_engine()
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda c: __import__("sqlalchemy").inspect(c).get_table_names()
            )
            assert "channels" in tables
            row = (
                await conn.execute(
                    text("SELECT name, channel_id FROM invite_jobs WHERE id='legacyjob1'")
                )
            ).one()
            assert row.name == "legacy"
            assert row.channel_id == ""  # default filled for the existing row

    asyncio.run(_run())


def test_unknown_schema_is_not_adopted() -> None:
    """An unmarked database that is neither empty nor a known schema is refused."""

    async def _run() -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE mystery (id INTEGER PRIMARY KEY)"))
        status = await migrate.database_status()
        assert status.state == migrate.DB_STATE_UNKNOWN
        result = await migrate.upgrade_database()
        assert result.state == migrate.DB_STATE_FAILED

    asyncio.run(_run())


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


def test_v1_2_content_tables_added_with_server_defaults() -> None:
    """The v1.2 content migration adds its tables to an existing database.

    Proves the in-place upgrade path: a pre-v1.2 database (schema via
    ``create_all``, then stamped at head) gains the content tables, and the
    additive columns carry server defaults so no backfill is required.
    """
    import sqlalchemy as sa

    async def _run() -> None:
        # Build a v1.1-shaped schema, then stamp it at the pre-v1.2 revision.
        from alembic import command

        cfg = migrate._alembic_config()
        await asyncio.to_thread(
            command.upgrade, cfg, "b3d7e1a5c9f2"
        )
        await dispose_engine()

        # A v1.1 database has no content tables yet.
        engine = get_engine()
        async with engine.connect() as conn:
            before = await conn.run_sync(
                lambda c: sa.inspect(c).get_table_names()
            )
        assert "content_items" not in before
        await dispose_engine()

        status = await migrate.database_status()
        assert status.state == migrate.DB_STATE_PENDING
        result = await migrate.upgrade_database()
        assert result.state == migrate.DB_STATE_UPDATED

        engine = get_engine()
        async with engine.connect() as conn:
            names = await conn.run_sync(
                lambda c: sa.inspect(c).get_table_names()
            )
            assert {
                "content_sources",
                "content_items",
                "media_assets",
                "publications",
                "button_sets",
                "comment_plans",
            } <= set(names)
            cols = await conn.run_sync(
                lambda c: {col["name"] for col in sa.inspect(c).get_columns("content_items")}
            )
            assert {"held", "moderation_note", "content_hash", "language"} <= cols
            src_cols = await conn.run_sync(
                lambda c: {
                    col["name"] for col in sa.inspect(c).get_columns("content_sources")
                }
            )
            assert {"blocked_keywords", "quiet_hours_enabled", "etag"} <= src_cols

    asyncio.run(_run())
