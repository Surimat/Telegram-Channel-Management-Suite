"""Backup / restore and configuration export / import (PHASE 10).

Design goals:

* A backup is a single ``.tcmsbak`` zip containing the SQLite database plus a
  small ``manifest.json`` (app version, timestamp, whether sessions are
  included). It restores cleanly on the same or a new machine.
* **Session files are never included by default** — they grant full Telegram
  account access. The owner must opt in explicitly (``backup_include_sessions``)
  and even then they are clearly marked in the manifest.
* **Configuration export/import** moves the user-owned rows (settings and
  reaction rules/profiles) between installations as a plain, reviewable JSON
  file. It never contains the encrypted secrets table rows: ``bots`` and
  ``user_sessions`` hold sealed tokens/hashes and are intentionally excluded.
* No secret (bot token, ``api_hash``, phone, session content) is ever placed in
  an API response, log line, or the manifest.

The service is synchronous in its file work (small local zips) and is called
from async endpoints; the database rows are loaded with async SQLAlchemy first.
"""

from __future__ import annotations

import contextlib
import io
import json
import secrets
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import __version__
from backend.app.core.config import Settings, get_settings
from backend.app.db.models.reaction import ReactionProfile, ReactionRule
from backend.app.db.models.setting import Setting
from backend.app.services.events_service import EventsService

BACKUP_SUFFIX = ".tcmsbak"
BACKUP_KIND = "full"
CONFIG_KIND = "config"
_MANIFEST_NAME = "manifest.json"
_DB_MEMBER = "data/app.db"

# Tables exported/imported by configuration transfer, and the model that reads
# and writes each. Order matters for import (nothing here has FK dependencies).
_CONFIG_TABLES: tuple[tuple[str, type], ...] = (
    ("settings", Setting),
    ("reaction_profiles", ReactionProfile),
    ("reaction_rules", ReactionRule),
)

# Never exported/imported: sealed secrets and session references.
_EXCLUDED_TABLES = ("bots", "user_sessions")


class BackupError(RuntimeError):
    """Raised for an invalid or unsafe backup/restore request."""


@dataclass
class BackupEntry:
    """Metadata about a stored backup file."""

    filename: str
    kind: str
    created_at: datetime | None
    size_bytes: int
    includes_sessions: bool
    version: str = ""


@dataclass
class RestoreResult:
    """Outcome of a restore operation."""

    restored: bool
    source: str
    safety_backup: str
    includes_sessions: bool


class BackupService:
    """Create, list, restore and delete backups; export/import configuration."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.events = EventsService(session)

    # --- Locations -----------------------------------------------------------

    def backup_dir(self) -> Path:
        directory = self.settings.resolve_backup_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _database_path(self) -> Path:
        url = self.settings.resolve_database_url()
        prefix = "sqlite+aiosqlite:///"
        if not url.startswith(prefix):
            raise BackupError(
                "Резервное копирование сейчас поддерживает только файловую базу "
                "SQLite. Для внешней базы используйте её собственные средства."
            )
        return Path(url[len(prefix) :])

    # --- Create --------------------------------------------------------------

    async def create_backup(
        self, *, include_sessions: bool | None = None, note: str = ""
    ) -> BackupEntry:
        """Write a full backup (database + manifest) and return its metadata."""
        if include_sessions is None:
            include_sessions = self.settings.backup_include_sessions

        db_path = self._database_path()
        if not db_path.is_file():
            raise BackupError(
                "Файл базы данных не найден. Запустите приложение хотя бы один раз, "
                "чтобы база была создана."
            )

        created = datetime.now(UTC)
        stamp = created.strftime("%Y%m%d-%H%M%S")
        filename = f"backup-{stamp}-{secrets.token_hex(2)}{BACKUP_SUFFIX}"
        target = self.backup_dir() / filename

        manifest = {
            "kind": BACKUP_KIND,
            "app": "Telegram Channel Management Suite",
            "version": __version__,
            "created_at": created.isoformat(),
            "includes_sessions": bool(include_sessions),
            "note": note,
        }

        # Read the DB bytes up front. Committing the current session first
        # flushes pending writes so the snapshot is consistent.
        with contextlib.suppress(Exception):
            await self.session.commit()
        db_bytes = db_path.read_bytes()

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr(_DB_MEMBER, db_bytes)
            if include_sessions:
                self._add_sessions(archive)

        self._prune()
        await self.events.info(
            "backup",
            "Создана резервная копия.",
            explanation="Данные приложения сохранены в один архив.",
            how_to_fix="",
            operation="backup.create",
            status="ok",
            details=f"file={filename}; sessions={bool(include_sessions)}",
        )
        return self._entry_for(target)

    def _add_sessions(self, archive: zipfile.ZipFile) -> None:
        """Add MTProto session files (opt-in only)."""
        directory = self.settings.resolve_sessions_dir()
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.session")):
            archive.write(path, f"sessions/{path.name}")

    # --- List / delete -------------------------------------------------------

    def list_backups(self) -> list[BackupEntry]:
        entries = [
            self._entry_for(p)
            for p in self.backup_dir().glob(f"*{BACKUP_SUFFIX}")
            if p.is_file()
        ]
        entries.sort(key=lambda e: e.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return entries

    def delete_backup(self, filename: str) -> bool:
        target = self._safe_member_path(filename)
        if target.is_file():
            target.unlink()
            return True
        return False

    # --- Restore -------------------------------------------------------------

    async def restore_backup(self, filename: str) -> RestoreResult:
        """Restore a backup, first saving a safety copy of the current state."""
        source = self._safe_member_path(filename)
        if not source.is_file():
            raise BackupError("Выбранный файл резервной копии не найден.")

        includes_sessions = False
        with zipfile.ZipFile(source, "r") as archive:
            names = set(archive.namelist())
            if _DB_MEMBER not in names:
                raise BackupError(
                    "Файл не похож на резервную копию: в нём нет базы данных."
                )
            manifest = self._read_manifest(archive)
            includes_sessions = bool(manifest.get("includes_sessions"))
            db_bytes = archive.read(_DB_MEMBER)
            session_files = {
                n: archive.read(n) for n in names if n.startswith("sessions/")
            }

        # Safety net: snapshot the current database before overwriting it.
        safety = await self.create_backup(note="auto: перед восстановлением")
        await self.session.commit()

        db_path = self._database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(db_bytes)

        if session_files:
            directory = self.settings.resolve_sessions_dir()
            directory.mkdir(parents=True, exist_ok=True)
            for member, payload in session_files.items():
                (directory / Path(member).name).write_bytes(payload)

        await self.events.warning(
            "backup",
            "Резервная копия восстановлена.",
            explanation=(
                "Данные заменены содержимым архива. Если включены сессии, "
                "они также восстановлены."
            ),
            how_to_fix="Перезапустите приложение, чтобы все изменения вступили в силу.",
            operation="backup.restore",
            status="ok",
            details=f"file={filename}; sessions={includes_sessions}",
        )
        return RestoreResult(
            restored=True,
            source=filename,
            safety_backup=safety.filename,
            includes_sessions=includes_sessions,
        )

    # --- Configuration export / import --------------------------------------

    async def export_config(self) -> bytes:
        """Return a JSON document with the user-owned configuration rows."""
        payload: dict[str, object] = {
            "kind": CONFIG_KIND,
            "app": "Telegram Channel Management Suite",
            "version": __version__,
            "exported_at": datetime.now(UTC).isoformat(),
            "excluded_tables": list(_EXCLUDED_TABLES),
            "tables": {},
        }
        tables: dict[str, list[dict[str, object]]] = {}
        for name, model in _CONFIG_TABLES:
            rows = (await self.session.execute(select(model))).scalars().all()
            tables[name] = [self._row_to_dict(model, row) for row in rows]
        payload["tables"] = tables
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    async def import_config(self, data: bytes, *, replace: bool = True) -> dict[str, int]:
        """Import a configuration document produced by :meth:`export_config`.

        ``replace=True`` clears the current configuration tables first. Only the
        whitelisted tables are touched; secrets and sessions are never imported.
        """
        try:
            payload = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise BackupError("Файл конфигурации повреждён или не является JSON.") from exc

        if not isinstance(payload, dict) or payload.get("kind") != CONFIG_KIND:
            raise BackupError("Это не файл конфигурации Telegram Channel Management Suite.")

        tables = payload.get("tables")
        if not isinstance(tables, dict):
            raise BackupError("В файле конфигурации нет раздела с данными.")

        counts: dict[str, int] = {}
        for name, model in _CONFIG_TABLES:
            rows = tables.get(name, [])
            if not isinstance(rows, list):
                continue
            if replace:
                await self.session.execute(delete(model))
            imported = 0
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                self.session.add(model(**self._dict_to_kwargs(model, raw)))
                imported += 1
            counts[name] = imported
        await self.session.commit()

        await self.events.info(
            "backup",
            "Конфигурация импортирована.",
            explanation="Правила, профили реакций и настройки обновлены из файла.",
            how_to_fix="Перезапустите приложение, если изменения не видны сразу.",
            operation="backup.import_config",
            status="ok",
            details="; ".join(f"{k}={v}" for k, v in counts.items()),
        )
        return counts

    # --- Helpers -------------------------------------------------------------

    def _prune(self) -> None:
        retention = int(self.settings.backup_retention)
        if retention <= 0:
            return
        entries = self.list_backups()
        for stale in entries[retention:]:
            with contextlib.suppress(OSError):
                (self.backup_dir() / stale.filename).unlink()

    def _entry_for(self, path: Path) -> BackupEntry:
        kind = BACKUP_KIND
        created_at: datetime | None = None
        includes_sessions = False
        version = ""
        try:
            with zipfile.ZipFile(path, "r") as archive:
                manifest = self._read_manifest(archive)
            kind = str(manifest.get("kind", BACKUP_KIND))
            includes_sessions = bool(manifest.get("includes_sessions"))
            version = str(manifest.get("version", ""))
            created_raw = manifest.get("created_at")
            if isinstance(created_raw, str):
                created_at = datetime.fromisoformat(created_raw)
        except (zipfile.BadZipFile, OSError, ValueError):
            created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if created_at is None:
            created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        return BackupEntry(
            filename=path.name,
            kind=kind,
            created_at=created_at,
            size_bytes=path.stat().st_size,
            includes_sessions=includes_sessions,
            version=version,
        )

    @staticmethod
    def _read_manifest(archive: zipfile.ZipFile) -> dict:
        if _MANIFEST_NAME not in archive.namelist():
            return {}
        try:
            return json.loads(archive.read(_MANIFEST_NAME).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _safe_member_path(self, filename: str) -> Path:
        """Resolve ``filename`` inside the backup dir, rejecting traversal."""
        candidate = (self.backup_dir() / filename).resolve()
        root = self.backup_dir().resolve()
        if root not in candidate.parents:
            raise BackupError("Недопустимое имя файла резервной копии.")
        return candidate

    @staticmethod
    def _row_to_dict(model: type, row: object) -> dict[str, object]:
        result: dict[str, object] = {}
        for column in model.__table__.columns:  # type: ignore[attr-defined]
            if column.name in {"id", "created_at", "updated_at"}:
                continue
            value = getattr(row, column.name)
            result[column.name] = _jsonable(value)
        return result

    @staticmethod
    def _dict_to_kwargs(model: type, raw: dict) -> dict[str, object]:
        columns = {c.name for c in model.__table__.columns}  # type: ignore[attr-defined]
        skip = {"id", "created_at", "updated_at"}
        return {k: v for k, v in raw.items() if k in columns and k not in skip}


def _jsonable(value: object) -> object:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "value"):  # StrEnum members
        return value.value
    return value


def read_backup_manifest(path: Path) -> dict:
    """Read a backup manifest without extracting it (used by scripts/tests)."""
    with zipfile.ZipFile(path, "r") as archive:
        return BackupService._read_manifest(archive)


def build_backup_zip(
    *, db_bytes: bytes, version: str, includes_sessions: bool = False, note: str = ""
) -> bytes:
    """Build an in-memory backup zip (helper for tests and tooling)."""
    buffer = io.BytesIO()
    manifest = {
        "kind": BACKUP_KIND,
        "app": "Telegram Channel Management Suite",
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "includes_sessions": includes_sessions,
        "note": note,
    }
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr(_DB_MEMBER, db_bytes)
    return buffer.getvalue()


__all__ = [
    "BACKUP_KIND",
    "BACKUP_SUFFIX",
    "BackupEntry",
    "BackupError",
    "BackupService",
    "RestoreResult",
    "build_backup_zip",
    "read_backup_manifest",
]
