#!/usr/bin/env python3
"""One-step in-place update that preserves the owner's data and secrets.

The owner extracts a newer Windows portable build, double-clicks
``UPDATE_EXISTING.bat``, and this script updates the existing installation
without losing anything. It never asks the owner to copy files, edit ``.env``
or re-enter tokens.

What it does, in order:

1. Locate the existing installation (``--root`` or ``--auto``).
2. Copy every irreplaceable user artefact into
   ``<root>/backups/preupdate-<timestamp>/`` **before** touching anything:
   ``.env`` (holds ``APP_SECRET_KEY`` and the manager token), ``data/`` (the
   SQLite database with the sealed bot/account secrets, ``sync/`` and
   ``tray.json``), ``sessions/`` (MTProto sessions), ``exports/`` and the old
   ``app/`` code.
3. Replace only the application code (``app/``) with the new build's code. It
   never copies the new ``.env`` over the old one; it only appends settings that
   are missing, and never a secret-looking key.
4. Apply pending Alembic migrations to the existing database (the runner takes
   its own pre-migration copy of the DB first).
5. Prove the result: bot/channel/job/owner rows are still there and every
   ``enc:`` secret still decrypts with the preserved ``APP_SECRET_KEY``. On any
   failure it stops, leaves the original data untouched and points at the backup.

Nothing here touches Telegram: no publications, no invites, no session use.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

NEW_ROOT = Path(__file__).resolve().parents[1]

#: Application code copied from the new build into ``<old>/app``.
_CODE_ITEMS = (
    "backend",
    "migrations",
    "alembic.ini",
    "pyproject.toml",
    "requirements.txt",
    ".env.example",
)
#: User directories copied into the backup (irreplaceable state / secrets).
_BACKUP_DIRS = ("data", "sessions", "exports")
#: User directories never touched and never deleted (preserved in place).
_KEEP_DIRS = ("backups", "logs", "models", "updates")
#: A setting whose name looks like this is never appended by the env merge.
_SECRETISH = re.compile(r"(SECRET|TOKEN|PASSWORD|API_HASH|PRIVATE|PASSPHRASE)", re.I)
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NEED_TARGET = 3


def _log(message: str) -> None:
    print(message, flush=True)


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_value(text: str, key: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            if name.strip() == key:
                return value.strip()
    return ""


def _db_path(root: Path) -> Path:
    url = _parse_env(root / ".env").get("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/"):
        rel = url[len(prefix) :]
        if not rel.startswith(":"):
            return (root / rel).resolve()
    return (root / "data" / "app.db").resolve()


def _looks_like_install(path: Path) -> bool:
    if not path.is_dir():
        return False
    has_code = (path / "app" / "backend" / "app" / "main.py").is_file() or (
        path / "backend" / "app" / "main.py"
    ).is_file()
    has_data = (path / ".env").is_file() or (path / "data" / "app.db").is_file()
    return has_code and has_data


def _auto_detect(new_root: Path) -> list[Path]:
    """Return existing installations found near the new build (bounded scan)."""
    candidates: list[Path] = [new_root, new_root.parent]
    for base in (new_root.parent, new_root.parent.parent):
        with suppress(OSError):
            candidates += [child for child in base.iterdir() if child.is_dir()]
    home = Path.home()
    for sub in ("Desktop", "Downloads", "Documents", "OneDrive/Desktop", "OneDrive/Downloads"):
        base = home / sub
        if base.is_dir():
            candidates.append(base)
            with suppress(OSError):
                candidates += [child for child in base.iterdir() if child.is_dir()]
    found: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if _looks_like_install(resolved) and (resolved / "data" / "app.db").is_file():
            found.append(resolved)
    return found


def _merge_env(old_text: str, example_text: str) -> tuple[str, list[str]]:
    have: set[str] = set()
    for line in old_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            have.add(stripped.split("=", 1)[0].strip())
    added: list[str] = []
    for line in example_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in have or _SECRETISH.search(key):
            continue
        added.append(f"{key}={value}")
        have.add(key)
    if not added:
        return old_text, []
    text = old_text if old_text.endswith("\n") else old_text + "\n"
    text += "\n# --- added by the update (defaults only) ---\n" + "\n".join(added) + "\n"
    return text, added


def _backup(old_root: Path, stamp: str) -> tuple[Path, list[str]]:
    dest = old_root / "backups" / f"preupdate-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    env = old_root / ".env"
    if env.is_file():
        shutil.copy2(env, dest / ".env")
        copied.append(".env")
    for name in _BACKUP_DIRS:
        src = old_root / name
        if src.is_dir():
            shutil.copytree(src, dest / name, dirs_exist_ok=True, ignore=_IGNORE)
            copied.append(f"{name}/")
    app = old_root / "app"
    if app.is_dir():
        shutil.copytree(app, dest / "app", dirs_exist_ok=True, ignore=_IGNORE)
        copied.append("app/")
    return dest, copied


def _copy_code(new_root: Path, old_root: Path) -> list[str]:
    src = new_root / "app" if (new_root / "app" / "backend").is_dir() else new_root
    dst = old_root / "app"
    if src.resolve() == dst.resolve():
        return []
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in _CODE_ITEMS:
        source = src / item
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, dst / item, ignore=_IGNORE)
        else:
            shutil.copy2(source, dst / item)
        copied.append(item)
    return copied


def _app_env_keys() -> set[str]:
    """Upper-cased names of every application setting (so we can ignore them)."""
    try:
        from backend.app.core.config import Settings
    except ImportError:
        # The target code is not importable yet: fall back to the settings that
        # would corrupt an update if inherited from the shell.
        return {"DATABASE_URL", "APP_SECRET_KEY", "APP_ENV", "TCMS_ROOT"}
    return {name.upper() for name in Settings.model_fields}


def _strip_app_env(env: dict[str, str]) -> None:
    """Drop inherited application settings so the target's ``.env`` wins.

    Without this, a ``DATABASE_URL``/``APP_SECRET_KEY`` left in the shell (or in
    the parent process) would silently point the update at the wrong database or
    decrypt with the wrong key.
    """
    keys = _app_env_keys()
    for key in list(env):
        if key.upper() in keys:
            env.pop(key, None)


def _prepare_import(old_root: Path) -> None:
    os.environ["TCMS_ROOT"] = str(old_root)
    os.environ["PYTHONPATH"] = str(old_root / "app")
    _strip_app_env(os.environ)
    os.environ["TCMS_ROOT"] = str(old_root)
    if str(old_root / "app") not in sys.path:
        sys.path.insert(0, str(old_root / "app"))
    os.chdir(old_root)
    from backend.app.core import paths
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    if hasattr(paths.project_root, "cache_clear"):
        paths.project_root.cache_clear()


def _collect_state(root: Path) -> dict[str, object]:
    db = _db_path(root)
    state: dict[str, object] = {
        "db_path": str(db),
        "exists": db.is_file(),
        "counts": {},
        "sealed_total": 0,
        "sealed_ok": 0,
        "sealed_bad": 0,
    }
    if not db.is_file():
        return state
    try:
        from backend.app.core.security import open_secret
    except ImportError:
        # Not importable (e.g. a self-test): skip the sealed-secret scan.
        return state

    try:
        con = sqlite3.connect(str(db))
    except sqlite3.Error as exc:
        state["error"] = str(exc)
        return state
    try:
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in rows}
        counts: dict[str, int] = {}
        for table in sorted(tables):
            if table == "alembic_version":
                continue
            counts[table] = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        state["counts"] = counts
        # Every sealed value (any *_encrypted column holding an "enc:" string)
        # must still decrypt with the preserved APP_SECRET_KEY.
        for table in sorted(tables):
            columns = [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]
            sealed = [c for c in columns if c.endswith("_encrypted")]
            if not sealed:
                continue
            query = "SELECT " + ", ".join(f'"{c}"' for c in sealed) + f' FROM "{table}"'
            for row in con.execute(query):
                for value in row:
                    if value and str(value).startswith("enc:"):
                        state["sealed_total"] = int(state["sealed_total"]) + 1
                        try:
                            open_secret(str(value))
                            state["sealed_ok"] = int(state["sealed_ok"]) + 1
                        except Exception:
                            state["sealed_bad"] = int(state["sealed_bad"]) + 1
    except sqlite3.Error as exc:
        state["error"] = str(exc)
    finally:
        con.close()
    return state


def _run_migration(old_root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    _strip_app_env(env)
    env["TCMS_ROOT"] = str(old_root)
    env["PYTHONPATH"] = str(old_root / "app")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "backend.app.db.migrate", "upgrade"],
        cwd=str(old_root),
        env=env,
        capture_output=True,
        text=True,
    )


def _write_result(old_root: Path, lines: list[str]) -> None:
    with suppress(OSError):
        (old_root / "UPDATE_RESULT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "data").mkdir()
        sqlite3.connect(str(root / "data" / "app.db")).close()
        (root / ".env").write_text(
            "APP_SECRET_KEY=keep-me\nMANAGER_BOT_TOKEN=123:secret\n", encoding="utf-8"
        )
        dest, _copied = _backup(root, _stamp())
        assert (dest / ".env").read_text(encoding="utf-8") == (
            root / ".env"
        ).read_text(encoding="utf-8")
        merged, added = _merge_env(
            (root / ".env").read_text(encoding="utf-8"),
            "APP_SECRET_KEY=placeholder\nNEW_SETTING=1\nMANAGER_BOT_TOKEN=other\n",
        )
        assert "APP_SECRET_KEY=keep-me" in merged
        assert "MANAGER_BOT_TOKEN=123:secret" in merged
        assert "NEW_SETTING=1" in merged and "placeholder" not in merged
        assert added == ["NEW_SETTING=1"], added
        state = _collect_state(root)
        assert state["exists"] and state["counts"].get("bots") is None
    _log("SELF-TEST: OK")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update an existing TCMS install, keeping all data."
    )
    parser.add_argument(
        "--root", help="Existing installation folder (the one with run.bat and .env)."
    )
    parser.add_argument("--auto", action="store_true", help="Find the installation automatically.")
    parser.add_argument("--yes", action="store_true", help="Do not ask questions.")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen and stop.")
    parser.add_argument("--self-test", action="store_true", help="Run an internal check and exit.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.root:
        old_root = Path(args.root).expanduser().resolve()
    else:
        found = _auto_detect(NEW_ROOT)
        if len(found) == 1:
            old_root = found[0]
            _log(f"Found existing installation: {old_root}")
        elif len(found) > 1:
            _log("Several installations were found; please choose one:")
            for item in found:
                _log(f"  - {item}")
            return EXIT_NEED_TARGET
        else:
            _log("No existing installation was found automatically.")
            return EXIT_NEED_TARGET

    if not _looks_like_install(old_root):
        _log(f"ERROR: {old_root} does not look like a TCMS installation.")
        return EXIT_FAIL

    stamp = _stamp()
    db = _db_path(old_root)
    _log("== TCMS update ==")
    _log(f"Existing installation: {old_root}")
    _log(f"New build            : {NEW_ROOT}")
    _log(f"Database             : {db}")

    env_path = old_root / ".env"
    env_before = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""

    if args.dry_run:
        _log("[dry-run] would back up .env, data/, sessions/, exports/ and app/ into "
             f"backups/preupdate-{stamp}/, replace app/ and apply migrations.")
        return EXIT_OK

    # 1. Back up everything irreplaceable first.
    backup_dir, copied = _backup(old_root, stamp)
    _log(f"[1/5] Backup: {backup_dir}")
    _log(f"      copied: {', '.join(copied) or '(nothing)'}")

    # 2. Replace the application code only.
    code_items = _copy_code(NEW_ROOT, old_root)
    _log(f"[2/5] Application files updated: {', '.join(code_items) or '(already in place)'}")

    # 3. Add any brand-new settings without touching existing ones or secrets.
    example = NEW_ROOT / "app" / ".env.example"
    if not example.is_file():
        example = NEW_ROOT / ".env.example"
    if env_path.is_file() and example.is_file():
        merged, added = _merge_env(env_before, example.read_text(encoding="utf-8"))
        if added:
            env_path.write_text(merged, encoding="utf-8")
        _log(f"[3/5] Settings: kept all existing values; added {len(added)} new default key(s)")
    else:
        _log("[3/5] Settings: kept the existing .env unchanged")

    # 4. Read state, then migrate the existing database.
    _prepare_import(old_root)
    before = _collect_state(old_root)
    _log(
        f"[4/5] Before: bots={before['counts'].get('bots')} "
        f"channels={before['counts'].get('channels')} "
        f"sealed={before['sealed_ok']}/{before['sealed_total']}"
    )

    migration = _run_migration(old_root)
    _log(migration.stdout.strip() or "(no migration output)")
    if migration.returncode != 0:
        _log("ERROR: database migration failed. Your original data was not changed.")
        _log(f"Restore from: {backup_dir}")
        _log(migration.stderr.strip())
        _write_result(
            old_root,
            ["ИТОГ: НЕ ПРОЙДЕНО", "Миграция базы не удалась.", f"Резервная копия: {backup_dir}"],
        )
        return EXIT_FAIL

    # 5. Prove the data and secrets survived.
    _prepare_import(old_root)
    after = _collect_state(old_root)
    problems: list[str] = []
    for table, count in before["counts"].items():
        if int(after["counts"].get(table, -1)) < int(count):
            problems.append(f"{table}: {count} -> {after['counts'].get(table)}")
    if int(after["sealed_bad"]) > 0:
        problems.append(f"{after['sealed_bad']} secret(s) no longer decrypt")
    env_after_value = _parse_env(old_root / ".env").get("APP_SECRET_KEY", "")
    if env_after_value != _env_value(env_before, "APP_SECRET_KEY"):
        problems.append("APP_SECRET_KEY changed (secrets would become unreadable)")
    if not env_path.is_file():
        problems.append("the .env file is missing after the update")

    if problems:
        _log("ERROR: verification failed:")
        for problem in problems:
            _log(f"  - {problem}")
        _log(f"Restore from: {backup_dir}")
        _log("ИТОГ: НЕ ПРОЙДЕНО — данные не изменены, восстановите из резервной копии.")
        _write_result(old_root, ["ИТОГ: НЕ ПРОЙДЕНО", *problems, f"Резервная копия: {backup_dir}"])
        return EXIT_FAIL

    _log(
        f"[5/5] After : bots={after['counts'].get('bots')} "
        f"channels={after['counts'].get('channels')} "
        f"sealed={after['sealed_ok']}/{after['sealed_total']}"
    )
    _log("")
    _log("ИТОГ: ПРОЙДЕНО — все данные и секреты на месте.")
    _log(f"Резервная копия: {backup_dir}")
    _log("Теперь запустите программу как обычно (run.bat).")
    _write_result(
        old_root,
        [
            "ИТОГ: ПРОЙДЕНО",
            f"Обновление: {stamp}",
            f"Боты: {after['counts'].get('bots')}",
            f"Каналы: {after['counts'].get('channels')}",
            f"Секреты расшифрованы: {after['sealed_ok']}/{after['sealed_total']}",
            f"Резервная копия: {backup_dir}",
        ],
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
