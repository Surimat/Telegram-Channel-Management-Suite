"""Repository for donor metrics."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.donor import DonorMetrics


class DonorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_source(self, source_id: str) -> DonorMetrics | None:
        result = await self.session.execute(
            select(DonorMetrics).where(DonorMetrics.source_id == source_id)
        )
        return result.scalars().first()

    async def upsert(self, source_id: str) -> DonorMetrics:
        existing = await self.get_for_source(source_id)
        if existing is not None:
            return existing
        row = DonorMetrics(source_id=source_id)
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_all(self) -> list[DonorMetrics]:
        stmt = select(DonorMetrics).order_by(DonorMetrics.updated_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())
