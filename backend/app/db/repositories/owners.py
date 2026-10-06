"""Repositories for the owner identity and the config-sync state."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.config_sync import ConfigSyncState
from backend.app.db.models.owner import OwnerIdentity


class OwnerRepository:
    """Access to the single owner identity row."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, owner: OwnerIdentity) -> OwnerIdentity:
        self.session.add(owner)
        await self.session.flush()
        return owner

    async def get(self, owner_id: str) -> OwnerIdentity | None:
        return await self.session.get(OwnerIdentity, owner_id)

    async def get_single(self) -> OwnerIdentity | None:
        stmt = select(OwnerIdentity).order_by(OwnerIdentity.created_at)
        return (await self.session.execute(stmt)).scalars().first()

    async def delete(self, owner: OwnerIdentity) -> None:
        await self.session.delete(owner)
        await self.session.flush()


class ConfigSyncRepository:
    """Access to the single config-sync state row."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_single(self) -> ConfigSyncState | None:
        stmt = select(ConfigSyncState).order_by(ConfigSyncState.created_at)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_or_create(self) -> ConfigSyncState:
        state = await self.get_single()
        if state is None:
            state = ConfigSyncState()
            self.session.add(state)
            await self.session.flush()
        return state


__all__ = ["ConfigSyncRepository", "OwnerRepository"]
