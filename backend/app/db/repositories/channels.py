"""Channel repository: the only module that queries the ``channels`` table."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.channel import Channel, ChannelStatus


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, channel: Channel) -> Channel:
        self.session.add(channel)
        await self.session.flush()
        return channel

    async def get(self, channel_id: str) -> Channel | None:
        return await self.session.get(Channel, channel_id)

    async def find_by_reference(self, reference: str) -> Channel | None:
        """Return a channel matching a stored reference (case-insensitive)."""
        value = (reference or "").strip().lower()
        if not value:
            return None
        result = await self.session.execute(
            select(Channel).where(func.lower(Channel.reference) == value)
        )
        return result.scalars().first()

    async def find_by_telegram_id(self, telegram_id: int) -> Channel | None:
        result = await self.session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        return result.scalars().first()

    async def find_by_username(self, username: str) -> Channel | None:
        value = (username or "").strip().lstrip("@").lower()
        if not value:
            return None
        result = await self.session.execute(
            select(Channel).where(func.lower(Channel.username) == value)
        )
        return result.scalars().first()

    async def list(
        self,
        *,
        status: ChannelStatus | None = None,
        search: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[Channel], int]:
        stmt = select(Channel)
        count_stmt = select(func.count()).select_from(Channel)

        conditions = []
        if status is not None:
            conditions.append(Channel.status == status)
        term = (search or "").strip()
        if term:
            pattern = f"%{term.lower()}%"
            conditions.append(
                or_(
                    func.lower(Channel.reference).like(pattern),
                    func.lower(Channel.title).like(pattern),
                    func.lower(Channel.username).like(pattern),
                )
            )
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        # Default channel first, then most recently verified.
        stmt = (
            stmt.order_by(Channel.is_default.desc(), Channel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def get_default(self) -> Channel | None:
        result = await self.session.execute(
            select(Channel).where(Channel.is_default.is_(True)).order_by(Channel.created_at)
        )
        return result.scalars().first()

    async def clear_default(self, *, except_id: str | None = None) -> None:
        """Unset ``is_default`` on every channel except the given one."""
        result = await self.session.execute(select(Channel).where(Channel.is_default.is_(True)))
        for channel in result.scalars().all():
            if channel.id != except_id:
                channel.is_default = False
        await self.session.flush()

    async def delete(self, channel: Channel) -> None:
        await self.session.delete(channel)
        await self.session.flush()

    async def count(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(Channel))).scalar_one()
        )
