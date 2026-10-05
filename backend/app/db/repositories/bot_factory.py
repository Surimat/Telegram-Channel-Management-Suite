"""Repositories for Bot Factory batches and candidates (v1.3)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.bot_factory import BotBatch, BotCandidate


class BotBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, batch: BotBatch) -> BotBatch:
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def get(self, batch_id: str) -> BotBatch | None:
        return await self.session.get(BotBatch, batch_id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> tuple[list[BotBatch], int]:
        stmt = select(BotBatch).order_by(BotBatch.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int(
            (await self.session.execute(select(func.count()).select_from(BotBatch))).scalar_one()
        )
        return rows, total

    async def delete(self, batch: BotBatch) -> None:
        await self.session.delete(batch)
        await self.session.flush()


class BotCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, candidate: BotCandidate) -> BotCandidate:
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def add_many(self, candidates: list[BotCandidate]) -> list[BotCandidate]:
        self.session.add_all(candidates)
        await self.session.flush()
        return candidates

    async def get(self, candidate_id: str) -> BotCandidate | None:
        return await self.session.get(BotCandidate, candidate_id)

    async def list_for_batch(self, batch_id: str) -> list[BotCandidate]:
        stmt = (
            select(BotCandidate)
            .where(BotCandidate.batch_id == batch_id)
            .order_by(BotCandidate.index)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all(self, *, limit: int = 500) -> list[BotCandidate]:
        stmt = select(BotCandidate).order_by(BotCandidate.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_for_batch(self, batch_id: str) -> int:
        rows = await self.list_for_batch(batch_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)


__all__ = ["BotBatchRepository", "BotCandidateRepository"]
