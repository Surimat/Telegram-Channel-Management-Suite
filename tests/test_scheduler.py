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


async def test_scheduler_executes_registered_handler() -> None:
    executed: list[str] = []

    async def handler(job: Job) -> None:
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
    async def failing(job: Job) -> None:
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
    scheduler.register("reaction", lambda job: None)  # type: ignore[arg-type]
    await scheduler._tick()  # must not raise
