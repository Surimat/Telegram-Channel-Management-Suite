"""Repositories for reaction profiles, rules and jobs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.reaction import (
    ReactionJob,
    ReactionJobStatus,
    ReactionProfile,
    ReactionRule,
)


class ReactionProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, profile: ReactionProfile) -> ReactionProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get(self, profile_id: str) -> ReactionProfile | None:
        return await self.session.get(ReactionProfile, profile_id)

    async def list(self) -> list[ReactionProfile]:
        stmt = select(ReactionProfile).order_by(
            ReactionProfile.is_default.desc(), ReactionProfile.name
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_default(self) -> ReactionProfile | None:
        stmt = (
            select(ReactionProfile)
            .where(ReactionProfile.is_default.is_(True))
            .order_by(ReactionProfile.created_at)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_active(self) -> ReactionProfile | None:
        """The profile the manager currently uses (default, else first enabled)."""
        default = await self.get_default()
        if default is not None and default.enabled:
            return default
        stmt = (
            select(ReactionProfile)
            .where(ReactionProfile.enabled.is_(True))
            .order_by(ReactionProfile.created_at)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def clear_defaults(self, except_id: str = "") -> None:
        stmt = select(ReactionProfile).where(ReactionProfile.is_default.is_(True))
        for profile in (await self.session.execute(stmt)).scalars().all():
            if profile.id != except_id:
                profile.is_default = False
        await self.session.flush()

    async def delete(self, profile: ReactionProfile) -> None:
        await self.session.delete(profile)
        await self.session.flush()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(ReactionProfile)
        return int((await self.session.execute(stmt)).scalar_one())


class ReactionRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, rule: ReactionRule) -> ReactionRule:
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get(self, rule_id: str) -> ReactionRule | None:
        return await self.session.get(ReactionRule, rule_id)

    async def list(self, *, enabled: bool | None = None) -> list[ReactionRule]:
        stmt = select(ReactionRule)
        if enabled is not None:
            stmt = stmt.where(ReactionRule.enabled == enabled)
        stmt = stmt.order_by(
            ReactionRule.priority.desc(), ReactionRule.category, ReactionRule.name
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, rule: ReactionRule) -> None:
        await self.session.delete(rule)
        await self.session.flush()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(ReactionRule)
        return int((await self.session.execute(stmt)).scalar_one())


class ReactionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, job: ReactionJob) -> ReactionJob:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: str) -> ReactionJob | None:
        return await self.session.get(ReactionJob, job_id)

    async def get_by_queue_job(self, queue_job_id: str) -> ReactionJob | None:
        stmt = select(ReactionJob).where(ReactionJob.queue_job_id == queue_job_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def for_post(self, post_id: str) -> list[ReactionJob]:
        stmt = select(ReactionJob).where(ReactionJob.post_id == post_id).order_by(
            ReactionJob.scheduled_at
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list(
        self,
        *,
        status: ReactionJobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ReactionJob], int]:
        stmt = select(ReactionJob)
        count_stmt = select(func.count()).select_from(ReactionJob)
        if status is not None:
            stmt = stmt.where(ReactionJob.status == status)
            count_stmt = count_stmt.where(ReactionJob.status == status)
        stmt = stmt.order_by(ReactionJob.scheduled_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(ReactionJob.status, func.count()).group_by(ReactionJob.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def count_created_since(self, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ReactionJob)
            .where(ReactionJob.created_at >= since)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_completed_since(self, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ReactionJob)
            .where(
                ReactionJob.status == ReactionJobStatus.DONE,
                ReactionJob.completed_at.is_not(None),
                ReactionJob.completed_at >= since,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_failed_since(self, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(ReactionJob)
            .where(
                ReactionJob.status == ReactionJobStatus.FAILED,
                ReactionJob.updated_at >= since,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def recover_stuck_running(self) -> int:
        """Reset reaction jobs stuck RUNNING after a crash back to scheduled."""
        stmt = select(ReactionJob).where(ReactionJob.status == ReactionJobStatus.RUNNING)
        jobs = list((await self.session.execute(stmt)).scalars().all())
        for job in jobs:
            job.status = ReactionJobStatus.SCHEDULED
        if jobs:
            await self.session.flush()
        return len(jobs)

    def now(self) -> datetime:
        return utcnow()
