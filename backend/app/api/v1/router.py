"""Aggregate all v1 routers into a single router."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import (
    ai,
    analytics,
    audience,
    bots,
    events,
    invites,
    miniapp,
    queue,
    reactions,
    sessions,
    settings,
    system,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(settings.router)
api_router.include_router(bots.router)
api_router.include_router(sessions.router)
api_router.include_router(audience.router)
api_router.include_router(invites.router)
api_router.include_router(reactions.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
api_router.include_router(miniapp.router)
api_router.include_router(events.router)
api_router.include_router(queue.router)

__all__ = ["api_router"]
