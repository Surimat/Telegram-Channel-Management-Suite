"""v1.1 multi-format session import tests (local artifacts, fake provider).

Covers the format detectors, the companion-JSON secret handling and the durable
import path — all against the deterministic fake provider (no network, no real
session). The raw StringSession value is asserted to never surface in a result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import SessionInvalidError
from backend.app.providers.fake_session import FakeAuthScenario, FakeSessionProvider
from backend.app.services.session_import import (
    FORMAT_SESSION,
    FORMAT_SESSION_JSON,
    FORMAT_STRING_SESSION,
    FORMAT_TDATA,
    FORMAT_UNKNOWN,
    STATE_DAMAGED,
    STATE_UNKNOWN,
    STATE_VALID,
    SessionImportRequest,
    _read_companion_json,
    detect_format,
    select_provider,
)
from backend.app.services.session_service import SessionService, SessionServiceError

SQLITE_MAGIC = b"SQLite format 3\x00" + b"\x00" * 64
VALID_STRING = "1" + "A" * 40
STRING_SECRET = "1" + "B" * 48


def factory_for(provider: FakeSessionProvider):
    def _factory(
        *,
        api_id="",
        api_hash="",
        session_path=None,
        provider_name="auto",
        settings=None,
        proxy=None,
    ):
        provider._session_path = session_path
        provider._api_id = api_id
        provider._api_hash = api_hash
        return provider

    return _factory


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


# --- detection ---------------------------------------------------------------


def test_detect_plain_session_file(tmp_path: Path) -> None:
    path = tmp_path / "account.session"
    path.write_bytes(SQLITE_MAGIC)
    result = detect_format(SessionImportRequest(path=path))
    assert result.format == FORMAT_SESSION
    assert result.state == STATE_VALID
    assert result.available is True


def test_detect_session_with_companion_json(tmp_path: Path) -> None:
    path = tmp_path / "account.session"
    path.write_bytes(SQLITE_MAGIC)
    (tmp_path / "account.json").write_text(json.dumps({"api_id": "12345"}))
    result = detect_format(SessionImportRequest(path=path))
    assert result.format == FORMAT_SESSION_JSON
    assert result.state == STATE_VALID


def test_damaged_session_reports_state(tmp_path: Path) -> None:
    path = tmp_path / "broken.session"
    path.write_bytes(b"not-a-sqlite-file")
    result = detect_format(SessionImportRequest(path=path))
    assert result.format == FORMAT_SESSION
    assert result.state == STATE_DAMAGED
    assert result.how_to_fix


def test_detect_string_session() -> None:
    result = detect_format(SessionImportRequest(string_session=VALID_STRING))
    assert result.format == FORMAT_STRING_SESSION
    assert result.state == STATE_VALID


def test_detect_bad_string_session_is_unknown() -> None:
    # A value that is not a valid StringSession is not claimed as one; the user
    # gets an honest "format not recognised" instead of a false positive.
    result = detect_format(SessionImportRequest(string_session="not-a-session"))
    assert result.format == FORMAT_UNKNOWN


def test_detect_tdata_without_converter_is_honest(tmp_path: Path) -> None:
    tdata = tmp_path / "tdata"
    tdata.mkdir()
    (tdata / "key_datas").write_bytes(b"x")
    result = detect_format(SessionImportRequest(path=tdata))
    assert result.format == FORMAT_TDATA
    assert result.available is False
    assert result.state == STATE_UNKNOWN


def test_detect_unknown_artifact(tmp_path: Path) -> None:
    path = tmp_path / "random.bin"
    path.write_bytes(b"\x00\x01\x02")
    result = detect_format(SessionImportRequest(path=path))
    assert result.format == FORMAT_UNKNOWN


def test_companion_json_never_reads_secret_keys(tmp_path: Path) -> None:
    companion = tmp_path / "meta.json"
    companion.write_text(
        json.dumps(
            {
                "api_id": "777",
                "api_hash": "deadbeef",
                "session_string": STRING_SECRET,
                "password": "hunter2",
                "phone": "+79991234567",
            }
        )
    )
    meta = _read_companion_json(companion)
    assert meta["api_id"] == "777"
    assert "session_string" not in meta
    assert "password" not in meta
    # api_hash is read (it is needed to connect) but is never surfaced by the API.
    assert meta["api_hash"] == "deadbeef"


def test_select_provider_prefers_companion_variant(tmp_path: Path) -> None:
    path = tmp_path / "account.session"
    path.write_bytes(SQLITE_MAGIC)
    (tmp_path / "account.json").write_text("{}")
    provider = select_provider(SessionImportRequest(path=path))
    assert provider is not None
    assert provider.format == FORMAT_SESSION_JSON


# --- import ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_session_file(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "existing.session"
    source.write_bytes(SQLITE_MAGIC)
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        account, result = await svc.import_artifact(
            SessionImportRequest(
                path=source, api_id="123", api_hash="hash", phone="+79991234567"
            )
        )
        assert account.status.value == "online"
        assert result.format == FORMAT_SESSION
        assert (dir_ / f"{account.session_ref}.session").is_file()
        # Secrets are sealed, never stored in plaintext columns.
        assert account.api_hash_encrypted.startswith("enc:")
        assert account.phone_encrypted.startswith("enc:")


@pytest.mark.asyncio
async def test_import_string_session_materialises_file(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        account, result = await svc.import_artifact(
            SessionImportRequest(
                string_session=STRING_SECRET, api_id="123", api_hash="hash"
            )
        )
        assert result.format == FORMAT_STRING_SESSION
        assert (dir_ / f"{account.session_ref}.session").is_file()
        # The raw StringSession value must not appear in the result message/notes.
        joined = " ".join(result.notes) + result.message
        assert STRING_SECRET not in joined


@pytest.mark.asyncio
async def test_import_requires_api_id(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "a.session"
    source.write_bytes(SQLITE_MAGIC)
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        with pytest.raises(SessionServiceError):
            await svc.import_artifact(SessionImportRequest(path=source, api_hash="h"))


@pytest.mark.asyncio
async def test_import_unknown_artifact_rejected(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    path = tmp_path / "x.bin"
    path.write_bytes(b"\x00\x01")
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        with pytest.raises(SessionServiceError):
            await svc.import_artifact(
                SessionImportRequest(path=path, api_id="1", api_hash="h")
            )


@pytest.mark.asyncio
async def test_import_bad_session_rolls_back(tmp_path: Path) -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(health_error=SessionInvalidError())
    )
    source = tmp_path / "bad.session"
    source.write_bytes(SQLITE_MAGIC)
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        with pytest.raises(SessionServiceError):
            await svc.import_artifact(
                SessionImportRequest(path=source, api_id="1", api_hash="h")
            )
        assert await svc.list_accounts() == []
        assert list(dir_.glob("*.session")) == []
