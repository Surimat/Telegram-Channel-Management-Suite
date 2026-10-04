"""Repository for channel reaction capabilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.capability import ChannelCapabilities


class CapabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, channel_id: str) -> ChannelCapabilities | None:
        result = await self.session.execute(
            select(ChannelCapabilities).where(ChannelCapabilities.channel_id == channel_id)
        )
        return result.scalars().first()

    async def upsert(self, channel_id: str) -> ChannelCapabilities:
        existing = await self.get(channel_id)
        if existing is not None:
            return existing
        row = ChannelCapabilities(channel_id=channel_id)
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete_for_channel(self, channel_id: str) -> None:
        row = await self.get(channel_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()

    async def list_all(self) -> list[ChannelCapabilities]:
        result = await self.session.execute(
            select(ChannelCapabilities).order_by(ChannelCapabilities.channel_id)
        )
        return list(result.scalars().all())
