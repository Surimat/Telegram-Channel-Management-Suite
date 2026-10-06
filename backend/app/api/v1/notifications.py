"""Notification Center router (v1.4).

Exposes the notification history, the per-category routing/toggles, quiet hours
and a "send test" action to the Web UI / Mini App. Secrets are never returned.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_notification_service
from backend.app.api.schemas.notification import (
    NotificationCategoryOut,
    NotificationDashboardOut,
    NotificationListOut,
    NotificationOut,
    NotificationSettingsIn,
    NotificationSettingsOut,
    NotificationTestIn,
)
from backend.app.db.models.notification import (
    NOTIFICATION_DESTINATION_TITLES,
    PRIORITY_TITLES,
    STATUS_TITLES,
    NotificationDestination,
    NotificationPriority,
    NotificationStatus,
)
from backend.app.manager.bus import CATEGORY_LABELS
from backend.app.services.notification_service import NotificationCenterService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notification_out(record) -> NotificationOut:  # type: ignore[no-untyped-def]
    return NotificationOut(
        id=record.id,
        category=record.category,
        category_label=CATEGORY_LABELS.get(record.category, record.category),
        priority=str(record.priority),
        priority_label=PRIORITY_TITLES.get(record.priority, str(record.priority)),
        destination=str(record.destination),
        destination_label=NOTIFICATION_DESTINATION_TITLES.get(
            record.destination, str(record.destination)
        ),
        event_key=record.event_key,
        message=record.message,
        how_to_fix=record.how_to_fix,
        status=str(record.status),
        status_label=STATUS_TITLES.get(record.status, str(record.status)),
        error=record.error,
        aggregate_count=record.aggregate_count,
        read=record.read,
        postponed_until=record.postponed_until.isoformat() if record.postponed_until else "",
        delivered_at=record.delivered_at.isoformat() if record.delivered_at else "",
        created_at=record.created_at.isoformat() if record.created_at else "",
    )


def _settings_out(data) -> NotificationSettingsOut:  # type: ignore[no-untyped-def]
    categories = data.categories
    routing = data.routing
    return NotificationSettingsOut(
        enabled=data.enabled,
        categories=[
            NotificationCategoryOut(
                key=key,
                label=CATEGORY_LABELS.get(key, key),
                enabled=bool(categories.get(key, True)),
                destinations=list(routing.get(key, [])),
            )
            for key in CATEGORY_LABELS
        ],
        quiet_hours_enabled=data.quiet_hours_enabled,
        quiet_hours_start=data.quiet_hours_start,
        quiet_hours_end=data.quiet_hours_end,
        quiet_hours_tz=data.quiet_hours_tz,
        aggregation_enabled=data.aggregation_enabled,
        destinations=[
            {"key": d.value, "label": NOTIFICATION_DESTINATION_TITLES[d]}
            for d in NotificationDestination
        ],
    )


@router.get("/settings", response_model=NotificationSettingsOut)
async def get_settings(
    service: NotificationCenterService = Depends(get_notification_service),
) -> NotificationSettingsOut:
    return _settings_out(await service.load_settings())


@router.put("/settings", response_model=NotificationSettingsOut)
async def update_settings(
    payload: NotificationSettingsIn,
    service: NotificationCenterService = Depends(get_notification_service),
) -> NotificationSettingsOut:
    data = await service.update_settings(
        enabled=payload.enabled,
        categories=payload.categories,
        routing=payload.routing,
        quiet_hours_enabled=payload.quiet_hours_enabled,
        quiet_hours_start=payload.quiet_hours_start,
        quiet_hours_end=payload.quiet_hours_end,
        quiet_hours_tz=payload.quiet_hours_tz,
        aggregation_enabled=payload.aggregation_enabled,
    )
    await service.session.commit()
    return _settings_out(data)


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    category: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: NotificationCenterService = Depends(get_notification_service),
) -> NotificationListOut:
    rows, total = await service.history(
        category=category,
        priority=priority,
        status=status,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return NotificationListOut(items=[_notification_out(r) for r in rows], total=total)


@router.get("/dashboard", response_model=NotificationDashboardOut)
async def dashboard(
    service: NotificationCenterService = Depends(get_notification_service),
) -> NotificationDashboardOut:
    data = await service.dashboard()
    cfg = await service.load_settings()
    return NotificationDashboardOut(
        enabled=bool(data["enabled"]),
        pending=int(data["pending"]),
        failed=int(data["failed"]),
        quiet_hours_enabled=bool(data["quiet_hours_enabled"]),
        in_quiet_hours=service.in_quiet_hours(cfg),
        status_counts={str(k): int(v) for k, v in data["status_counts"].items()},  # type: ignore[union-attr]
        category_counts={str(k): int(v) for k, v in data["category_counts"].items()},  # type: ignore[union-attr]
    )


@router.post("/test", response_model=NotificationOut)
async def send_test(
    payload: NotificationTestIn,
    service: NotificationCenterService = Depends(get_notification_service),
) -> NotificationOut:
    record = await service.send_test(category=payload.category, priority=payload.priority)
    return _notification_out(record)


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: str,
    service: NotificationCenterService = Depends(get_notification_service),
) -> NotificationOut:
    from backend.app.api.errors import ApiError

    record = await service.mark_read(notification_id)
    if record is None:
        raise ApiError(404, "Уведомление не найдено.")
    return _notification_out(record)


#: Referenced so static analysis keeps the enums in this module's import list.
_ENUM_HINT = (NotificationPriority, NotificationStatus)


__all__ = ["router"]
