"""Guard the one-step, data-preserving portable update (D-131).

The non-programmer owner must be able to update an existing installation with a
single double-click (``UPDATE_EXISTING.bat``) and keep **all** settings and
secrets: the manager token, the created bots, channel memberships, MTProto
sessions and the ``APP_SECRET_KEY`` that decrypts them.

These tests build a realistic old installation (a real migrated database with
sealed bot tokens), run the real updater against it in a subprocess, and prove:

1. the database rows and every sealed secret survive and still decrypt;
2. ``.env`` keeps its existing values (including ``APP_SECRET_KEY`` and the
   manager token) and only *adds* missing defaults — never a secret-looking key;
3. pending migrations are applied to the existing database;
4. a timestamped backup of ``.env``/``data``/``sessions``/``app`` is written;
5. a second run is a safe no-op (idempotent);
6. the updater and its launcher are bundled into the portable build.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UPDATER = ROOT / "scripts" / "update_existing.py"
LAUNCHER = ROOT / "portable" / "UPDATE_EXISTING.bat"
BUILD = ROOT / "scripts" / "build_portable.sh"

# The revision just before the Setup Wizard migration: forces a real migration.
OLD_HEAD = "f6a7b8c9d0e1"
# The Setup Wizard migration, then the migration that retires the promotion
# wizard table — the updater must apply both to reach the current head.
NEW_HEAD = "b8c9d0e1f2a3"
NEW_HEAD_TABLE = "setup_wizard_steps"

MANAGER_TOKEN = "111111:MANAGER-TOKEN-ORIGINAL"
WORKER_TOKEN = "222222:WORKER-TOKEN-ORIGINAL"
SECRET_KEY = "owner-secret-key-0123456789-abcdefghij"

# Builds an old installation: copies the code, writes a real ``.env``, migrates
# the DB to ``OLD_HEAD`` and inserts fake rows (with sealed secrets) via raw SQL.
_PREP = '''
import os, sqlite3, sys, uuid
from pathlib import Path

old = Path(sys.argv[1]).resolve()
old_head = sys.argv[2]
src = Path(sys.argv[3]).resolve()
(old / "data").mkdir(parents=True, exist_ok=True)
(old / "sessions").mkdir(exist_ok=True)

os.environ["TCMS_ROOT"] = str(old)
os.chdir(old)

# Copy the application code into <old>/app (a real portable layout).
import shutil
app = old / "app"
if app.exists():
    shutil.rmtree(app)
app.mkdir()
shutil.copytree(src / "backend", app / "backend",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copytree(src / "migrations", app / "migrations",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copy2(src / "alembic.ini", app / "alembic.ini")
shutil.copy2(src / ".env.example", app / ".env.example")

(old / ".env").write_text(
    "APP_ENV=production\\n"
    "APP_SECRET_KEY=" + sys.argv[4] + "\\n"
    "DATABASE_URL=sqlite+aiosqlite:///./data/app.db\\n"
    "MANAGER_BOT_TOKEN=" + sys.argv[5] + "\\n"
    "MANAGER_BOT_ADMIN_IDS=42\\n"
    "TELEGRAM_API_ID=12345\\n"
    "TELEGRAM_API_HASH=deadbeefhash\\n"
    "APP_LANGUAGE=ru\\n",
    encoding="utf-8",
)
# A session file (must be preserved, never read).
(old / "sessions" / "abc123.session").write_bytes(b"session-bytes")

sys.path.insert(0, str(old / "app"))
# Ignore any application settings inherited from the test shell (pytest sets a
# DATABASE_URL/APP_SECRET_KEY): the target's own .env must win.
from backend.app.core.config import Settings
for _k in list(os.environ):
    if _k.upper() in {n.upper() for n in Settings.model_fields}:
        del os.environ[_k]
# Optional: seal secrets with a DIFFERENT key than the one in .env (simulates a
# corrupted/regenerated .env whose secrets no longer decrypt).
if len(sys.argv) > 7 and sys.argv[7]:
    os.environ["APP_SECRET_KEY"] = sys.argv[7]
from alembic import command
from backend.app.core.config import reset_settings_cache
from backend.app.core.security import seal_secret
from backend.app.db.migrate import _alembic_config

reset_settings_cache()
command.upgrade(_alembic_config(), old_head)

con = sqlite3.connect(str(old / "data" / "app.db"))
def insert(table, **overrides):
    info = {r[1]: r for r in con.execute('PRAGMA table_info("%s")' % table)}
    values = {}
    for col, meta in info.items():
        if col in overrides:
            values[col] = overrides[col]
        elif meta[5]:  # pk
            values[col] = uuid.uuid4().hex
        elif meta[3] and meta[4] is None:  # notnull without default
            ctype = (meta[2] or "").upper()
            values[col] = 0 if ("INT" in ctype or "BOOL" in ctype) else ""
    names = ", ".join('"%s"' % c for c in values)
    marks = ", ".join("?" for _ in values)
    con.execute('INSERT INTO "%s" (%s) VALUES (%s)' % (table, names, marks), list(values.values()))

insert("bots", title="manager-bot", kind="manager", token_encrypted=seal_secret(sys.argv[5]))
insert("bots", title="worker-1", kind="managed", token_encrypted=seal_secret(sys.argv[6]))
insert("channels", title="my-channel", username="my_channel")
insert("job_queue", kind="reaction", status="pending")
insert("owner_identities", verifier="pbkdf2_sha256$200000$salt$hash", sync_salt="syncsalt123")
insert("settings", key="language", value="ru")
con.commit()
con.close()
print("old install ready")
'''


def _run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(ROOT))


@pytest.fixture
def old_install(tmp_path: Path) -> Path:
    return _make_old_install(tmp_path, seal_key="")


def _make_old_install(tmp_path: Path, *, seal_key: str) -> Path:
    old = tmp_path / "old"
    prep = tmp_path / "prep_old.py"
    prep.write_text(_PREP, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    result = _run(
        [
            sys.executable,
            str(prep),
            str(old),
            OLD_HEAD,
            str(ROOT),
            SECRET_KEY,
            MANAGER_TOKEN,
            WORKER_TOKEN,
            seal_key,
        ],
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return old


def _update(old: Path) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(UPDATER), "--root", str(old), "--yes"])


def _decrypt_tokens(old: Path) -> list[str]:
    """Independently decrypt the sealed bot tokens with the preserved key."""
    code = (
        "import sqlite3,sys;"
        f"sys.path.insert(0,{str(old / 'app')!r});"
        "from backend.app.core.security import open_secret;"
        f"con=sqlite3.connect({str(old / 'data' / 'app.db')!r});"
        "print('\\n'.join(open_secret(r[0]) for r in con.execute("
        "'select token_encrypted from bots order by id') if r[0]))"
    )
    env = dict(os.environ)
    env["TCMS_ROOT"] = str(old)
    env["PYTHONPATH"] = str(old / "app")
    env["APP_SECRET_KEY"] = SECRET_KEY
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(old)
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_update_preserves_data_and_secrets(old_install: Path) -> None:
    env_before = (old_install / ".env").read_text(encoding="utf-8")
    result = _update(old_install)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ИТОГ: ПРОЙДЕНО" in result.stdout

    # 1. Data rows are intact.
    con = sqlite3.connect(str(old_install / "data" / "app.db"))
    try:
        assert con.execute("select count(*) from bots").fetchone()[0] == 2
        assert con.execute("select count(*) from channels").fetchone()[0] == 1
        assert con.execute("select count(*) from job_queue").fetchone()[0] == 1
        assert con.execute("select count(*) from owner_identities").fetchone()[0] == 1
        # 3. Pending migration was applied to the existing database.
        assert con.execute("select version_num from alembic_version").fetchone()[0] == NEW_HEAD
        assert con.execute(
            "select 1 from sqlite_master where name=?", (NEW_HEAD_TABLE,)
        ).fetchone()
    finally:
        con.close()

    # 2. Every sealed secret still decrypts to the original value.
    assert sorted(_decrypt_tokens(old_install)) == sorted([MANAGER_TOKEN, WORKER_TOKEN])

    # 4. .env keeps existing values; only defaults are added.
    env_after = (old_install / ".env").read_text(encoding="utf-8")
    for line in ("APP_SECRET_KEY=" + SECRET_KEY, "MANAGER_BOT_TOKEN=" + MANAGER_TOKEN,
                 "TELEGRAM_API_HASH=deadbeefhash", "APP_LANGUAGE=ru"):
        assert line in env_after, line
    # The example's placeholder secret is never written into the real .env.
    assert "change-me-please-generate-a-long-random-value" not in env_after
    assert env_after.count("APP_SECRET_KEY=") == env_before.count("APP_SECRET_KEY=") == 1

    # 5. A timestamped backup exists with the irreplaceable artefacts.
    backups = sorted((old_install / "backups").glob("preupdate-*"))
    assert backups, "no preupdate backup written"
    latest = backups[-1]
    assert (latest / ".env").read_text(encoding="utf-8") == env_before
    assert (latest / "data" / "app.db").is_file()
    assert (latest / "sessions" / "abc123.session").is_file()
    assert (latest / "app" / "backend").is_dir()

    # The owner-facing result file reports success.
    assert "ИТОГ: ПРОЙДЕНО" in (old_install / "UPDATE_RESULT.txt").read_text(encoding="utf-8")


def test_update_is_idempotent(old_install: Path) -> None:
    assert _update(old_install).returncode == 0
    first_env = (old_install / ".env").read_text(encoding="utf-8")
    second = _update(old_install)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "ИТОГ: ПРОЙДЕНО" in second.stdout
    # No duplicate keys, no data loss on a second run.
    assert (old_install / ".env").read_text(encoding="utf-8").count("APP_SECRET_KEY=") == 1
    assert (old_install / ".env").read_text(encoding="utf-8").count("MANAGER_BOT_TOKEN=") == 1
    assert (old_install / ".env").read_text(encoding="utf-8") == first_env
    con = sqlite3.connect(str(old_install / "data" / "app.db"))
    try:
        assert con.execute("select count(*) from bots").fetchone()[0] == 2
        assert con.execute("select version_num from alembic_version").fetchone()[0] == NEW_HEAD
    finally:
        con.close()


def test_env_merge_keeps_secrets_and_adds_defaults() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("update_existing", UPDATER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    old = "APP_SECRET_KEY=keep\nMANAGER_BOT_TOKEN=123:real\nAPP_LANGUAGE=ru\n"
    example = (
        "APP_SECRET_KEY=change-me-please\n"
        "MANAGER_BOT_TOKEN=\n"
        "APP_LANGUAGE=en\n"
        "BRAND_NEW_SETTING=42\n"
    )
    merged, added = module._merge_env(old, example)
    assert "APP_SECRET_KEY=keep" in merged
    assert "MANAGER_BOT_TOKEN=123:real" in merged
    assert "APP_LANGUAGE=ru" in merged and "APP_LANGUAGE=en" not in merged
    assert "BRAND_NEW_SETTING=42" in merged
    assert "change-me-please" not in merged
    assert added == ["BRAND_NEW_SETTING=42"]


def test_update_aborts_and_keeps_data_when_a_secret_cannot_be_decrypted(tmp_path: Path) -> None:
    # Secrets were sealed with a different key than the one now in .env.
    old = _make_old_install(tmp_path, seal_key="a-completely-different-secret-key-9999")
    before_rows = sqlite3.connect(str(old / "data" / "app.db")).execute(
        "select count(*) from bots"
    ).fetchone()[0]

    result = _update(old)
    assert result.returncode == 1, result.stdout
    assert "ИТОГ: НЕ ПРОЙДЕНО" in result.stdout
    # The failure is reported, data is untouched and the backup is named.
    assert "no longer decrypt" in result.stdout
    assert "preupdate-" in result.stdout
    con = sqlite3.connect(str(old / "data" / "app.db"))
    try:
        assert con.execute("select count(*) from bots").fetchone()[0] == before_rows
    finally:
        con.close()
    backups = sorted((old / "backups").glob("preupdate-*"))
    assert backups and (backups[-1] / "data" / "app.db").is_file()
    assert "ИТОГ: НЕ ПРОЙДЕНО" in (old / "UPDATE_RESULT.txt").read_text(encoding="utf-8")


def test_updater_is_bundled_in_the_portable_build() -> None:
    assert UPDATER.is_file() and LAUNCHER.is_file()
    launcher = LAUNCHER.read_text(encoding="utf-8")
    assert "app\\scripts\\update_existing.py" in launcher
    assert "--auto" in launcher
    build = BUILD.read_text(encoding="utf-8")
    assert "update_existing.py" in build
    assert "UPDATE_EXISTING.bat" in build


def test_updater_self_test_passes() -> None:
    result = _run([sys.executable, str(UPDATER), "--self-test"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELF-TEST: OK" in result.stdout
