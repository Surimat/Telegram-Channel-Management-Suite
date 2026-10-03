"""Events service: the central log / error center.

Provides friendly wrappers that store an event and return human-readable
guidance. Sensitive detail must never be passed in ``details``.

Since the post-1.0 hardening, significant events are also published onto the
in-process notification bus (see :mod:`backend.app.manager.bus`) so the manager
bot can forward them to the owner. Publishing is fire-and-forget and can never
raise into the caller.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.event import Event, EventLevel
from backend.app.db.repositories.events import EventRepository

# Errors and above are always worth forwarding; lifecycle events are published
# explicitly by their call sites (app start/stop, backup created, ...).
_NOTIFIABLE_LEVELS = {EventLevel.ERROR, EventLevel.CRITICAL}


class EventsService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = EventRepository(session)

    async def record(
        self,
        *,
        level: EventLevel,
        module: str,
        message: str,
        explanation: str = "",
        how_to_fix: str = "",
        details: str = "",
        actor: str = "",
        operation: str = "",
        status: str = "",
        notify: bool | None = None,
    ) -> Event:
        event = Event(
            level=level,
            module=module,
            message=message,
            explanation=explanation,
            how_to_fix=how_to_fix,
            details=details,
            actor=actor,
            operation=operation,
            status=status,
        )
        event = await self.repo.add(event)
        if notify is None:
            notify = level in _NOTIFIABLE_LEVELS
        if notify:
            self._publish(module, operation or module, message, level, how_to_fix)
        return event

    @staticmethod
    def _publish(
        module: str, event_key: str, message: str, level: EventLevel, how_to_fix: str
    ) -> None:
        # Imported lazily to avoid a hard import cycle at module load time.
        from backend.app.manager.bus import category_for_module, publish

        publish(
            category=category_for_module(module),
            event_key=event_key,
            message=message,
            level=level.value,
            how_to_fix=how_to_fix,
        )

    async def info(self, module: str, message: str, **kwargs: object) -> Event:
        return await self.record(level=EventLevel.INFO, module=module, message=message, **kwargs)

    async def warning(self, module: str, message: str, **kwargs: object) -> Event:
        return await self.record(level=EventLevel.WARNING, module=module, message=message, **kwargs)

    async def error(self, module: str, message: str, **kwargs: object) -> Event:
        return await self.record(level=EventLevel.ERROR, module=module, message=message, **kwargs)

    async def critical(self, module: str, message: str, **kwargs: object) -> Event:
        return await self.record(
            level=EventLevel.CRITICAL, module=module, message=message, **kwargs
        )

    async def list(
        self,
        *,
        level: EventLevel | None = None,
        module: str | None = None,
        resolved: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Event], int]:
        return await self.repo.list(
            level=level, module=module, resolved=resolved, limit=limit, offset=offset
        )

    async def get(self, event_id: str) -> Event | None:
        return await self.repo.get(event_id)

    async def resolve(self, event_id: str) -> Event | None:
        return await self.repo.mark_resolved(event_id)
