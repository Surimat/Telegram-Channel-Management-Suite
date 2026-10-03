"""Analytics router (PHASE 8).

Read-only aggregates over the suite's own data. Every response includes a
plain-language ``summary`` so the Web UI can explain numbers, not just show them.
No secrets or per-person PII are returned (D-010/D-029).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.analytics import (
    AnalyticsOverviewOut,
    AudienceAnalyticsOut,
    ContentAnalyticsOut,
    ReactionsAnalyticsOut,
)
from backend.app.db.session import get_session
from backend.app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

_DAYS = Query(default=30, ge=1, le=365, description="Период в днях (1–365).")
_CHANNEL = Query(
    default="",
    description="ID канала в реестре «Каналы» (пусто — по всем каналам).",
)


@router.get("/overview", response_model=AnalyticsOverviewOut)
async def analytics_overview(
    days: int = _DAYS,
    channel_id: str = _CHANNEL,
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOverviewOut:
    return AnalyticsOverviewOut(
        **await AnalyticsService(session).overview(days=days, channel_id=channel_id or None)
    )


@router.get("/content", response_model=ContentAnalyticsOut)
async def analytics_content(
    days: int = _DAYS,
    channel_id: str = _CHANNEL,
    session: AsyncSession = Depends(get_session),
) -> ContentAnalyticsOut:
    return ContentAnalyticsOut(
        **await AnalyticsService(session).content(days=days, channel_id=channel_id or None)
    )


@router.get("/reactions", response_model=ReactionsAnalyticsOut)
async def analytics_reactions(
    days: int = _DAYS,
    channel_id: str = _CHANNEL,
    session: AsyncSession = Depends(get_session),
) -> ReactionsAnalyticsOut:
    return ReactionsAnalyticsOut(
        **await AnalyticsService(session).reactions(days=days, channel_id=channel_id or None)
    )


@router.get("/audience", response_model=AudienceAnalyticsOut)
async def analytics_audience(
    days: int = _DAYS,
    channel_id: str = _CHANNEL,
    session: AsyncSession = Depends(get_session),
) -> AudienceAnalyticsOut:
    return AudienceAnalyticsOut(
        **await AnalyticsService(session).audience(days=days, channel_id=channel_id or None)
    )


__all__ = ["router"]
