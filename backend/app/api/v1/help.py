"""Help router: beginner explanations + the "show explanations" preference.

Read-only catalog served to every client so the Web UI, the Mini App and the
Setup Wizard explain concepts identically. The preference is stored in the
``settings`` table (default: explanations ON).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.help import HelpTopicOut, UiPrefsOut, UiPrefsUpdate
from backend.app.db.session import get_session
from backend.app.services.help_topics import all_topics
from backend.app.services.ui_prefs import UiPrefsService

router = APIRouter(prefix="/help", tags=["help"])


@router.get("/topics", response_model=list[HelpTopicOut])
async def list_help_topics() -> list[HelpTopicOut]:
    """Return every beginner-facing explanation (no secrets, static text)."""
    return [HelpTopicOut(**item) for item in all_topics()]


@router.get("/prefs", response_model=UiPrefsOut)
async def get_prefs(session: AsyncSession = Depends(get_session)) -> UiPrefsOut:
    return UiPrefsOut(**(await UiPrefsService(session).as_dict()))


@router.put("/prefs", response_model=UiPrefsOut)
async def update_prefs(
    payload: UiPrefsUpdate, session: AsyncSession = Depends(get_session)
) -> UiPrefsOut:
    service = UiPrefsService(session)
    if payload.show_explanations is not None:
        await service.set_show_explanations(payload.show_explanations)
    await session.commit()
    return UiPrefsOut(**(await service.as_dict()))
