"""Aggregate all v1 routers into a single router."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import events, queue, settings, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(settings.router)
api_router.include_router(events.router)
api_router.include_router(queue.router)

__all__ = ["api_router"]
