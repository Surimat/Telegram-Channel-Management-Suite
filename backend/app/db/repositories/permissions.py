"""Permission-check repository (post-1.0 hardening)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.permission import PermissionCheck


class PermissionCheckRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, check: PermissionCheck) -> PermissionCheck:
        self.session.add(check)
        await self.session.flush()
        return check

    async def get(self, check_id: str) -> PermissionCheck | None:
        return await self.session.get(PermissionCheck, check_id)

    async def latest(self) -> PermissionCheck | None:
        stmt = select(PermissionCheck).order_by(PermissionCheck.created_at.desc()).limit(1)
        return (await self.session.execute(stmt)).scalars().first()

    async def latest_for_account(self, account_id: str) -> PermissionCheck | None:
        stmt = (
            select(PermissionCheck)
            .where(PermissionCheck.account_id == account_id)
            .order_by(PermissionCheck.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_recent(self, limit: int = 20) -> list[PermissionCheck]:
        stmt = select(PermissionCheck).order_by(PermissionCheck.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
