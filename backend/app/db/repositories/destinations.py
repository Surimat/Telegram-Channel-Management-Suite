"""Repository for backup destinations and update state."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.backup_destination import (
    BackupDestination,
    DestinationKind,
)
from backend.app.db.models.update_state import UpdateState


class DestinationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, destination: BackupDestination) -> BackupDestination:
        self.session.add(destination)
        await self.session.flush()
        return destination

    async def get(self, destination_id: str) -> BackupDestination | None:
        return await self.session.get(BackupDestination, destination_id)

    async def find_by_kind(self, kind: DestinationKind) -> BackupDestination | None:
        result = await self.session.execute(
            select(BackupDestination).where(BackupDestination.kind == kind)
        )
        return result.scalars().first()

    async def list_all(self) -> list[BackupDestination]:
        stmt = select(BackupDestination).order_by(BackupDestination.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, destination: BackupDestination) -> None:
        await self.session.delete(destination)
        await self.session.flush()


class UpdateStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> UpdateState | None:
        result = await self.session.execute(
            select(UpdateState).order_by(UpdateState.created_at.desc())
        )
        return result.scalars().first()

    async def get_or_create(self) -> UpdateState:
        existing = await self.get()
        if existing is not None:
            return existing
        row = UpdateState()
        self.session.add(row)
        await self.session.flush()
        return row
