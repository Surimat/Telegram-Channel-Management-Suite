"""Invite repositories (PHASE 6): the only modules that query invite tables.

Kept query-focused so :class:`~backend.app.services.invite_service.InviteService`
stays free of SQLAlchemy specifics. Tasks are claimed and updated one bounded
batch at a time so the queue is restart-safe on a weak machine.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.invite import (
    TERMINAL_INVITE_STATUSES,
    InviteJob,
    InviteJobStatus,
    InviteStatus,
    InviteTask,
)


def _enum_value(enum_cls, raw: object) -> str:
    text = str(raw)
    member = enum_cls.__members__.get(text)
    return member.value if member is not None else text.lower()


class InviteJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, job: InviteJob) -> InviteJob:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: str) -> InviteJob | None:
        return await self.session.get(InviteJob, job_id)

    async def list(
        self,
        *,
        status: InviteJobStatus | None = None,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InviteJob], int]:
        stmt = select(InviteJob)
        count_stmt = select(func.count()).select_from(InviteJob)
        conditions = []
        if status is not None:
            conditions.append(InviteJob.status == status)
        if search:
            like = f"%{search.lower()}%"
            conditions.append(
                func.lower(InviteJob.name).like(like)
                | func.lower(InviteJob.target).like(like)
            )
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(InviteJob.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(InviteJob.status, func.count()).group_by(InviteJob.status)
        rows = (await self.session.execute(stmt)).all()
        return {_enum_value(InviteJobStatus, k): int(v) for k, v in rows}

    async def active(self) -> list[InviteJob]:
        """Jobs that are mid-flight and should be recovered on restart."""
        stmt = select(InviteJob).where(
            InviteJob.status.in_([InviteJobStatus.RUNNING, InviteJobStatus.READY])
        )
        return list((await self.session.execute(stmt)).scalars().all())


class InviteTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, tasks: list[InviteTask]) -> None:
        if tasks:
            self.session.add_all(tasks)
            await self.session.flush()

    async def get(self, task_id: str) -> InviteTask | None:
        return await self.session.get(InviteTask, task_id)

    async def list_for_job(
        self,
        job_id: str,
        *,
        status: InviteStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InviteTask], int]:
        stmt = select(InviteTask).where(InviteTask.job_id == job_id)
        count_stmt = select(func.count()).select_from(InviteTask).where(
            InviteTask.job_id == job_id
        )
        if status is not None:
            stmt = stmt.where(InviteTask.status == status)
            count_stmt = count_stmt.where(InviteTask.status == status)
        stmt = stmt.order_by(InviteTask.created_at.asc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def claim_batch(
        self, job_id: str, *, limit: int, now: datetime
    ) -> list[InviteTask]:
        """Atomically claim up to ``limit`` pending, due tasks for ``job_id``."""
        sub = (
            select(InviteTask.id)
            .where(
                InviteTask.job_id == job_id,
                InviteTask.status == InviteStatus.PENDING,
                (InviteTask.scheduled_at.is_(None)) | (InviteTask.scheduled_at <= now),
            )
            .order_by(InviteTask.created_at.asc())
            .limit(limit)
            .scalar_subquery()
        )
        await self.session.execute(
            update(InviteTask)
            .where(InviteTask.id.in_(sub))
            .values(status=InviteStatus.RUNNING)
        )
        await self.session.flush()
        stmt = select(InviteTask).where(
            InviteTask.job_id == job_id,
            InviteTask.status == InviteStatus.RUNNING,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def status_counts(self, job_id: str) -> dict[str, int]:
        stmt = (
            select(InviteTask.status, func.count())
            .where(InviteTask.job_id == job_id)
            .group_by(InviteTask.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {_enum_value(InviteStatus, k): int(v) for k, v in rows}

    async def pending_count(self, job_id: str) -> int:
        stmt = select(func.count()).select_from(InviteTask).where(
            InviteTask.job_id == job_id,
            InviteTask.status == InviteStatus.PENDING,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def unfinished_count(self, job_id: str) -> int:
        """Tasks not yet in a terminal status (still actionable)."""
        terminal = list(TERMINAL_INVITE_STATUSES)
        stmt = select(func.count()).select_from(InviteTask).where(
            InviteTask.job_id == job_id,
            InviteTask.status.not_in(terminal),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def next_due(self, job_id: str, now: datetime) -> InviteTask | None:
        stmt = (
            select(InviteTask)
            .where(
                InviteTask.job_id == job_id,
                InviteTask.status == InviteStatus.PENDING,
                (InviteTask.scheduled_at.is_(None)) | (InviteTask.scheduled_at <= now),
            )
            .order_by(InviteTask.scheduled_at.asc().nullsfirst())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def retry_failed(self, job_id: str) -> int:
        """Reset failed/pending-safe tasks back to pending for a manual retry."""
        stmt = (
            update(InviteTask)
            .where(
                InviteTask.job_id == job_id,
                InviteTask.status.in_([InviteStatus.FAILED, InviteStatus.FLOOD_WAIT]),
            )
            .values(status=InviteStatus.PENDING, error="", wait_until=None)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)


__all__ = ["InviteJobRepository", "InviteTaskRepository"]
