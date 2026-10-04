"""Repository for bot↔channel bindings."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.binding import (
    FUNCTION_REACTIONS,
    BindingStatus,
    BotChannelBinding,
)


class BindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, binding: BotChannelBinding) -> BotChannelBinding:
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def get(self, binding_id: str) -> BotChannelBinding | None:
        return await self.session.get(BotChannelBinding, binding_id)

    async def find(
        self, bot_id: str, channel_id: str, function: str = FUNCTION_REACTIONS
    ) -> BotChannelBinding | None:
        result = await self.session.execute(
            select(BotChannelBinding).where(
                BotChannelBinding.bot_id == bot_id,
                BotChannelBinding.channel_id == channel_id,
                BotChannelBinding.function == function,
            )
        )
        return result.scalars().first()

    async def list_for_channel(
        self, channel_id: str, *, function: str | None = None
    ) -> list[BotChannelBinding]:
        stmt = select(BotChannelBinding).where(BotChannelBinding.channel_id == channel_id)
        if function:
            stmt = stmt.where(BotChannelBinding.function == function)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_bot(
        self, bot_id: str, *, function: str | None = None
    ) -> list[BotChannelBinding]:
        stmt = select(BotChannelBinding).where(BotChannelBinding.bot_id == bot_id)
        if function:
            stmt = stmt.where(BotChannelBinding.function == function)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all(self) -> list[BotChannelBinding]:
        stmt = select(BotChannelBinding).order_by(BotChannelBinding.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def ready_bots_for_channel(
        self, channel_id: str, function: str = FUNCTION_REACTIONS
    ) -> list[BotChannelBinding]:
        """Bindings that Telegram confirmed are ready for ``function``."""
        stmt = select(BotChannelBinding).where(
            BotChannelBinding.channel_id == channel_id,
            BotChannelBinding.function == function,
            BotChannelBinding.status == BindingStatus.READY,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, binding: BotChannelBinding) -> None:
        await self.session.delete(binding)
        await self.session.flush()

    async def delete_for_channel(self, channel_id: str) -> int:
        rows = await self.list_for_channel(channel_id)
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(BotChannelBinding.status, func.count()).group_by(BotChannelBinding.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}
