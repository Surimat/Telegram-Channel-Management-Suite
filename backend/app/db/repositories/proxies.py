"""Repositories for proxy profiles and discovered donor candidates."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.donor_candidate import DonorCandidate
from backend.app.db.models.proxy import ProxyProfile


class ProxyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, profile: ProxyProfile) -> ProxyProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get(self, profile_id: str) -> ProxyProfile | None:
        return await self.session.get(ProxyProfile, profile_id)

    async def list_all(self) -> list[ProxyProfile]:
        stmt = select(ProxyProfile).order_by(ProxyProfile.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(ProxyProfile)
        return int((await self.session.execute(stmt)).scalar_one())

    async def delete(self, profile: ProxyProfile) -> None:
        await self.session.delete(profile)
        await self.session.flush()


class DonorCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, candidate: DonorCandidate) -> DonorCandidate:
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def get(self, candidate_id: str) -> DonorCandidate | None:
        return await self.session.get(DonorCandidate, candidate_id)

    async def find(self, username: str) -> DonorCandidate | None:
        if not username:
            return None
        stmt = select(DonorCandidate).where(DonorCandidate.username == username)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(self, *, provider: str | None = None) -> list[DonorCandidate]:
        stmt = select(DonorCandidate)
        if provider:
            stmt = stmt.where(DonorCandidate.provider == provider)
        stmt = stmt.order_by(DonorCandidate.fit_score.desc(), DonorCandidate.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def clear(self, *, provider: str | None = None) -> int:
        rows = await self.list_all(provider=provider)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)

    async def delete(self, candidate: DonorCandidate) -> None:
        await self.session.delete(candidate)
        await self.session.flush()


__all__ = ["DonorCandidateRepository", "ProxyRepository"]
