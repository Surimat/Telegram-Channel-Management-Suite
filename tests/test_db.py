"""Database tests: models, repositories, queue, events, settings."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app.db.base import utcnow
from backend.app.db.models.event import EventLevel
from backend.app.db.models.job import JobStatus
from backend.app.db.session import init_models, session_scope
from backend.app.services.events_service import EventsService
from backend.app.services.queue_service import QueueService
from backend.app.services.settings_service import SettingsService


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


async def test_settings_roundtrip() -> None:
    async with session_scope() as session:
        service = SettingsService(session)
        await service.set("reaction_delay_min", 30)
        await service.set("ai_enabled", True)
        assert await service.get_typed("reaction_delay_min") == 30
        assert await service.get_typed("ai_enabled") is True


async def test_events_record_and_list() -> None:
    async with session_scope() as session:
        service = EventsService(session)
        await service.error("scheduler", "boom", how_to_fix="retry")
    async with session_scope() as session:
        rows, total = await EventsService(session).list(level=EventLevel.ERROR)
        assert total == 1
        assert rows[0].how_to_fix == "retry"


async def test_queue_enqueue_and_claim() -> None:
    async with session_scope() as session:
        service = QueueService(session)
        await service.enqueue(kind="reaction", payload={"x": 1})
    async with session_scope() as session:
        service = QueueService(session)
        due = await service.claim_due()
        assert len(due) == 1
        assert due[0].kind == "reaction"


async def test_queue_scheduled_not_due() -> None:
    async with session_scope() as session:
        await QueueService(session).enqueue(
            kind="reaction", scheduled_at=utcnow() + timedelta(hours=1)
        )
    async with session_scope() as session:
        assert await QueueService(session).claim_due() == []


async def test_queue_recover_running() -> None:
    async with session_scope() as session:
        service = QueueService(session)
        job = await service.enqueue(kind="reaction")
        job.mark_running()
        job_id = job.id
    async with session_scope() as session:
        recovered = await QueueService(session).recover()
        assert recovered == 1
        job = await QueueService(session).get(job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING


async def test_queue_retry_and_cancel() -> None:
    async with session_scope() as session:
        service = QueueService(session)
        job = await service.enqueue(kind="invite")
        job.mark_failed("nope")
        job_id = job.id
    async with session_scope() as session:
        service = QueueService(session)
        retried = await service.retry(job_id)
        assert retried is not None and retried.status == JobStatus.PENDING
        cancelled = await service.cancel(job_id)
        assert cancelled is not None and cancelled.status == JobStatus.CANCELLED
