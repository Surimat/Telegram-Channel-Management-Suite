"""Repositories for the mass bot-to-channel onboarding queue (v2.0)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.bot_onboarding import OnboardingBatch, OnboardingCandidate


class OnboardingBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, batch: OnboardingBatch) -> OnboardingBatch:
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def get(self, batch_id: str) -> OnboardingBatch | None:
        return await self.session.get(OnboardingBatch, batch_id)

    async def list_all(
        self, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[OnboardingBatch], int]:
        stmt = (
            select(OnboardingBatch)
            .order_by(OnboardingBatch.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int(
            (
                await self.session.execute(select(func.count()).select_from(OnboardingBatch))
            ).scalar_one()
        )
        return rows, total

    async def delete(self, batch: OnboardingBatch) -> None:
        await self.session.delete(batch)
        await self.session.flush()


class OnboardingCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, candidate: OnboardingCandidate) -> OnboardingCandidate:
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def add_many(
        self, candidates: list[OnboardingCandidate]
    ) -> list[OnboardingCandidate]:
        self.session.add_all(candidates)
        await self.session.flush()
        return candidates

    async def get(self, candidate_id: str) -> OnboardingCandidate | None:
        return await self.session.get(OnboardingCandidate, candidate_id)

    async def list_for_batch(self, batch_id: str) -> list[OnboardingCandidate]:
        stmt = (
            select(OnboardingCandidate)
            .where(OnboardingCandidate.batch_id == batch_id)
            .order_by(OnboardingCandidate.index)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_by_status(self, batch_id: str) -> dict[str, int]:
        stmt = (
            select(OnboardingCandidate.status, func.count())
            .where(OnboardingCandidate.batch_id == batch_id)
            .group_by(OnboardingCandidate.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def delete_for_batch(self, batch_id: str) -> int:
        rows = await self.list_for_batch(batch_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)


__all__ = ["OnboardingBatchRepository", "OnboardingCandidateRepository"]
