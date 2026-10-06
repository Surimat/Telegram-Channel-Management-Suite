"""Aggregate all v1 routers into a single router."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import (
    ai,
    analytics,
    audience,
    backup,
    bindings,
    bot_factory,
    bots,
    campaigns,
    channels,
    content,
    diagnostics,
    discovery,
    editorial,
    events,
    help,
    invites,
    manager,
    mesh,
    miniapp,
    notifications,
    permissions,
    product,
    proxies,
    queue,
    reactions,
    sessions,
    settings,
    system,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(help.router)
api_router.include_router(diagnostics.router)
api_router.include_router(settings.router)
api_router.include_router(bots.router)
api_router.include_router(bot_factory.router)
api_router.include_router(channels.router)
api_router.include_router(content.router)
api_router.include_router(editorial.router)
api_router.include_router(bindings.router)
api_router.include_router(bindings.capabilities_router)
api_router.include_router(manager.router)
api_router.include_router(notifications.router)
api_router.include_router(sessions.router)
api_router.include_router(proxies.router)
api_router.include_router(audience.router)
api_router.include_router(invites.router)
api_router.include_router(campaigns.router)
api_router.include_router(campaigns.donors_router)
api_router.include_router(discovery.router)
api_router.include_router(reactions.router)
api_router.include_router(permissions.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
api_router.include_router(miniapp.router)
api_router.include_router(mesh.router)
api_router.include_router(backup.router)
api_router.include_router(product.router)
api_router.include_router(events.router)
api_router.include_router(queue.router)

__all__ = ["api_router"]
