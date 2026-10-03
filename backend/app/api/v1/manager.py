"""Manager-bot runtime router (post-1.0 hardening).

Exposes the manager-bot status and notification toggles to the Web UI / Mini App.
Secrets are never returned; only the bot username and health are shown.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.app.api.deps import get_manager_service
from backend.app.api.schemas.manager import (
    ManagerStatusOut,
    NotificationCategoryOut,
    NotificationSettingsIn,
    NotificationSettingsOut,
)
from backend.app.manager.bus import CATEGORIES, CATEGORY_LABELS, get_notification_bus
from backend.app.manager.service import ManagerBotService, manager_bot_status_label

router = APIRouter(prefix="/manager", tags=["manager"])


def _runtime_running(request: Request) -> bool:
    runtime = getattr(request.app.state, "manager_runtime", None)
    return bool(runtime is not None and getattr(runtime, "running", False))


@router.get("/status", response_model=ManagerStatusOut)
async def manager_status(
    request: Request,
    service: ManagerBotService = Depends(get_manager_service),
) -> ManagerStatusOut:
    manager = await service.bots.get_manager()
    connected = manager is not None and manager.enabled and manager.has_token
    health = manager.health.value if manager else "unknown"
    if connected and manager is not None:
        label = manager_bot_status_label(health)
    elif manager is not None and not manager.enabled:
        label = "выключен"
    else:
        label = "не подключён"
    return ManagerStatusOut(
        connected=connected,
        runtime_running=_runtime_running(request),
        username=manager.username if manager else "",
        health=health,
        status_label=label,
        admin_count=len(service.settings.admin_ids),
        notifications_enabled=await service.notifications_enabled(),
        pending_notifications=get_notification_bus().pending,
        how_to_fix=(
            ""
            if connected
            else "Добавьте управляющего бота в разделе «Боты», чтобы получать "
            "уведомления и управлять системой из Telegram."
        ),
    )


@router.get("/notifications", response_model=NotificationSettingsOut)
async def notification_settings(
    service: ManagerBotService = Depends(get_manager_service),
) -> NotificationSettingsOut:
    data = await service.notification_settings()
    return NotificationSettingsOut(
        enabled=bool(data["enabled"]),
        categories=[
            NotificationCategoryOut(
                key=c, label=CATEGORY_LABELS[c], enabled=bool(data["categories"][c])
            )
            for c in CATEGORIES
        ],
    )


@router.put("/notifications", response_model=NotificationSettingsOut)
async def update_notification_settings(
    payload: NotificationSettingsIn,
    service: ManagerBotService = Depends(get_manager_service),
) -> NotificationSettingsOut:
    data = await service.update_notification_settings(
        enabled=payload.enabled, categories=payload.categories
    )
    return NotificationSettingsOut(
        enabled=bool(data["enabled"]),
        categories=[
            NotificationCategoryOut(
                key=c, label=CATEGORY_LABELS[c], enabled=bool(data["categories"][c])
            )
            for c in CATEGORIES
        ],
    )
