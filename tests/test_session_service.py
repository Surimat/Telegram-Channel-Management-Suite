"""SessionService tests against a temporary SQLite DB (PHASE 4).

Uses the deterministic fake provider, so no Telegram account or network is
needed. Covers the auth state machine, import, health, enable/disable, delete,
logout and restart recovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.db.models.session import SessionStatus
from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import FloodWaitError, SessionInvalidError
from backend.app.providers.fake_session import (
    DEFAULT_CODE,
    DEFAULT_PASSWORD,
    FakeAuthScenario,
    FakeSessionProvider,
)
from backend.app.services.session_service import SessionService, SessionServiceError


def factory_for(provider: FakeSessionProvider):
    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        provider._session_path = session_path
        provider._api_id = api_id
        provider._api_hash = api_hash
        return provider

    return _factory


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


# --- full happy path ---------------------------------------------------------


@pytest.mark.asyncio
async def test_start_code_finish_auth(tmp_path: Path) -> None:
    provider = FakeSessionProvider(scenario=FakeAuthScenario(authorized=False))
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        started = await svc.start_auth(api_id="123456", api_hash="hash", phone="+79991234567")
        assert started.next_step == "code"
        assert started.phone_masked == "+7999***4567"
        assert started.account_id

        step = await svc.submit_code(started.account_id, DEFAULT_CODE)
        assert step.done is True
        assert step.identity is not None

        account = await svc.get(started.account_id)
        assert account is not None
        assert account.status == SessionStatus.ONLINE
        assert account.telegram_user_id == 1000001
        assert account.username == "fake_user"
        # No plaintext phone/secret leaks into non-secret columns.
        assert account.phone_masked == "+7999***4567"
        assert account.phone_encrypted.startswith("enc:")
        assert account.api_hash_encrypted.startswith("enc:")


@pytest.mark.asyncio
async def test_two_factor_flow(tmp_path: Path) -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(authorized=False, requires_2fa=True)
    )
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        started = await svc.start_auth(api_id="1", api_hash="h", phone="+79990000000")
        step = await svc.submit_code(started.account_id, DEFAULT_CODE)
        assert step.next_step == "password"
        assert step.done is False

        done = await svc.submit_password(started.account_id, DEFAULT_PASSWORD)
        assert done.done is True
        account = await svc.get(started.account_id)
        assert account.status == SessionStatus.ONLINE


@pytest.mark.asyncio
async def test_wrong_code_sets_error_and_keeps_account(tmp_path: Path) -> None:
    provider = FakeSessionProvider(scenario=FakeAuthScenario(authorized=False))
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        started = await svc.start_auth(api_id="1", api_hash="h", phone="+79990000001")
        with pytest.raises(SessionServiceError) as exc:
            await svc.submit_code(started.account_id, "00000")
        assert exc.value.how_to_fix
        account = await svc.get(started.account_id)
        assert account is not None
        assert account.last_error


@pytest.mark.asyncio
async def test_flood_wait_sets_status(tmp_path: Path) -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(authorized=False, send_code_error=FloodWaitError(99))
    )
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        with pytest.raises(SessionServiceError):
            await svc.start_auth(api_id="1", api_hash="h", phone="+79990000002")
        accounts = await svc.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].status == SessionStatus.FLOOD_WAIT
        assert "99" in accounts[0].status_message


# --- validation --------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_auth_rejects_bad_api_id(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        with pytest.raises(SessionServiceError):
            await svc.start_auth(api_id="abc", api_hash="h", phone="+7999")


@pytest.mark.asyncio
async def test_start_auth_rejects_missing_phone(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        with pytest.raises(SessionServiceError):
            await svc.start_auth(api_id="123", api_hash="h", phone="")


# --- import ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_valid_session(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "existing.session"
    source.write_bytes(b"PRETEND-SESSION-BYTES")
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        account = await svc.import_session(
            api_id="123", api_hash="hash", phone="+79991234567", session_file=source
        )
        assert account.status == SessionStatus.ONLINE
        assert account.telegram_user_id == 1000001
        info = svc.session_file_info(account)
        assert info.exists is True
        assert info.size_bytes > 0
        # The copied file lives under the sessions dir with a UUID name.
        assert (dir_ / f"{account.session_ref}.session").is_file()


@pytest.mark.asyncio
async def test_import_missing_file_rejected(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        with pytest.raises(SessionServiceError):
            await svc.import_session(
                api_id="123", api_hash="h", phone="+7999", session_file=tmp_path / "nope.session"
            )


@pytest.mark.asyncio
async def test_import_invalid_session_rolls_back(tmp_path: Path) -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(health_error=SessionInvalidError())
    )
    source = tmp_path / "bad.session"
    source.write_bytes(b"x")
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        with pytest.raises(SessionServiceError):
            await svc.import_session(
                api_id="123", api_hash="h", phone="+7999", session_file=source
            )
        # Record rolled back and copied file removed.
        assert await svc.list_accounts() == []
        assert list(dir_.glob("*.session")) == []


# --- lifecycle ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_online(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "s.session"
    source.write_bytes(b"x")
    async with session_scope() as db:
        svc = SessionService(
            db, provider_factory=factory_for(provider), sessions_dir=tmp_path / "sessions"
        )
        account = await svc.import_session(api_id="1", api_hash="h", session_file=source)
        checked = await svc.health_check(account.id)
        assert checked.status == SessionStatus.ONLINE
        assert checked.telegram_user_id == 1000001


@pytest.mark.asyncio
async def test_health_check_missing_session_file(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "s.session"
    source.write_bytes(b"x")
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        account = await svc.import_session(api_id="1", api_hash="h", session_file=source)
        (dir_ / f"{account.session_ref}.session").unlink()
        checked = await svc.health_check(account.id)
        assert checked.status == SessionStatus.DISCONNECTED
        assert checked.status_hint


@pytest.mark.asyncio
async def test_enable_disable(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "s.session"
    source.write_bytes(b"x")
    async with session_scope() as db:
        svc = SessionService(
            db, provider_factory=factory_for(provider), sessions_dir=tmp_path / "sessions"
        )
        account = await svc.import_session(api_id="1", api_hash="h", session_file=source)
        disabled = await svc.set_enabled(account.id, False)
        assert disabled.enabled is False
        assert disabled.status == SessionStatus.DISABLED
        enabled = await svc.set_enabled(account.id, True)
        assert enabled.enabled is True
        assert enabled.status == SessionStatus.DISCONNECTED


@pytest.mark.asyncio
async def test_delete_removes_record_and_file(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "s.session"
    source.write_bytes(b"x")
    dir_ = tmp_path / "sessions"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=dir_)
        account = await svc.import_session(api_id="1", api_hash="h", session_file=source)
        file_path = dir_ / f"{account.session_ref}.session"
        assert file_path.is_file()
        await svc.delete_account(account.id)
        assert await svc.get(account.id) is None
        assert not file_path.exists()


@pytest.mark.asyncio
async def test_logout_rotates_session_ref(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    source = tmp_path / "s.session"
    source.write_bytes(b"x")
    async with session_scope() as db:
        svc = SessionService(
            db, provider_factory=factory_for(provider), sessions_dir=tmp_path / "sessions"
        )
        account = await svc.import_session(api_id="1", api_hash="h", session_file=source)
        old_ref = account.session_ref
        updated = await svc.logout(account.id)
        assert updated.session_ref != old_ref
        assert updated.status == SessionStatus.AUTH_REQUIRED
        assert updated.auth_step == "idle"


@pytest.mark.asyncio
async def test_recover_resets_unfinished_wizard(tmp_path: Path) -> None:
    provider = FakeSessionProvider(scenario=FakeAuthScenario(authorized=False))
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        started = await svc.start_auth(api_id="1", api_hash="h", phone="+79990000003")
        # Simulate a crash right after the code step.
        assert (await svc.get(started.account_id)).auth_step == "code"
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        reset = await svc.recover()
        assert reset == 1
        account = await svc.get(started.account_id)
        assert account.auth_step == "idle"
        assert account.status == SessionStatus.AUTH_REQUIRED


@pytest.mark.asyncio
async def test_summary_counts(tmp_path: Path) -> None:
    provider = FakeSessionProvider()
    async with session_scope() as db:
        svc = SessionService(db, provider_factory=factory_for(provider), sessions_dir=tmp_path)
        summary = await svc.summary()
        assert summary["total"] == 0
        source = tmp_path / "s.session"
        source.write_bytes(b"x")
        await svc.import_session(api_id="1", api_hash="h", session_file=source)
        summary = await svc.summary()
        assert summary["total"] == 1
        assert summary["online"] == 1
        assert summary["active"] == 1
