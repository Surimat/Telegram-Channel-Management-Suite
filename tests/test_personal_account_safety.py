"""Personal-account safety policy tests.

The default must be *safe*: with no explicit opt-in the system never uses the
owner's personal Telegram (MTProto) account and never launches an unbounded bulk
invite. Everything runs against the deterministic fake provider — no credentials
and no network (D-001).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.db.models.audience import AudienceUser
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.providers.fake_session import FakeSessionProvider
from backend.app.services.invite_service import (
    DEFAULT_INVITE_MAX_PER_ACCOUNT,
    DEFAULT_INVITE_MAX_TOTAL,
    InviteService,
)
from backend.app.services.personal_account import (
    PersonalAccountDisabledError,
    PersonalAccountPolicy,
    ensure_personal_account_settings,
)
from backend.app.services.session_service import SessionService, describe_code_delivery
from backend.app.services.settings_service import SettingsService


def _factory(provider: FakeSessionProvider):
    def _build(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return provider

    return _build


async def _set_flag(key: str, value: bool) -> None:
    from backend.app.db.session import session_scope

    async with session_scope() as session:
        await SettingsService(session).set(key, value)


@pytest_asyncio.fixture
async def db():
    from backend.app.db.session import dispose_engine, init_models, session_scope

    await init_models()
    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )
        for i in range(5):
            session.add(
                AudienceUser(
                    telegram_user_id=1000 + i,
                    username=f"user{i}",
                    display_name=f"User {i}",
                )
            )
        await session.flush()
    yield
    await dispose_engine()


# --- the switches ------------------------------------------------------------
def test_settings_default_is_off() -> None:
    """The shipped default (no .env, no DB row) must be OFF for both switches."""
    from backend.app.core.config import Settings

    assert Settings.model_fields["personal_account_enabled"].default is False
    assert Settings.model_fields["invites_enabled"].default is False


async def test_stored_off_row_is_honoured(db) -> None:
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", False)
    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        policy = PersonalAccountPolicy(session)
        assert await policy.personal_account_enabled() is False
        assert await policy.invites_enabled() is False
        assert await policy.invites_allowed() is False


async def test_master_switch_blocks_auth_without_creating_an_account(db) -> None:
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", False)
    async with session_scope() as session:
        service = SessionService(
            session,
            provider_factory=_factory(FakeSessionProvider()),
            sessions_dir=None,
        )
        with pytest.raises(PersonalAccountDisabledError):
            await service.start_auth(api_id="123", api_hash="hash", phone="+79991234567")

    # The refusal happens before anything is persisted: no orphan account/file.
    from sqlalchemy import func, select

    from backend.app.db.models.session import UserSession as _UserSession

    async with session_scope() as session:
        count = await session.scalar(select(func.count()).select_from(_UserSession))
    assert count == 1  # only the pre-seeded account


async def test_invites_require_both_switches(db) -> None:
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(FakeSessionProvider()))
        with pytest.raises(PersonalAccountDisabledError):
            await service.preview(target="@target")
        with pytest.raises(PersonalAccountDisabledError):
            await service.create_job(target="@target")

    # Turning the mass-action switch on is not enough by itself.
    await _set_flag("personal_account_enabled", False)
    await _set_flag("invites_enabled", True)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(FakeSessionProvider()))
        with pytest.raises(PersonalAccountDisabledError):
            await service.create_job(target="@target")


async def test_start_is_blocked_when_invites_are_switched_off_mid_run(db) -> None:
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", True)
    provider = FakeSessionProvider()
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        job = await service.create_job(
            target="@target", per_account_delay_min=0, per_account_delay_max=0
        )
        job = await service.confirm_and_start(job.id)
        assert job.status.value == "running"

    # The owner switches invitations off; the running job must pause, not invite.
    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        action, _ = await service.run_tick(job.id)
        assert action == "done"
    assert provider.invite.record == []


# --- caps --------------------------------------------------------------------
async def test_invite_caps_are_bounded_by_default(db) -> None:
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", True)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(FakeSessionProvider()))
        job = await service.create_job(target="@target")
        assert job.max_total == DEFAULT_INVITE_MAX_TOTAL
        assert job.max_per_account == DEFAULT_INVITE_MAX_PER_ACCOUNT


async def test_invite_caps_cannot_be_unbounded(db) -> None:
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", True)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(FakeSessionProvider()))
        # A request for "no cap" (0) must fall back to a real, non-zero limit.
        job = await service.create_job(target="@target", max_total=0, max_per_account=0)
        assert job.max_total > 0
        assert job.max_per_account > 0


# --- wiring ------------------------------------------------------------------
async def test_seed_creates_switches_without_overwriting_owner_choice(db) -> None:
    from backend.app.db.session import session_scope

    async with session_scope() as session:
        await ensure_personal_account_settings(session)
        await SettingsService(session).set("personal_account_enabled", True)
        # A second seed must not clobber the owner's choice.
        await ensure_personal_account_settings(session)
        value = await SettingsService(session).get_typed("personal_account_enabled")
    assert value is True


def test_code_delivery_never_promises_sms() -> None:
    assert "SMS" in describe_code_delivery("SentCodeTypeSms")
    assert "приложение" in describe_code_delivery("app")
    assert "приложение" in describe_code_delivery("")
    assert "SMS" not in describe_code_delivery("app")


async def test_api_returns_friendly_403_when_disabled(client) -> None:
    await _set_flag("personal_account_enabled", False)
    resp = await client.post(
        "/api/v1/sessions/auth/start",
        json={"api_id": "123", "api_hash": "hash", "phone": "+79991234567"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert "личн" in body["error"]["message"].lower()
    assert body["error"]["hint"]
    assert body["error"]["code"] == "forbidden"
