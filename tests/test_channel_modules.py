"""Module-gate regression guard (D-124).

``channel.modules`` is the authoritative registry of what is enabled per
channel: switching a module off must *actually* gate its operations on every
path (API, scheduler, background tick), not merely persist a flag.

These tests seed a channel, disable one module, and prove:
* a never-configured channel keeps every module enabled (backward compatible);
* the service guard refuses with a friendly error and no 500;
* the HTTP slice returns a friendly 403 for a disabled module;
* the invite and audience *background* ticks refuse to run for that channel.
"""

from __future__ import annotations

import json

import pytest

from backend.app.db.models.channel import Channel, ChannelKind
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.session import init_models, session_scope
from backend.app.services.channel_modules import (
    MODULE_AUDIENCE,
    MODULE_INVITES,
    ChannelModuleDisabledError,
    ChannelModuleGuard,
    effective_modules,
    module_enabled,
    parse_modules,
)
from backend.app.services.channel_service import ChannelService


async def _seed_session(telegram_user_id: int = 1000001) -> str:
    from backend.app.db.base import new_id

    account = UserSession(
        id=new_id(),
        telegram_user_id=telegram_user_id,
        username="fake_user",
        display_name="Fake User",
        status=SessionStatus.ONLINE,
        enabled=True,
        api_id="1",
    )
    async with session_scope() as session:
        session.add(account)
    return account.id


async def _seed_channel(channel_id: str, *, modules: str | None = None) -> None:
    async with session_scope() as session:
        session.add(
            Channel(
                id=channel_id,
                reference="@guarded",
                username="guarded",
                kind=ChannelKind.CHANNEL,
                **({"modules": modules} if modules is not None else {}),
            )
        )


def test_effective_map_legacy_and_configured() -> None:
    # Never configured (empty/absent map) ⇒ every module stays enabled.
    assert effective_modules({}) == {
        "reactions": True,
        "audience": True,
        "invites": True,
        "analytics": True,
    }
    assert module_enabled({}, MODULE_INVITES) is True

    # A configured map is authoritative; a missing canonical key is disabled.
    configured = {"invites": False, "audience": True}
    assert module_enabled(configured, MODULE_INVITES) is False
    assert module_enabled(configured, MODULE_AUDIENCE) is True
    assert module_enabled(configured, "analytics") is False

    # Unknown modules are never blocked by this gate.
    assert module_enabled({"invites": False}, "some-future-module") is True


def test_parse_modules_tolerates_bad_json() -> None:
    assert parse_modules("not-json") == {}
    assert parse_modules("[]") == {}
    assert parse_modules(json.dumps({"invites": 1})) == {"invites": True}


async def test_guard_refuses_disabled_module() -> None:
    await init_models()
    async with session_scope() as session:
        session.add(
            Channel(
                id="ch-guard",
                reference="@guarded",
                username="guarded",
                kind=ChannelKind.CHANNEL,
                modules=json.dumps({"invites": False}),
            )
        )

    async with session_scope() as session:
        guard = ChannelModuleGuard(session)
        assert await guard.is_enabled("ch-guard", MODULE_INVITES) is False
        try:
            await guard.require("ch-guard", MODULE_INVITES)
        except ChannelModuleDisabledError as exc:
            assert exc.status_code == 403
            assert "отключён" in exc.message.lower()
        else:  # pragma: no cover - the guard must raise
            raise AssertionError("require() must raise for a disabled module")

        # Unknown / missing channels have no authority to consult ⇒ not blocked.
        assert await guard.is_enabled("", MODULE_INVITES) is True
        assert await guard.is_enabled("no-such-channel", MODULE_INVITES) is True


async def test_never_configured_channel_gate_passes() -> None:
    await init_models()
    await _seed_channel("ch-legacy")

    async with session_scope() as session:
        # The default module string is "{}" (never configured) ⇒ enabled.
        guard = ChannelModuleGuard(session)
        assert await guard.is_enabled("ch-legacy", MODULE_INVITES) is True
        # set_modules always persists every canonical key afterwards.
        svc = ChannelService(session)
        await svc.set_modules("ch-legacy", {})
        channel = await svc.get("ch-legacy")
        assert channel is not None
        stored = parse_modules(channel.modules)
        assert set(stored) == {"reactions", "audience", "invites", "analytics"}


async def test_channels_api_refuses_disabled_invites(channel_client) -> None:
    # A fresh, never-configured channel: the owner disables invites via the API.
    await _seed_channel("ch-api")

    # Enabling/disabling through the API persists and is echoed back.
    toggled = await channel_client.post(
        "/api/v1/channels/ch-api/modules", json={"modules": {"invites": False}}
    )
    assert toggled.status_code == 200
    assert toggled.json()["modules"]["invites"] is False
    # Disabling one module must not disconnect the untouched modules.
    assert toggled.json()["modules"]["audience"] is True

    refused = await channel_client.post(
        "/api/v1/invites",
        json={
            "target": "@target",
            "channel_id": "ch-api",
            "per_account_delay_min": 0,
            "per_account_delay_max": 0,
        },
    )
    assert refused.status_code == 403, refused.text
    assert "отключён" in refused.json()["error"]["message"].lower()


async def test_audience_api_refuses_disabled_module(audience_client) -> None:
    await _seed_channel("ch-aud", modules=json.dumps({"audience": False}))
    refused = await audience_client.post(
        "/api/v1/audience/sources",
        json={"reference": "@somefeed", "channel_id": "ch-aud"},
    )
    assert refused.status_code == 403, refused.text
    assert "отключён" in refused.json()["error"]["message"].lower()


async def test_audience_api_refuses_disabled_analytics(client) -> None:
    await _seed_channel("ch-an", modules=json.dumps({"analytics": False}))
    refused = await client.get("/api/v1/analytics/overview", params={"channel_id": "ch-an"})
    assert refused.status_code == 403, refused.text
    assert "отключён" in refused.json()["error"]["message"].lower()
    # Global aggregates stay available.
    assert (await client.get("/api/v1/analytics/overview")).status_code == 200


async def test_invite_tick_pauses_when_module_disabled() -> None:
    from backend.app.db.models.invite import InviteJob, InviteJobStatus
    from backend.app.providers.fake_session import FakeSessionProvider
    from backend.app.services.invite_service import InviteService

    await init_models()
    await _seed_channel("ch-tick", modules=json.dumps({"invites": False}))
    async with session_scope() as session:
        session.add(
            InviteJob(
                id="job-1",
                target="@target",
                channel_id="ch-tick",
                status=InviteJobStatus.RUNNING,
            )
        )

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return FakeSessionProvider()

    async with session_scope() as session:
        action, _ = await InviteService(
            session, session_provider_factory=_factory
        ).run_tick("job-1")
    assert action == "done"

    async with session_scope() as session:
        job = await session.get(InviteJob, "job-1")
        assert job is not None
        assert job.status == InviteJobStatus.PAUSED


async def test_audience_tick_pauses_when_module_disabled() -> None:
    from backend.app.db.models.audience import AudienceSource, ScanStatus
    from backend.app.providers.fake_session import (
        FakeAudienceScenario,
        FakeSessionProvider,
        make_fake_users,
    )
    from backend.app.services.audience_service import AudienceService

    await init_models()
    await _seed_channel("ch-scan", modules=json.dumps({"audience": False}))
    await _seed_session()
    async with session_scope() as session:
        session.add(
            AudienceSource(
                id="src-1",
                reference="@scan",
                channel_id="ch-scan",
                scan_status=ScanStatus.SCANNING,
            )
        )

    shared = FakeSessionProvider(
        audience=FakeAudienceScenario(participants=make_fake_users(10), page_size=50)
    )

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return shared

    async with session_scope() as session:
        await AudienceService(
            session, session_provider_factory=_factory
        ).run_scan_chunk()

    async with session_scope() as session:
        source = await session.get(AudienceSource, "src-1")
        assert source is not None
        assert source.scan_status == ScanStatus.PAUSED


async def test_scheduler_scan_handler_pauses_disabled_module() -> None:
    """The real background audience handler refuses a switched-off channel.

    ``_handle_scan`` is what the scheduler actually runs; it must pause the
    source instead of scanning when the audience module is off (D-124).
    """
    from backend.app.db.models.audience import AudienceSource, ScanStatus
    from backend.app.db.models.job import Job, JobStatus
    from backend.app.scheduler.handlers import _handle_scan
    from backend.app.scheduler.scheduler import Scheduler
    from backend.app.services.queue_service import QueueService

    await init_models()
    await _seed_channel("ch-sched", modules=json.dumps({"audience": False}))
    async with session_scope() as session:
        session.add(
            AudienceSource(
                id="src-sched",
                reference="@scan",
                channel_id="ch-sched",
                scan_status=ScanStatus.SCANNING,
            )
        )
        job = await QueueService(session).enqueue(kind="audience.scan")
        job_id = job.id

    scheduler = Scheduler()
    scheduler.register("audience.scan", _handle_scan)
    await scheduler._tick()

    async with session_scope() as session:
        qjob = await session.get(Job, job_id)
        assert qjob is not None and qjob.status == JobStatus.DONE
        source = await session.get(AudienceSource, "src-sched")
        assert source is not None
        assert source.scan_status == ScanStatus.PAUSED


async def test_audience_check_and_preview_refused_when_disabled() -> None:
    """Read-only audience probes still contact Telegram, so they are gated too."""
    from backend.app.db.models.audience import AudienceSource, ScanStatus
    from backend.app.services.audience_service import AudienceService

    await init_models()
    await _seed_channel("ch-probe", modules=json.dumps({"audience": False}))
    async with session_scope() as session:
        session.add(
            AudienceSource(
                id="src-probe",
                reference="@probe",
                channel_id="ch-probe",
                scan_status=ScanStatus.IDLE,
            )
        )

    async with session_scope() as session:
        service = AudienceService(session)
        with pytest.raises(ChannelModuleDisabledError):
            await service.check_source("src-probe")
        with pytest.raises(ChannelModuleDisabledError):
            await service.preview_scan("src-probe")
        # Editing a source is part of the module too: it must be refused before
        # any field changes (D-124).
        with pytest.raises(ChannelModuleDisabledError):
            await service.update_source("src-probe", title="changed")


async def test_channel_modules_are_independent() -> None:
    """Switching a module off on one channel never affects another channel."""
    await init_models()
    await _seed_channel("ch-a", modules=json.dumps({"invites": False, "audience": True}))
    await _seed_channel("ch-b", modules=json.dumps({"invites": True, "audience": True}))

    async with session_scope() as session:
        guard = ChannelModuleGuard(session)
        # invites: off on A, on for B.
        assert await guard.is_enabled("ch-a", MODULE_INVITES) is False
        assert await guard.is_enabled("ch-b", MODULE_INVITES) is True
        with pytest.raises(ChannelModuleDisabledError):
            await guard.require("ch-a", MODULE_INVITES)
        await guard.require("ch-b", MODULE_INVITES)  # must not raise


async def test_invite_http_resume_refused_when_module_disabled(invite_client) -> None:
    """The HTTP resume launch point refuses a channel whose invites are off.

    A job is created while invites are connected, then the owner disconnects the
    module via the API; starting/resuming the run must now answer a friendly 403.
    """
    await _seed_channel("ch-inv")
    created = await invite_client.post(
        "/api/v1/invites",
        json={
            "target": "@target",
            "channel_id": "ch-inv",
            "per_account_delay_min": 0,
            "per_account_delay_max": 0,
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    off = await invite_client.post(
        "/api/v1/channels/ch-inv/modules", json={"modules": {"invites": False}}
    )
    assert off.status_code == 200
    assert off.json()["modules"]["invites"] is False

    confirmed = await invite_client.post(f"/api/v1/invites/{job_id}/confirm")
    assert confirmed.status_code == 403, confirmed.text
    assert "отключён" in confirmed.json()["error"]["message"].lower()


async def test_bot_rights_remain_the_real_authority_for_enabled_channels() -> None:
    """Connecting a module is not the same as Telegram allowing it (D-124).

    A connected module still defers to the real permission probe: a Telegram
    account that cannot invite yields an honest, not-fully-authorized status even
    though the registry gate is open. The registry never fabricates rights.
    """
    from sqlalchemy import select

    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.providers.fake_session import (
        FakeAuthScenario,
        FakePermissionScenario,
        FakeSessionProvider,
    )
    from backend.app.services.permission_service import STATUS_OK, PermissionService

    await init_models()
    await _seed_channel("ch-rights")

    # The registry gate is open for a connected invites module.
    async with session_scope() as session:
        assert (
            await ChannelModuleGuard(session).is_enabled("ch-rights", MODULE_INVITES)
            is True
        )

    provider = FakeSessionProvider(
        permission=FakePermissionScenario(can_invite=False, participants_hidden=False),
        scenario=FakeAuthScenario(),
    )

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return provider

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
    async with session_scope() as session:
        account = (await session.execute(select(UserSession).limit(1))).scalar_one()
        result = await PermissionService(
            session, session_provider_factory=_factory
        ).check(account.id, "@guarded")
    # Telegram says this account cannot invite — the probe reports that honestly.
    assert result.can_invite is False
    assert result.status != STATUS_OK


async def test_personal_account_off_beats_connected_invites_module() -> None:
    """D-123 is not weakened: the personal-account switch still gates invites.

    Even with the invites module *connected* to the channel, turning the personal
    account master switch off must refuse the bulk run (the registry never removes
    a safety gate).
    """
    from backend.app.providers.fake_session import FakeSessionProvider
    from backend.app.services.personal_account import PersonalAccountDisabledError
    from backend.app.services.settings_service import SettingsService

    await init_models()
    await _seed_channel("ch-safety", modules=json.dumps({"invites": True}))

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return FakeSessionProvider()

    async with session_scope() as session:
        await SettingsService(session).set("personal_account_enabled", False)

    async with session_scope() as session:
        from backend.app.services.invite_service import InviteService

        service = InviteService(session, session_provider_factory=_factory)
        with pytest.raises(PersonalAccountDisabledError):
            await service.preview(channel_id="ch-safety", target="@target")
