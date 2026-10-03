"""Event (log/error center) repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.event import Event, EventLevel


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: Event) -> Event:
        self.session.add(event)
        await self.session.flush()
        return event

    async def get(self, event_id: str) -> Event | None:
        return await self.session.get(Event, event_id)

    async def list(
        self,
        *,
        level: EventLevel | None = None,
        module: str | None = None,
        resolved: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Event], int]:
        stmt = select(Event)
        count_stmt = select(func.count()).select_from(Event)
        if level is not None:
            stmt = stmt.where(Event.level == level)
            count_stmt = count_stmt.where(Event.level == level)
        if module:
            stmt = stmt.where(Event.module == module)
            count_stmt = count_stmt.where(Event.module == module)
        if resolved is not None:
            stmt = stmt.where(Event.resolved == resolved)
            count_stmt = count_stmt.where(Event.resolved == resolved)

        stmt = stmt.order_by(Event.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def mark_resolved(self, event_id: str) -> Event | None:
        event = await self.get(event_id)
        if event is not None:
            event.resolved = True
            await self.session.flush()
        return event
