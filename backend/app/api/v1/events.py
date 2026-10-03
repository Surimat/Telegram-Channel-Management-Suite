"""Events router: log / error center."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.common import Page
from backend.app.api.schemas.events import EventOut
from backend.app.db.models.event import EventLevel
from backend.app.db.session import get_session
from backend.app.services.events_service import EventsService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=Page[EventOut])
async def list_events(
    level: EventLevel | None = None,
    module: str | None = None,
    resolved: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> Page[EventOut]:
    service = EventsService(session)
    offset = (page - 1) * page_size
    rows, total = await service.list(
        level=level, module=module, resolved=resolved, limit=page_size, offset=offset
    )
    return Page[EventOut](
        items=[EventOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: str, session: AsyncSession = Depends(get_session)) -> EventOut:
    service = EventsService(session)
    event = await service.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено.")
    return EventOut.model_validate(event)


@router.post("/{event_id}/resolve", response_model=EventOut)
async def resolve_event(event_id: str, session: AsyncSession = Depends(get_session)) -> EventOut:
    service = EventsService(session)
    event = await service.resolve(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено.")
    await session.commit()
    return EventOut.model_validate(event)
