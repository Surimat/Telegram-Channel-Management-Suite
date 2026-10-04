"""Diagnostics + redaction tests (product polish).

Covers:
* redaction of every secret kind (configured values, bot tokens, api_hash,
  session strings, phones, long hex);
* the safety scan;
* report generation in JSON/TXT/ZIP with no secrets and no database contents;
* status aggregation for every subsystem;
* the Diagnostics API (status, actions, report download);
* safe maintenance actions (scheduler restart, cleanup) never touching user data.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from backend.app.core.redaction import (
    REDACTED,
    redact_and_verify,
    redact_mapping,
    redact_text,
    scan,
)

# --- redaction ---------------------------------------------------------------

_BOT_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
_API_HASH = "0123456789abcdef0123456789abcdef"
_SESSION = "1" + "A" * 60
_PHONE = "+79991234567"


@pytest.mark.parametrize(
    "text",
    [
        f"token={_BOT_TOKEN}",
        f"api_hash={_API_HASH}",
        f"session={_SESSION}",
        f"phone {_PHONE}",
        "secret=supersecretvalue",
    ],
)
def test_redact_text_masks_secret_kinds(text: str) -> None:
    redacted = redact_text(text, extra_secrets=["supersecretvalue"])
    assert REDACTED in redacted
    assert _BOT_TOKEN not in redacted
    assert _API_HASH not in redacted
    assert _SESSION not in redacted
    assert _PHONE not in redacted
    assert "supersecretvalue" not in redacted


def test_redact_text_masks_registered_secret() -> None:
    redacted = redact_text("value is TOPSECRETVALUE123 here", extra_secrets=["TOPSECRETVALUE123"])
    assert "TOPSECRETVALUE123" not in redacted
    assert REDACTED in redacted


def test_scan_flags_secrets_and_clean_text() -> None:
    assert scan(f"token={_BOT_TOKEN}")
    assert scan(f"api_hash={_API_HASH}")
    assert scan("just a normal sentence about channels") == []


def test_redact_mapping_drops_forbidden_keys_and_redacts_values() -> None:
    payload = {
        "token": _BOT_TOKEN,
        "api_hash": _API_HASH,
        "username": "mybot",
        "note": f"uses {_BOT_TOKEN}",
        "nested": {"phone": _PHONE, "title": "Канал"},
    }
    result = redact_mapping(payload)
    assert "token" not in result
    assert "api_hash" not in result
    assert result["username"] == "mybot"
    assert _BOT_TOKEN not in json.dumps(result)
    assert "phone" not in result["nested"]
    assert result["nested"]["title"] == "Канал"


def test_redact_and_verify_is_clean_after_redaction() -> None:
    result = redact_and_verify({"token": _BOT_TOKEN, "note": f"api_hash={_API_HASH}"})
    assert result.clean is True
    assert result.findings == []


# --- report generation -------------------------------------------------------


@pytest.fixture(autouse=True)
async def _models() -> None:
    from backend.app.db.session import init_models

    await init_models()


async def test_collect_reports_every_subsystem() -> None:
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import DiagnosticsService

    async with session_scope() as session:
        report = await DiagnosticsService(session).collect()
    keys = {item.key for item in report.items}
    expected = {
        "application",
        "database",
        "telegram_api",
        "manager_bot",
        "managed_bots",
        "sessions",
        "channels",
        "audience",
        "reactions",
        "invites",
        "ai",
        "scheduler",
        "storage",
        "portable_runtime",
    }
    assert expected.issubset(keys)
    assert report.version
    assert report.overall in {"ok", "warning", "error"}
    for item in report.items:
        assert item.status in {"ok", "warning", "error", "not_configured", "unknown"}
        assert item.status_label
        assert item.meaning


async def test_report_payload_contains_no_secrets_or_db_contents() -> None:
    from backend.app.core.config import get_settings
    from backend.app.core.security import seal_secret
    from backend.app.db.models.bot import Bot, BotKind
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import DiagnosticsService

    settings = get_settings()
    sealed = seal_secret(_BOT_TOKEN, settings)
    async with session_scope() as session:
        session.add(
            Bot(
                kind=BotKind.MANAGER,
                username="manager_bot",
                title="Manager",
                token_encrypted=sealed,
            )
        )
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="123456",
                phone_masked="+7999***4567",
            )
        )
    async with session_scope() as session:
        content, filename, media_type = await DiagnosticsService(session).build_report("json")
    assert filename.endswith(".json")
    assert media_type == "application/json"
    text = content.decode("utf-8")
    # No secrets / PII / database contents.
    assert _BOT_TOKEN not in text
    assert "token_encrypted" not in text
    assert "api_hash" not in text
    assert _PHONE not in text
    assert "phone_masked" not in text
    assert "password" not in text
    # But the report is useful: it names the manager bot and version.
    payload = json.loads(text)
    assert payload["application"]["version"]
    assert payload["telegram"]["bots"][0]["username"] == "manager_bot"
    assert payload["report"]["redaction"]


async def test_report_txt_and_zip_are_redacted() -> None:
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import DiagnosticsService

    async with session_scope() as session:
        txt, name_txt, mime_txt = await DiagnosticsService(session).build_report("txt")
        zipped, name_zip, mime_zip = await DiagnosticsService(session).build_report("zip")
    assert name_txt.endswith(".txt") and mime_txt == "text/plain"
    assert "Отчёт безопасно очищен от секретов." in txt.decode("utf-8")
    assert name_zip.endswith(".zip") and mime_zip == "application/zip"
    with zipfile.ZipFile(__import__("io").BytesIO(zipped)) as archive:
        names = set(archive.namelist())
        assert {"report.json", "report.txt", "README.txt"}.issubset(names)
        for member in names:
            assert _BOT_TOKEN not in archive.read(member).decode("utf-8")


async def test_report_unknown_format_rejected() -> None:
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import DiagnosticsError, DiagnosticsService

    async with session_scope() as session:
        with pytest.raises(DiagnosticsError):
            await DiagnosticsService(session).build_report("pdf")


async def test_cleanup_action_resets_stuck_jobs_without_deleting_data() -> None:
    from backend.app.db.models.job import Job, JobStatus
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import (
        ACTION_CLEANUP_JOBS,
        DiagnosticsService,
    )

    async with session_scope() as session:
        stuck = Job(kind="scan", status=JobStatus.RUNNING)
        done = Job(kind="scan", status=JobStatus.DONE)
        session.add_all([stuck, done])
    async with session_scope() as session:
        result = await DiagnosticsService(session).run_action(ACTION_CLEANUP_JOBS)
    assert result.ok is True
    assert result.affected >= 1
    async with session_scope() as session:
        from backend.app.db.repositories.jobs import JobRepository

        repo = JobRepository(session)
        still_stuck = await repo.list_stuck_running()
        counts = await repo.status_counts()
    assert still_stuck == []
    # The finished job is preserved (user data / history is never deleted).
    assert counts.get("done", 0) == 1


# --- API ---------------------------------------------------------------------


@pytest.fixture
async def diagnostics_client():
    from httpx import ASGITransport, AsyncClient

    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_diagnostics_api_status(diagnostics_client) -> None:
    resp = await diagnostics_client.get("/api/v1/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"]
    assert body["overall"]
    assert len(body["items"]) >= 14
    for item in body["items"]:
        assert item["status_label"]


async def test_diagnostics_api_actions_and_cleanup(diagnostics_client) -> None:
    actions = await diagnostics_client.get("/api/v1/diagnostics/actions")
    assert actions.status_code == 200
    keys = {a["key"] for a in actions.json()}
    assert "restart_scheduler" in keys
    assert "cleanup_jobs" in keys
    # Non-destructive actions need no confirmation; cleanup does.
    cleanup = next(a for a in actions.json() if a["key"] == "cleanup_jobs")
    assert cleanup["requires_confirmation"] is True
    assert cleanup["destructive"] is False

    run = await diagnostics_client.post("/api/v1/diagnostics/actions/cleanup_jobs")
    assert run.status_code == 200
    assert run.json()["ok"] is True


async def test_diagnostics_api_report_download_has_no_secrets(diagnostics_client) -> None:
    resp = await diagnostics_client.get("/api/v1/diagnostics/report?format=json")
    assert resp.status_code == 200
    assert resp.headers["x-diagnostics-redacted"] == "true"
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.text
    assert _BOT_TOKEN not in text
    assert "api_hash" not in text
    payload = json.loads(text)
    assert payload["report"]["kind"] == "diagnostics"


async def test_diagnostics_api_report_zip(diagnostics_client) -> None:
    resp = await diagnostics_client.get("/api/v1/diagnostics/report?format=zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(__import__("io").BytesIO(resp.content)) as archive:
        assert "report.json" in archive.namelist()


async def test_diagnostics_api_rejects_bad_format(diagnostics_client) -> None:
    resp = await diagnostics_client.get("/api/v1/diagnostics/report?format=pdf")
    assert resp.status_code == 422


# --- graceful degradation ----------------------------------------------------
# The Diagnostics page is exactly where a user is sent when something is broken,
# so a failing check (e.g. a corrupt/unreadable database) must degrade that row
# instead of raising and blanking the whole page.


async def test_collect_degrades_when_a_check_fails(monkeypatch) -> None:
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import DiagnosticsService

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("file is not a database")

    monkeypatch.setattr(DiagnosticsService, "_managed_bots_item", _boom)
    async with session_scope() as session:
        report = await DiagnosticsService(session).collect()
    row = next(i for i in report.items if i.key == "managed_bots")
    assert row.status == "error"
    assert row.title  # still has a friendly title
    assert row.meaning
    assert row.how_to_fix
    # The rest of the page still renders.
    assert len(report.items) >= 14
    assert report.overall in {"warning", "error"}


async def test_collect_degrades_when_database_check_raises(monkeypatch) -> None:
    from backend.app.db.session import session_scope
    from backend.app.services import system_service
    from backend.app.services.diagnostics_service import DiagnosticsService

    async def _boom(self):
        raise RuntimeError("file is not a database")

    monkeypatch.setattr(system_service.SystemService, "database_check", _boom)
    async with session_scope() as session:
        report = await DiagnosticsService(session).collect()
    row = next(i for i in report.items if i.key == "database")
    assert row.status == "error"
    assert "баз" in row.meaning.lower()


async def test_report_payload_survives_db_failure(monkeypatch) -> None:
    from backend.app.db.session import session_scope
    from backend.app.services.diagnostics_service import DiagnosticsService

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("file is not a database")

    monkeypatch.setattr(DiagnosticsService, "_bots_payload", _boom)
    monkeypatch.setattr(DiagnosticsService, "_queue_payload", _boom)
    async with session_scope() as session:
        payload = await DiagnosticsService(session).build_report_payload()
    # Sections that failed fall back to safe empty values, not a crash.
    assert payload["telegram"]["bots"] == []
    assert payload["queue"] == {"unavailable": True}
    # And the report is still produced.
    assert payload["report"]["kind"] == "diagnostics"
