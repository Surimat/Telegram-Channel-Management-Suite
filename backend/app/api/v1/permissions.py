"""Permission-probe router (post-1.0 hardening).

Lets the operator check whether a Telegram account can actually work with a
channel. Read-only and separate from the Invite Manager (see docs/API.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_permission_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.permissions import (
    PermissionCheckIn,
    PermissionHistoryOut,
    PermissionResultOut,
)
from backend.app.services.permission_service import (
    PermissionService,
    PermissionServiceError,
)

router = APIRouter(prefix="/permissions", tags=["permissions"])


def _raise(exc: PermissionServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


@router.post("/check", response_model=PermissionResultOut)
async def check_permissions(
    payload: PermissionCheckIn,
    service: PermissionService = Depends(get_permission_service),
) -> PermissionResultOut:
    """Probe one account's access to one channel and return the honest result."""
    try:
        result = await service.check(
            payload.account_id,
            payload.target,
            registry_channel_id=payload.channel_id,
        )
    except PermissionServiceError as exc:
        _raise(exc)
    return PermissionResultOut.from_result(result)


@router.get("/latest", response_model=PermissionResultOut | None)
async def latest_permission(
    service: PermissionService = Depends(get_permission_service),
) -> PermissionResultOut | None:
    result = await service.latest()
    return PermissionResultOut.from_result(result) if result else None


@router.get("/history", response_model=PermissionHistoryOut)
async def permission_history(
    limit: int = Query(default=20, ge=1, le=100),
    service: PermissionService = Depends(get_permission_service),
) -> PermissionHistoryOut:
    items = await service.history(limit=limit)
    latest = items[0] if items else None
    return PermissionHistoryOut(
        items=[PermissionResultOut.from_result(r) for r in items],
        latest=PermissionResultOut.from_result(latest) if latest else None,
    )
