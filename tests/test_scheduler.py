"""Scheduler tests: durable recovery and job execution without external services."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app.db.base import utcnow
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.session import init_models, session_scope
from backend.app.scheduler.scheduler import Scheduler
from backend.app.services.queue_service import QueueService


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


async def test_scheduler_recovers_running_jobs() -> None:
    async with session_scope() as session:
        job = await QueueService(session).enqueue(kind="reaction")
        job.mark_running()
        job_id = job.id

    scheduler = Scheduler()
    await scheduler._recover()

    async with session_scope() as session:
        recovered = await QueueService(session).get(job_id)
        assert recovered is not None
        assert recovered.status == JobStatus.PENDING


async def test_scheduler_start_survives_recovery_failure(monkeypatch) -> None:
    """A failing recovery (e.g. corrupt DB) must not crash app startup."""
    scheduler = Scheduler()

    async def _boom() -> None:
        raise RuntimeError("file is not a database")

    monkeypatch.setattr(scheduler, "_recover", _boom)
    await scheduler.start()
    try:
        assert scheduler._task is not None  # loop still started
    finally:
        await scheduler.stop()


async def test_scheduler_executes_registered_handler() -> None:
    executed: list[str] = []

    async def handler(session, job: Job) -> None:
        executed.append(job.id)

    async with session_scope() as session:
        job = await QueueService(session).enqueue(kind="reaction")
        job_id = job.id

    scheduler = Scheduler()
    scheduler.register("reaction", handler)
    await scheduler._tick()

    assert executed == [job_id]
    async with session_scope() as session:
        done = await QueueService(session).get(job_id)
        assert done is not None
        assert done.status == JobStatus.DONE


async def test_scheduler_marks_failed_handler() -> None:
    async def failing(session, job: Job) -> None:
        raise RuntimeError("boom")

    async with session_scope() as session:
        job = await QueueService(session).enqueue(kind="reaction")
        job_id = job.id

    scheduler = Scheduler()
    scheduler.register("reaction", failing)
    await scheduler._tick()

    async with session_scope() as session:
        failed = await QueueService(session).get(job_id)
        assert failed is not None
        assert failed.status == JobStatus.FAILED
        assert "boom" in failed.error


async def test_scheduler_ignores_future_jobs() -> None:
    async with session_scope() as session:
        await QueueService(session).enqueue(
            kind="reaction", scheduled_at=utcnow() + timedelta(hours=1)
        )
    scheduler = Scheduler()
    scheduler.register("reaction", lambda session, job: None)  # type: ignore[arg-type,return-value]
    await scheduler._tick()  # must not raise


async def test_ensure_periodic_is_idempotent() -> None:
    """``ensure_periodic`` keeps exactly one pending job of a kind."""
    async with session_scope() as session:
        service = QueueService(session)
        first = await service.ensure_periodic("content.posting", interval_seconds=15)
        second = await service.ensure_periodic("content.posting", interval_seconds=15)
        assert first.id == second.id

        jobs = await service.repo.list(kind="content.posting")
    assert len(jobs[0]) == 1


async def test_posting_tick_reschedules_itself() -> None:
    """The posting handler runs a bounded pass and re-enqueues the next tick."""
    from backend.app.scheduler.handlers import POSTING_TICK_SECONDS, _handle_posting

    async with session_scope() as session:
        job = await QueueService(session).enqueue(kind="content.posting")
        job_id = job.id

    scheduler = Scheduler()
    scheduler.register("content.posting", _handle_posting)
    await scheduler._tick()

    async with session_scope() as session:
        done = await QueueService(session).get(job_id)
        assert done is not None and done.status == JobStatus.DONE
        # A fresh tick is queued for the future (status SCHEDULED).
        pending, _total = await QueueService(session).repo.list(kind="content.posting")
    next_ticks = [j for j in pending if j.id != job_id]
    assert len(next_ticks) == 1
    scheduled_at = next_ticks[0].scheduled_at
    assert scheduled_at is not None
    # SQLite returns naive datetimes; compare in the same frame.
    now_naive = utcnow().replace(tzinfo=None)
    delta = (scheduled_at.replace(tzinfo=None) - now_naive).total_seconds()
    assert 0 < delta <= POSTING_TICK_SECONDS + 5


async def test_bot_factory_tick_drains_queue() -> None:
    """The factory handler processes one queued candidate per tick (deep-link)."""
    from backend.app.db.models.bot import BotKind
    from backend.app.scheduler.handlers import _handle_bot_factory
    from backend.app.services.bot_factory import BotFactoryService
    from backend.app.services.bot_service import BotService

    def _bot_factory(token, *, provider_name="auto", settings=None):  # type: ignore[no-untyped-def]
        from backend.app.providers.fake_bot import FakeTelegramBotProvider

        return FakeTelegramBotProvider(token)

    async with session_scope() as session:
        await BotService(session, provider_factory=_bot_factory).add_bot(
            "123123:MANAGER", kind=BotKind.MANAGER, title="Manager"
        )
        service = BotFactoryService(session)
        batch = await service.create_batch(prefix="Mix", count=1)
        await service.enqueue_candidates(batch.id)
        batch_id = batch.id

    async with session_scope() as session:
        job = await QueueService(session).enqueue(
            kind="bot_factory.create",
            payload={"batch_id": batch_id, "via_deeplink": True},
        )
        job_id = job.id

    scheduler = Scheduler()
    scheduler.register("bot_factory.create", _handle_bot_factory)
    await scheduler._tick()

    async with session_scope() as session:
        done = await QueueService(session).get(job_id)
        assert done is not None and done.status == JobStatus.DONE
        # Deep-link work is completed by the owner, so the queue is not re-ticked.
        pending, _total = await QueueService(session).repo.list(
            kind="bot_factory.create"
        )
    next_ticks = [j for j in pending if j.id != job_id]
    assert next_ticks == []
