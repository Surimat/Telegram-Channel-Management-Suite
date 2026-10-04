"""Durable scheduler.

An asyncio-based worker loop (no Redis/Celery) that:
1. On start, recovers jobs left RUNNING by a previous crash.
2. Periodically claims due jobs from the database and executes registered
   handlers.
3. Persists status transitions so progress survives restarts.

Job handlers are registered by ``kind``. A handler receives the *same* database
session the scheduler uses, so a handler can transact together with the job row
without opening a second SQLite connection (decisions D-008, D-022).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.db.models.event import EventLevel
from backend.app.db.models.job import Job
from backend.app.db.session import session_scope
from backend.app.services.events_service import EventsService
from backend.app.services.queue_service import QueueService

logger = get_logger(__name__)

JobHandler = Callable[[AsyncSession, Job], Awaitable[None]]


class Scheduler:
    """Minimal asyncio scheduler driving the durable job queue."""

    def __init__(self, poll_interval: float = 2.0, batch_size: int = 50) -> None:
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._handlers: dict[str, JobHandler] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        # Recovery touches the database. If the DB is unavailable/corrupt, do not
        # let it crash application startup: the scheduler loop below tolerates
        # errors and retries, and the Diagnostics page can then explain the DB
        # problem to the user instead of the app dying with a traceback.
        try:
            await self._recover()
        except Exception as exc:
            logger.error("Scheduler recovery failed (continuing): %s", exc)
        self._task = asyncio.create_task(self._run(), name="tcms-scheduler")
        logger.info("Scheduler started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Scheduler stopped")

    async def _recover(self) -> None:
        async with session_scope() as session:
            count = await QueueService(session).recover()
        if count:
            logger.info("Recovered %d unfinished job(s) after restart", count)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Scheduler tick failed: %s", exc)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)

    async def _tick(self) -> None:
        async with session_scope() as session:
            jobs = await QueueService(session).claim_due(limit=self.batch_size)
            for job in jobs:
                handler = self._handlers.get(job.kind)
                if handler is None:
                    continue
                job.mark_running()
                await session.flush()
                try:
                    await handler(session, job)
                    job.mark_done()
                except Exception as exc:
                    logger.warning("Job %s failed: %s", job.id, exc)
                    job.mark_failed(str(exc))
                    await EventsService(session).record(
                        level=EventLevel.ERROR,
                        module="scheduler",
                        operation=job.kind,
                        message="Не удалось выполнить задание.",
                        how_to_fix="Откройте раздел «Очередь» и повторите задание.",
                        status="failed",
                    )
                await session.flush()
