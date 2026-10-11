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


async def test_start_and_resume_blocked_when_invites_switched_off(db) -> None:
    """A drafted run cannot be started or resumed while the mass switch is off."""
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", True)
    provider = FakeSessionProvider()
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        job = await service.create_job(
            target="@target", per_account_delay_min=0, per_account_delay_max=0
        )
        job_id = job.id

    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        with pytest.raises(PersonalAccountDisabledError):
            await service.start_job(job_id)
        job = await service.jobs.get(job_id)
        await service.pause_job(job_id)
        with pytest.raises(PersonalAccountDisabledError):
            await service.resume_job(job_id)
    assert provider.invite.record == []


async def test_flood_wait_pauses_without_automatic_retry(db) -> None:
    """FloodWait pauses the run and is never retried automatically (D-006)."""
    from backend.app.db.models.invite import InviteJobStatus, InviteStatus
    from backend.app.db.session import session_scope
    from backend.app.providers.errors import FloodWaitError
    from backend.app.providers.fake_session import FakeInviteScenario

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", True)
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(error_after=1, default_error=FloodWaitError(45))
    )
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        job = await service.create_job(
            target="@target", per_account_delay_min=0, per_account_delay_max=0
        )
        job = await service.confirm_and_start(job.id)
        job_id = job.id

    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        action, delay = await service.run_tick(job_id)
        assert action == "paused"
        assert delay == 0.0
        job = await service.jobs.get(job_id)
        assert job.status == InviteJobStatus.PAUSED
        assert job.wait_until is not None
        assert job.flood_count >= 1
        tasks, _ = await service.tasks.list_for_job(job_id, limit=100)
        assert any(t.status == InviteStatus.FLOOD_WAIT for t in tasks)
        # A paused run does nothing on a further tick — no retry loop.
        assert await service.run_tick(job_id) == ("done", 0.0)
    assert len(provider.invite.record) <= 2


async def test_retry_failed_requires_the_mass_switch(db) -> None:
    """Even an explicit retry cannot run while bulk invitations are switched off."""
    from backend.app.db.models.invite import InviteJobStatus
    from backend.app.db.session import session_scope
    from backend.app.providers.errors import TelegramProviderError
    from backend.app.providers.fake_session import FakeInviteScenario

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", True)
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(default_error=TelegramProviderError("Временный сбой."))
    )
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        job = await service.create_job(
            target="@target", per_account_delay_min=0, per_account_delay_max=0
        )
        await service.confirm_and_start(job.id)
        await service.run_tick(job.id)
        job_id = job.id
    attempts_while_enabled = len(provider.invite.record)

    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        service = InviteService(session, session_provider_factory=_factory(provider))
        # An explicit retry must also refuse while the mass switch is off.
        with pytest.raises(PersonalAccountDisabledError):
            await service.retry_failed(job_id)
        job = await service.jobs.get(job_id)
        assert job.status != InviteJobStatus.RUNNING
        # run_tick must not act on a non-running job, so nothing new is invited.
        assert await service.run_tick(job_id) == ("done", 0.0)
    assert len(provider.invite.record) == attempts_while_enabled


async def test_invite_api_blocked_when_invites_off(client) -> None:
    """Both the dry-run and creation answer a friendly 403 while invites are off."""
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.session import session_scope

    await _set_flag("personal_account_enabled", True)
    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000009,
                username="fake_user2",
                display_name="Fake User 2",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )
        await session.flush()

    preview = await client.post("/api/v1/invites/preview", json={"target": "@target"})
    assert preview.status_code == 403
    assert preview.json()["error"]["hint"]

    created = await client.post("/api/v1/invites", json={"target": "@target"})
    assert created.status_code == 403
    assert created.json()["error"]["hint"]


async def test_bot_api_works_while_personal_account_is_off(db) -> None:
    """Turning the personal account off must not affect the Telegram Bot API."""
    from backend.app.db.session import session_scope
    from backend.app.services.bot_service import BotService
    from tests.conftest import make_fake_provider_factory

    await _set_flag("personal_account_enabled", False)
    await _set_flag("invites_enabled", False)
    async with session_scope() as session:
        service = BotService(session, provider_factory=make_fake_provider_factory())
        bot = await service.add_bot(token="123456:TEST-TOKEN", title="My Bot")
        assert bot.has_token
        provider = service.provider_for(bot)
        identity = await provider.get_me()
        assert identity.id == 123456
        await provider.send_message("@channel", "hello")
        assert provider.sent_messages == [("@channel", "hello")]


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
