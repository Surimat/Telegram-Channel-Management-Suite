"""Repositories for the Editorial Workspace (v1.4)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.editorial import (
    EditorialAuditEntry,
    EditorialItem,
    EditorialMember,
    EditorialRoom,
    EditorialStatus,
)


class EditorialRoomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, room: EditorialRoom) -> EditorialRoom:
        self.session.add(room)
        await self.session.flush()
        return room

    async def get(self, room_id: str) -> EditorialRoom | None:
        return await self.session.get(EditorialRoom, room_id)

    async def for_channel(self, channel_id: str) -> EditorialRoom | None:
        if not channel_id:
            return None
        stmt = select(EditorialRoom).where(EditorialRoom.channel_id == channel_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def for_group(self, group_chat_id: int) -> EditorialRoom | None:
        stmt = select(EditorialRoom).where(EditorialRoom.group_chat_id == group_chat_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(self) -> list[EditorialRoom]:
        stmt = select(EditorialRoom).order_by(EditorialRoom.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, room: EditorialRoom) -> None:
        await self.session.delete(room)
        await self.session.flush()


class EditorialMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, member: EditorialMember) -> EditorialMember:
        self.session.add(member)
        await self.session.flush()
        return member

    async def get(self, member_id: str) -> EditorialMember | None:
        return await self.session.get(EditorialMember, member_id)

    async def find(self, room_id: str, telegram_user_id: int) -> EditorialMember | None:
        stmt = select(EditorialMember).where(
            EditorialMember.room_id == room_id,
            EditorialMember.telegram_user_id == telegram_user_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_room(self, room_id: str) -> list[EditorialMember]:
        stmt = (
            select(EditorialMember)
            .where(EditorialMember.room_id == room_id)
            .order_by(EditorialMember.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, member: EditorialMember) -> None:
        await self.session.delete(member)
        await self.session.flush()


class EditorialItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, item: EditorialItem) -> EditorialItem:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, item_id: str) -> EditorialItem | None:
        return await self.session.get(EditorialItem, item_id)

    async def find(
        self, room_id: str, content_item_id: str, channel_id: str
    ) -> EditorialItem | None:
        stmt = select(EditorialItem).where(
            EditorialItem.room_id == room_id,
            EditorialItem.content_item_id == content_item_id,
            EditorialItem.channel_id == channel_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_room(
        self, room_id: str, *, status: EditorialStatus | None = None
    ) -> list[EditorialItem]:
        stmt = select(EditorialItem).where(EditorialItem.room_id == room_id)
        if status is not None:
            stmt = stmt.where(EditorialItem.status == status)
        stmt = stmt.order_by(EditorialItem.order_index, EditorialItem.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def next_order_index(self, room_id: str, status: EditorialStatus) -> int:
        stmt = select(func.max(EditorialItem.order_index)).where(
            EditorialItem.room_id == room_id,
            EditorialItem.status == status,
        )
        value = (await self.session.execute(stmt)).scalar_one_or_none()
        return int(value or 0) + 1

    async def status_counts(self, room_id: str) -> dict[str, int]:
        stmt = (
            select(EditorialItem.status, func.count())
            .where(EditorialItem.room_id == room_id)
            .group_by(EditorialItem.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def delete(self, item: EditorialItem) -> None:
        await self.session.delete(item)
        await self.session.flush()


class EditorialAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, entry: EditorialAuditEntry) -> EditorialAuditEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_item(self, item_id: str, limit: int = 50) -> list[EditorialAuditEntry]:
        stmt = (
            select(EditorialAuditEntry)
            .where(EditorialAuditEntry.item_id == item_id)
            .order_by(EditorialAuditEntry.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_room(self, room_id: str, limit: int = 100) -> list[EditorialAuditEntry]:
        stmt = (
            select(EditorialAuditEntry)
            .where(EditorialAuditEntry.room_id == room_id)
            .order_by(EditorialAuditEntry.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


__all__ = [
    "EditorialAuditRepository",
    "EditorialItemRepository",
    "EditorialMemberRepository",
    "EditorialRoomRepository",
]
