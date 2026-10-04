"""Job queue repository (durable, restart-resilient)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
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

    async def list_stuck_running(self) -> list[Job]:
        """Jobs still marked RUNNING (e.g. after an unclean shutdown)."""
        stmt = select(Job).where(Job.status == JobStatus.RUNNING)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_overdue(
        self, *, kind: str | None = None, grace_seconds: int = 300, limit: int = 500
    ) -> list[Job]:
        """Pending/scheduled jobs whose due time is far in the past.

        ``grace_seconds`` keeps recently scheduled work out of the result so a
        normal busy queue is never mistaken for stale jobs.
        """
        cutoff = utcnow() - timedelta(seconds=max(grace_seconds, 0))
        stmt = (
            select(Job)
            .where(Job.status.in_([JobStatus.PENDING, JobStatus.SCHEDULED]))
            .where(Job.scheduled_at.is_not(None))
            .where(Job.scheduled_at < cutoff)
        )
        if kind:
            stmt = stmt.where(Job.kind == kind)
        stmt = stmt.order_by(Job.scheduled_at.asc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def cancel_many(self, job_ids: list[str]) -> int:
        """Mark the given jobs CANCELLED; returns how many were changed."""
        if not job_ids:
            return 0
        stmt = select(Job).where(Job.id.in_(job_ids))
        jobs = list((await self.session.execute(stmt)).scalars().all())
        for job in jobs:
            job.status = JobStatus.CANCELLED
        if jobs:
            await self.session.flush()
        return len(jobs)

    async def status_counts(self) -> dict[str, int]:
        stmt = select(Job.status, func.count()).group_by(Job.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def kind_counts(self) -> dict[str, int]:
        stmt = select(Job.kind, func.count()).group_by(Job.kind)
        rows = (await self.session.execute(stmt)).all()
        return {str(kind): int(count) for kind, count in rows}

    async def failed_since(self, since: datetime, limit: int = 20) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.FAILED)
            .where(Job.completed_at.is_not(None))
            .where(Job.completed_at >= since)
            .order_by(Job.completed_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def oldest_pending_at(self) -> datetime | None:
        stmt = select(func.min(Job.scheduled_at)).where(
            or_(Job.status == JobStatus.PENDING, Job.status == JobStatus.SCHEDULED)
        )
        value = (await self.session.execute(stmt)).scalar_one_or_none()
        return value
