"""Capability graph router (v1.5).

Exposes one machine-readable view of what the product can do and what each
capability requires for the current install. The Promotion Wizard, the Dashboard
and the Diagnostics page read this instead of each re-deriving "does this need a
session?" from their own logic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.capability import CapabilityStateOut
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_session
from backend.app.services.capability_graph import context_from_db, evaluate_all

router = APIRouter(prefix="/capability-graph", tags=["capabilities"])


@router.get("", response_model=list[CapabilityStateOut])
async def capability_graph(
    language: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[CapabilityStateOut]:
    lang = language or settings.app_language
    context = await context_from_db(session)
    states = evaluate_all(context, lang)
    return [
        CapabilityStateOut(
            key=s.key,
            title=s.title,
            state=s.state,
            state_label=s.state_label,
            requires=s.requires,
            satisfied=s.satisfied,
            missing=s.missing,
            missing_fixes=s.missing_fixes,
            note=s.note,
        )
        for s in states
    ]


__all__ = ["router"]
