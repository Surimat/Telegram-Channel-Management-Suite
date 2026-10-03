"""Job queue repository (durable, restart-resilient)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.job import Job, JobStatus


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, job: Job) -> Job:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def list(
        self,
        *,
        status: JobStatus | None = None,
        kind: str | None = None,
        group_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        stmt = select(Job)
        count_stmt = select(func.count()).select_from(Job)
        for cond in (
            (Job.status == status) if status is not None else None,
            (Job.kind == kind) if kind else None,
            (Job.group_key == group_key) if group_key else None,
        ):
            if cond is not None:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
        stmt = (
            stmt.order_by(Job.priority.desc(), Job.scheduled_at.asc().nullsfirst())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def due(self, now: datetime | None = None, limit: int = 50) -> list[Job]:
        """Jobs that are ready to run (pending or scheduled and due)."""
        now = now or utcnow()
        stmt = (
            select(Job)
            .where(Job.status.in_([JobStatus.PENDING, JobStatus.SCHEDULED]))
            .where((Job.scheduled_at.is_(None)) | (Job.scheduled_at <= now))
            .order_by(Job.priority.desc(), Job.scheduled_at.asc().nullsfirst())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def recover_stuck_running(self) -> int:
        """Reset jobs left in RUNNING after a crash back to PENDING."""
        stmt = select(Job).where(Job.status == JobStatus.RUNNING)
        jobs = list((await self.session.execute(stmt)).scalars().all())
        for job in jobs:
            job.status = JobStatus.PENDING
        if jobs:
            await self.session.flush()
        return len(jobs)
