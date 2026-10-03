"""Guarded runtime database migration runner (hardening: versioned migrations).

This module replaces ``create_all`` at application startup with **versioned
Alembic migrations**, while staying safe for every installation kind:

* **Fresh install** — the database file does not exist yet. The baseline
  revision creates the full schema.
* **Existing install** — the database was created earlier by ``create_all`` and
  already has the application tables but no ``alembic_version`` marker. The
  runner **stamps** it at the current head (no table is touched, no data is
  lost) instead of re-running ``CREATE TABLE`` and failing.
* **Upgrade** — new revisions are pending. The runner takes a **pre-migration
  backup** of the SQLite file, then applies them inside a transaction. A failure
  rolls back and leaves the database intact.

Nothing here bypasses safety: a migration that raises never deletes the
database, and a backup is always written before pending work is applied.

The CLI entry point is::

    python -m backend.app.db.migrate upgrade
    python -m backend.app.db.migrate status
    python -m backend.app.db.migrate current
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from backend.app.core import paths
from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.db.session import get_engine

logger = get_logger(__name__)

# Beginner-facing states (docs/UI.md). Kept here so API, wizard and CLI agree.
DB_STATE_FRESH = "fresh"        # no schema yet — will be created
DB_STATE_READY = "ready"        # schema present and up to date
DB_STATE_PENDING = "pending"    # an update is available
DB_STATE_UPDATING = "updating"  # an update is running
DB_STATE_UPDATED = "updated"    # an update just finished successfully
DB_STATE_FAILED = "failed"      # an update failed; a backup file was kept
DB_STATE_UNKNOWN = "unknown"    # could not be determined

DB_MESSAGES = {
    DB_STATE_FRESH: "База данных будет создана при первом запуске.",
    DB_STATE_READY: "База данных готова.",
    DB_STATE_PENDING: "Для базы доступно обновление.",
    DB_STATE_UPDATING: "Идёт обновление структуры базы.",
    DB_STATE_UPDATED: "Обновление завершено.",
    DB_STATE_FAILED: "Обновление не удалось. Создан резервный файл.",
    DB_STATE_UNKNOWN: "Не удалось проверить структуру базы данных.",
}


class MigrationError(RuntimeError):
    """Raised when the database state cannot be determined or migrated safely."""


@dataclass
class MigrationStatus:
    """Snapshot of the database migration state."""

    state: str
    current_revision: str | None
    head_revision: str
    pending: list[str] = field(default_factory=list)
    message: str = ""
    error: str = ""

    @property
    def is_current(self) -> bool:
        return self.state in {DB_STATE_READY, DB_STATE_UPDATED}


@dataclass
class MigrationResult:
    """Outcome of an upgrade attempt."""

    state: str
    applied: list[str] = field(default_factory=list)
    backup_file: str | None = None
    message: str = ""
    error: str = ""


def _alembic_config() -> AlembicConfig:
    """Build an Alembic config pointing at this project's migrations."""
    cfg = AlembicConfig(str(paths.alembic_ini()))
    cfg.set_main_option("script_location", str(paths.migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", get_settings().resolve_database_url())
    return cfg


def _head_revision() -> str:
    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_current_head()
    if head is None:  # pragma: no cover - a project without revisions
        raise MigrationError("В проекте нет ни одной миграции.")
    return head


def _pending_revisions(current: str | None) -> list[str]:
    """Return revision ids between ``current`` and head (oldest first)."""
    script = ScriptDirectory.from_config(_alembic_config())
    if current is None:
        return [rev.revision for rev in script.walk_revisions()][::-1]
    pending: list[str] = []
    for rev in script.walk_revisions("head", current):
        if rev.revision != current:
            pending.append(rev.revision)
    return pending[::-1]


async def _table_names() -> list[str]:
    engine = get_engine()
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    return names


async def _current_revision() -> str | None:
    """Read ``alembic_version.version_num`` if the table exists."""
    names = await _table_names()
    if "alembic_version" not in names:
        return None
    engine = get_engine()
    async with engine.connect() as conn:
        row = await conn.execute(text("SELECT version_num FROM alembic_version"))
        value = row.scalar_one_or_none()
    return str(value) if value else None


async def database_status() -> MigrationStatus:
    """Determine the current database migration state (read-only).

    Never raises for an ordinary "not migrated yet" situation; those are
    reported as ``fresh``. A genuine inspection error is reported as
    ``unknown`` with the reason in ``error``.
    """
    try:
        head = _head_revision()
        tables = await _table_names()
    except Exception as exc:  # pragma: no cover - environment dependent
        return MigrationStatus(
            state=DB_STATE_UNKNOWN,
            current_revision=None,
            head_revision="",
            message=DB_MESSAGES[DB_STATE_UNKNOWN],
            error=str(exc),
        )

    current = await _current_revision()
    if current is None:
        # No Alembic marker. Distinguish a truly empty DB from one created by
        # an older `create_all` install that already holds the app tables.
        app_tables = [t for t in tables if t not in {"alembic_version"}]
        if not app_tables:
            return MigrationStatus(
                state=DB_STATE_FRESH,
                current_revision=None,
                head_revision=head,
                pending=[head],
                message=DB_MESSAGES[DB_STATE_FRESH],
            )
        # Existing pre-Alembic database: it is already at the baseline schema.
        return MigrationStatus(
            state=DB_STATE_READY,
            current_revision=head,
            head_revision=head,
            message=DB_MESSAGES[DB_STATE_READY],
        )

    pending = _pending_revisions(current)
    if pending:
        return MigrationStatus(
            state=DB_STATE_PENDING,
            current_revision=current,
            head_revision=head,
            pending=pending,
            message=DB_MESSAGES[DB_STATE_PENDING],
        )
    return MigrationStatus(
        state=DB_STATE_READY,
        current_revision=current,
        head_revision=head,
        message=DB_MESSAGES[DB_STATE_READY],
    )


def _database_path() -> Path | None:
    """Return the SQLite file path, or ``None`` for a non-file database."""
    url = get_settings().resolve_database_url()
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix):]
    if raw.startswith(":") or not raw:  # in-memory
        return None
    return Path(raw)


def create_pre_migration_backup() -> str | None:
    """Copy the SQLite file to ``backups/`` before applying migrations.

    Returns the backup file name, or ``None`` when there is nothing to back up
    (fresh or in-memory database). A copy failure is raised so the caller can
    abort rather than migrate without a safety net.
    """
    db_path = _database_path()
    if db_path is None or not db_path.exists() or db_path.stat().st_size == 0:
        return None
    backup_dir = get_settings().resolve_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"premigration-{stamp}-{db_path.name}"
    shutil.copy2(db_path, target)
    logger.info("Pre-migration backup written: %s", target.name)
    return target.name


async def _stamp_head() -> None:
    """Mark an existing pre-Alembic database as being at head (no schema change)."""

    def _run() -> None:
        command.stamp(_alembic_config(), "head")

    await asyncio.to_thread(_run)


async def upgrade_database(*, make_backup: bool = True) -> MigrationResult:
    """Bring the database up to date, safely.

    * Fresh/empty database → run the baseline migration.
    * Existing pre-Alembic database → stamp at head (never re-create tables).
    * Pending revisions → back up, then apply inside a transaction.

    A failure returns ``state=failed`` with the backup file name and leaves the
    database untouched.
    """
    status = await database_status()
    if status.state == DB_STATE_UNKNOWN:
        return MigrationResult(
            state=DB_STATE_FAILED,
            message=DB_MESSAGES[DB_STATE_FAILED],
            error=status.error or DB_MESSAGES[DB_STATE_UNKNOWN],
        )

    # Existing schema without an Alembic marker: adopt it, do not recreate.
    # (Checked before the READY early-return because such a database is
    # reported READY for the wizard but still needs the version marker.)
    tables = await _table_names()
    has_app_tables = any(t != "alembic_version" for t in tables)
    current = await _current_revision()
    if has_app_tables and current is None:
        try:
            await _stamp_head()
        except Exception as exc:  # pragma: no cover - defensive
            return MigrationResult(
                state=DB_STATE_FAILED,
                message=DB_MESSAGES[DB_STATE_FAILED],
                error=str(exc),
            )
        logger.info("Existing database adopted at Alembic head (no schema change)")
        return MigrationResult(
            state=DB_STATE_UPDATED,
            applied=[],
            message=DB_MESSAGES[DB_STATE_UPDATED],
        )

    if status.state == DB_STATE_READY:
        return MigrationResult(state=DB_STATE_READY, message=DB_MESSAGES[DB_STATE_READY])

    backup_file: str | None = None
    if make_backup:
        backup_file = create_pre_migration_backup()

    def _run() -> None:
        command.upgrade(_alembic_config(), "head")

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:
        logger.error("Database migration failed: %s", exc)
        return MigrationResult(
            state=DB_STATE_FAILED,
            applied=[],
            backup_file=backup_file,
            message=DB_MESSAGES[DB_STATE_FAILED],
            error=str(exc),
        )

    after = await database_status()
    return MigrationResult(
        state=DB_STATE_UPDATED,
        applied=status.pending,
        backup_file=backup_file,
        message=DB_MESSAGES[DB_STATE_UPDATED],
    ) if after.is_current else MigrationResult(
        state=DB_STATE_FAILED,
        backup_file=backup_file,
        message=DB_MESSAGES[DB_STATE_FAILED],
        error="Структура базы не достигла последней версии.",
    )


def _format_status(status: MigrationStatus) -> str:
    lines = [
        f"Состояние базы: {status.message}",
        f"Текущая версия: {status.current_revision or '—'}",
        f"Последняя версия: {status.head_revision or '—'}",
    ]
    if status.pending:
        lines.append(f"Ожидают применения: {len(status.pending)}")
    if status.error:
        lines.append(f"Подробности: {status.error}")
    return "\n".join(lines)


def _cli(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    action = args[0] if args else "status"
    if action == "upgrade":
        result = asyncio.run(upgrade_database())
        print(result.message)
        if result.backup_file:
            print(f"Резервная копия: {result.backup_file}")
        if result.error:
            print(f"Подробности: {result.error}")
        return 0 if result.state in {DB_STATE_UPDATED, DB_STATE_READY} else 1
    if action == "current":
        current = asyncio.run(_current_revision())
        print(current or "—")
        return 0
    if action == "status":
        status = asyncio.run(database_status())
        print(_format_status(status))
        return 0
    print(f"Неизвестная команда: {action}. Используйте: status | upgrade | current")
    return 2


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(_cli())
