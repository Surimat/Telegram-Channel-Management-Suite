"""Queue service: enqueue and manage durable jobs.

The queue is database-backed so unfinished work survives restarts. The scheduler
(PHASE 3) drives execution; this service owns the lifecycle transitions.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.job import Job, JobStatus
from backend.app.db.repositories.jobs import JobRepository


class QueueService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = JobRepository(session)

    async def enqueue(
        self,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
        priority: int = 0,
        group_key: str = "",
        max_attempts: int = 3,
    ) -> Job:
        status = JobStatus.SCHEDULED if scheduled_at else JobStatus.PENDING
        job = Job(
            kind=kind,
            payload=json.dumps(payload or {}),
            scheduled_at=scheduled_at,
            priority=priority,
            group_key=group_key,
            max_attempts=max_attempts,
            status=status,
        )
        return await self.repo.add(job)

    async def get(self, job_id: str) -> Job | None:
        return await self.repo.get(job_id)

    async def list(self, **kwargs: Any) -> tuple[list[Job], int]:
        return await self.repo.list(**kwargs)

    async def claim_due(self, limit: int = 50) -> list[Job]:
        return await self.repo.due(limit=limit)

    async def retry(self, job_id: str) -> Job | None:
        job = await self.repo.get(job_id)
        if job is None:
            return None
        job.status = JobStatus.PENDING
        job.error = ""
        await self.repo.session.flush()
        return job

    async def cancel(self, job_id: str) -> Job | None:
        job = await self.repo.get(job_id)
        if job is None:
            return None
        job.status = JobStatus.CANCELLED
        await self.repo.session.flush()
        return job

    async def recover(self) -> int:
        """Re-hydrate jobs stuck in RUNNING after a crash."""
        return await self.repo.recover_stuck_running()
