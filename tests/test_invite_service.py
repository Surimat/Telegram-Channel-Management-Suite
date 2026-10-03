"""Invite Manager tests (PHASE 6): planning, confirmation, execution, limits.

Everything runs against the deterministic fake session provider — no Telegram
credentials and no network (decision D-001). Server limits (FloodWait, privacy,
admin) are exercised via the fake invite scenario.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.db.models.audience import AudienceUser
from backend.app.db.models.invite import (
    InviteJobStatus,
    InviteStatus,
)
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.providers.errors import (
    AlreadyParticipantError,
    ChatAdminRequiredError,
    FloodWaitError,
    PrivacyRestrictedError,
    TelegramProviderError,
)
from backend.app.providers.fake_session import (
    FakeInviteScenario,
    FakeSessionProvider,
)
from backend.app.services.invite_service import InviteService, InviteServiceError


def _factory(provider: FakeSessionProvider):
    def _build(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return provider

    return _build


@pytest_asyncio.fixture
async def setup():
    """Temp DB with one online account and 5 audience users."""
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
        yield session
    await dispose_engine()


async def _drain(service: InviteService, job_id: str, *, max_ticks: int = 100) -> str:
    """Drive the durable loop like the scheduler handler does."""
    action = "more"
    for _ in range(max_ticks):
        action, _delay = await service.run_tick(job_id)
        if action in {"done", "paused"}:
            return action
    raise AssertionError("invite run did not finish")


async def test_preview_counts_and_requires_confirmation(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    preview = await service.preview(target="@target", filters={})
    assert preview["total_candidates"] == 5
    assert preview["planned_operations"] == 5
    assert preview["accounts_count"] == 1
    assert preview["requires_confirmation"] is True
    assert len(preview["sample"]) == 5


async def test_preview_rejects_missing_target(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    with pytest.raises(InviteServiceError):
        await service.preview(target="  ")


async def test_create_job_plans_tasks_without_running(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    job = await service.create_job(target="@target", filters={})
    assert job.status == InviteJobStatus.DRAFT
    assert job.confirmed_at is None
    assert job.total_tasks == 5
    tasks, total = await service.tasks.list_for_job(job.id)
    assert total == 5
    assert all(t.status == InviteStatus.PENDING for t in tasks)
    # A task is scheduled in the future (spaced out), not immediately for all.
    scheduled = sorted(t.scheduled_at for t in tasks)
    assert scheduled[-1] > scheduled[0]


async def test_start_requires_confirmation(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    job = await service.create_job(target="@target", filters={})
    with pytest.raises(InviteServiceError):
        await service.start_job(job.id)


async def test_confirm_and_run_invites_everyone(setup) -> None:
    provider = FakeSessionProvider()
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    job = await service.confirm_and_start(job.id)
    assert job.status == InviteJobStatus.RUNNING
    action = await _drain(service, job.id)
    assert action == "done"
    await setup.refresh(job)
    assert job.status == InviteJobStatus.COMPLETED
    assert job.invited_count == 5
    assert sorted(provider.invite.record) == [1000, 1001, 1002, 1003, 1004]


async def test_dry_run_does_not_call_provider(setup) -> None:
    provider = FakeSessionProvider()
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target",
        filters={},
        dry_run=True,
        per_account_delay_min=0,
        per_account_delay_max=0,
    )
    await service.confirm_and_start(job.id)
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.invited_count == 5
    assert provider.invite.record == []


async def test_privacy_restriction_becomes_task_status(setup) -> None:
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(
            errors_by_user={1002: PrivacyRestrictedError(technical="test")}
        )
    )
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.status == InviteJobStatus.COMPLETED
    assert job.invited_count == 4
    assert job.privacy_count == 1


async def test_already_participant_is_not_an_error(setup) -> None:
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(
            errors_by_user={1001: AlreadyParticipantError(technical="test")}
        )
    )
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.already_count == 1
    assert job.error_count == 0


async def test_flood_wait_pauses_and_reports_wait(setup) -> None:
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(error_after=1, default_error=FloodWaitError(45))
    )
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    action = await _drain(service, job.id)
    assert action == "paused"
    await setup.refresh(job)
    assert job.status == InviteJobStatus.PAUSED
    assert job.wait_until is not None
    assert job.flood_count >= 1
    # Never bypassed: at most 2 invites were attempted before pausing.
    assert len(provider.invite.record) <= 2


async def test_admin_required_counts_as_error(setup) -> None:
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(
            errors_by_user={1000: ChatAdminRequiredError(technical="test")}
        )
    )
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.error_count == 1


async def test_pause_and_resume(setup) -> None:
    provider = FakeSessionProvider()
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    job = await service.pause_job(job.id)
    assert job.status == InviteJobStatus.PAUSED
    # A paused run does nothing.
    action, _ = await service.run_tick(job.id)
    assert action == "done"
    job = await service.resume_job(job.id)
    assert job.status == InviteJobStatus.RUNNING
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.invited_count == 5


async def test_stop_halts_run(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    job = await service.stop_job(job.id)
    assert job.status == InviteJobStatus.STOPPED


async def test_retry_failed_resets_and_resumes(setup) -> None:
    # A generic provider error is a retryable failure; unlike a privacy
    # restriction it is safe to retry.
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(default_error=TelegramProviderError("Временный сбой."))
    )
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.error_count == 5
    # Now allow success and retry the failed tasks.
    provider.invite.default_error = None
    job = await service.retry_failed(job.id)
    assert job.status == InviteJobStatus.RUNNING
    await _drain(service, job.id)
    await setup.refresh(job)
    assert job.invited_count == 5


async def test_privacy_is_not_retried(setup) -> None:
    # Privacy restrictions are permanent server-side; retry must not reset them.
    provider = FakeSessionProvider(
        invite=FakeInviteScenario(default_error=PrivacyRestrictedError(technical="test"))
    )
    service = InviteService(setup, session_provider_factory=_factory(provider))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    await _drain(service, job.id)
    provider.invite.default_error = None
    job = await service.retry_failed(job.id)
    await setup.refresh(job)
    assert job.privacy_count == 5
    assert job.invited_count == 0


async def test_recover_pauses_interrupted_runs(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    job = await service.create_job(
        target="@target", filters={}, per_account_delay_min=0, per_account_delay_max=0
    )
    await service.confirm_and_start(job.id)
    paused = await service.recover()
    assert paused == 1
    await setup.refresh(job)
    assert job.status == InviteJobStatus.PAUSED


async def test_max_total_cap(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    job = await service.create_job(target="@target", filters={}, max_total=2)
    assert job.total_tasks == 2


async def test_filters_narrow_the_slice(setup) -> None:
    service = InviteService(setup, session_provider_factory=_factory(FakeSessionProvider()))
    preview = await service.preview(target="@t", filters={"search": "user3"})
    assert preview["total_candidates"] == 1
    assert preview["sample"][0]["username"] == "user3"
