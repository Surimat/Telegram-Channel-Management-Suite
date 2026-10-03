"""Bot repository: the only module that queries the ``bots`` table."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.bot import Bot, BotKind


class BotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, bot: Bot) -> Bot:
        self.session.add(bot)
        await self.session.flush()
        return bot

    async def get(self, bot_id: str) -> Bot | None:
        return await self.session.get(Bot, bot_id)

    async def get_by_telegram_id(self, telegram_id: int) -> Bot | None:
        result = await self.session.execute(
            select(Bot).where(Bot.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_manager(self) -> Bot | None:
        """Return the (single) manager bot, if configured."""
        result = await self.session.execute(
            select(Bot).where(Bot.kind == BotKind.MANAGER).order_by(Bot.created_at)
        )
        return result.scalars().first()

    async def list(
        self,
        *,
        kind: BotKind | None = None,
        enabled: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[Bot], int]:
        stmt = select(Bot)
        count_stmt = select(func.count()).select_from(Bot)
        for cond in (
            (Bot.kind == kind) if kind is not None else None,
            (Bot.enabled == enabled) if enabled is not None else None,
        ):
            if cond is not None:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(Bot.kind, Bot.username).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def delete(self, bot: Bot) -> None:
        await self.session.delete(bot)
        await self.session.flush()

    async def count_by_kind(self) -> dict[str, int]:
        stmt = select(Bot.kind, func.count()).group_by(Bot.kind)
        rows = (await self.session.execute(stmt)).all()
        return {str(kind): int(count) for kind, count in rows}
