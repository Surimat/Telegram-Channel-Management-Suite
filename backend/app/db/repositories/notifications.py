"""Repositories for the Notification Center (v1.4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.notification import (
    NotificationDelivery,
    NotificationRecord,
    NotificationStatus,
)


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, record: NotificationRecord) -> NotificationRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, notification_id: str) -> NotificationRecord | None:
        return await self.session.get(NotificationRecord, notification_id)

    async def list(
        self,
        *,
        category: str | None = None,
        priority: str | None = None,
        status: NotificationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[NotificationRecord], int]:
        stmt = select(NotificationRecord)
        count_stmt = select(func.count()).select_from(NotificationRecord)
        for cond in (
            (NotificationRecord.category == category) if category else None,
            (NotificationRecord.priority == priority) if priority else None,
            (NotificationRecord.status == status) if status is not None else None,
        ):
            if cond is not None:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
        stmt = (
            stmt.order_by(NotificationRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def recent_by_dedup(
        self, dedup_key: str, since: datetime
    ) -> NotificationRecord | None:
        """Return the most recent notification for a dedup key within a window."""
        if not dedup_key:
            return None
        stmt = (
            select(NotificationRecord)
            .where(NotificationRecord.dedup_key == dedup_key)
            .where(NotificationRecord.created_at >= since)
            .order_by(NotificationRecord.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def due_postponed(self, now: datetime, limit: int = 50) -> list[NotificationRecord]:
        stmt = (
            select(NotificationRecord)
            .where(NotificationRecord.status == NotificationStatus.POSTPONED)
            .where(NotificationRecord.postponed_until.is_not(None))
            .where(NotificationRecord.postponed_until <= now)
            .order_by(NotificationRecord.postponed_until)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def status_counts(self) -> dict[str, int]:
        stmt = select(NotificationRecord.status, func.count()).group_by(
            NotificationRecord.status
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def category_counts(self) -> dict[str, int]:
        stmt = select(NotificationRecord.category, func.count()).group_by(
            NotificationRecord.category
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(category): int(count) for category, count in rows}

    async def delete(self, record: NotificationRecord) -> None:
        await self.session.delete(record)
        await self.session.flush()


class NotificationDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def list_for_notification(
        self, notification_id: str
    ) -> list[NotificationDelivery]:
        stmt = (
            select(NotificationDelivery)
            .where(NotificationDelivery.notification_id == notification_id)
            .order_by(NotificationDelivery.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def failed(self, limit: int = 50) -> list[NotificationDelivery]:
        stmt = (
            select(NotificationDelivery)
            .where(NotificationDelivery.status == NotificationStatus.FAILED)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())


__all__ = ["NotificationDeliveryRepository", "NotificationRepository"]
