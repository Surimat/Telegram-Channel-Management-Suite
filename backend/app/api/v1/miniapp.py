"""Mini App authentication endpoints (PHASE 9).

These endpoints only establish *who* the Telegram caller is. All business
endpoints stay in their own routers and are shared with the local Web UI (D-003).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from backend.app.api.deps import get_miniapp_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.miniapp import (
    MiniAppAuthRequest,
    MiniAppAuthResponse,
    MiniAppConfig,
    MiniAppMeResponse,
    MiniAppSetupRequest,
    MiniAppSetupResponse,
    MiniAppUserOut,
)
from backend.app.core.config import get_settings
from backend.app.miniapp.auth import MiniAppAuthError
from backend.app.miniapp.service import MiniAppService
from backend.app.miniapp.sessions import MiniAppSessionError

router = APIRouter(prefix="/miniapp", tags=["miniapp"])

SESSION_COOKIE = "tcms_miniapp"


@router.get("/config", response_model=MiniAppConfig)
async def config(service: MiniAppService = Depends(get_miniapp_service)) -> MiniAppConfig:
    status = await service.status()
    return MiniAppConfig(
        enabled=status.enabled,
        available=status.available,
        bot_username=status.bot_username,
        public_url=status.public_url,
        reason=status.reason,
        how_to_fix=status.how_to_fix,
    )


@router.post("/auth", response_model=MiniAppAuthResponse)
async def authenticate(
    payload: MiniAppAuthRequest,
    response: Response,
    service: MiniAppService = Depends(get_miniapp_service),
) -> MiniAppAuthResponse:
    settings = get_settings()
    try:
        token, user, is_admin = await service.authenticate(payload.init_data)
    except MiniAppAuthError as exc:
        raise ApiError(401, exc.message, exc.hint) from None
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.miniapp_session_ttl,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    return MiniAppAuthResponse(
        authenticated=True,
        is_admin=is_admin,
        user=MiniAppUserOut(
            id=user.id,
            display_name=user.display_name,
            username=user.username,
            language_code=user.language_code,
            photo_url=user.photo_url,
        ),
        expires_in=settings.miniapp_session_ttl,
    )


@router.post("/setup", response_model=MiniAppSetupResponse)
async def setup(
    payload: MiniAppSetupRequest,
    service: MiniAppService = Depends(get_miniapp_service),
) -> MiniAppSetupResponse:
    """Register the Mini App menu button with Telegram (owner action)."""
    result = await service.setup(payload.public_url)
    return MiniAppSetupResponse(
        ok=result.ok, message=result.message, how_to_fix=result.how_to_fix
    )


@router.get("/me", response_model=MiniAppMeResponse)
async def me(
    request: Request,
    service: MiniAppService = Depends(get_miniapp_service),
) -> MiniAppMeResponse:
    raw = request.cookies.get(SESSION_COOKIE, "")
    if not raw:
        return MiniAppMeResponse(authenticated=False)
    try:
        resolved = service.resolve_session(raw)
    except MiniAppSessionError:
        return MiniAppMeResponse(authenticated=False)
    return MiniAppMeResponse(
        authenticated=True,
        is_admin=resolved.is_admin,
        telegram_id=resolved.telegram_id,
        expires_at=resolved.expires_at,
    )


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
