"""User-session repository: the only module that queries ``user_sessions``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.session import SessionStatus, UserSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, account: UserSession) -> UserSession:
        self.session.add(account)
        await self.session.flush()
        return account

    async def get(self, account_id: str) -> UserSession | None:
        return await self.session.get(UserSession, account_id)

    async def get_by_telegram_id(self, telegram_user_id: int) -> UserSession | None:
        result = await self.session.execute(
            select(UserSession).where(UserSession.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        status: SessionStatus | None = None,
        enabled: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[UserSession], int]:
        stmt = select(UserSession)
        count_stmt = select(func.count()).select_from(UserSession)
        for cond in (
            (UserSession.status == status) if status is not None else None,
            (UserSession.enabled == enabled) if enabled is not None else None,
        ):
            if cond is not None:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(UserSession.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def delete(self, account: UserSession) -> None:
        await self.session.delete(account)
        await self.session.flush()

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(UserSession.status, func.count()).group_by(UserSession.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(UserSession))
        return int(result.scalar_one())
