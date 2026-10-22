"""Analytics router (PHASE 8).

Read-only aggregates over the suite's own data. Every response includes a
plain-language ``summary`` so the Web UI can explain numbers, not just show them.
No secrets or per-person PII are returned (D-010/D-029).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.analytics import AnalyticsOverviewOut
from backend.app.db.session import get_session
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.channel_modules import MODULE_ANALYTICS, ChannelModuleGuard

router = APIRouter(prefix="/analytics", tags=["analytics"])

_DAYS = Query(default=30, ge=1, le=365, description="Период в днях (1–365).")
_CHANNEL = Query(
    default="",
    description="ID канала в реестре «Каналы» (пусто — по всем каналам).",
)


async def _require_analytics_module(channel_id: str, session: AsyncSession) -> None:
    """Refuse a channel-scoped report when analytics is off for that channel.

    Global aggregates (empty ``channel_id``) stay available. A channel the owner
    removed analytics from returns a friendly 403 instead of silently reporting
    numbers for a module that is supposed to be disconnected (D-124).
    """
    if channel_id:
        await ChannelModuleGuard(session).require(channel_id, MODULE_ANALYTICS)


@router.get("/overview", response_model=AnalyticsOverviewOut)
async def analytics_overview(
    days: int = _DAYS,
    channel_id: str = _CHANNEL,
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOverviewOut:
    await _require_analytics_module(channel_id, session)
    return AnalyticsOverviewOut(
        **await AnalyticsService(session).overview(days=days, channel_id=channel_id or None)
    )


__all__ = ["router"]
