"""Owner Auth + Config Sync router (v1.6).

Owner Auth protects the app locally; Config Sync moves an encrypted settings
bundle between computers. Neither ever returns a password, verifier, token or
key. Google Drive is optional and independent of the owner password (D-105/D-106).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.errors import ApiError
from backend.app.api.owner_guard import TOKEN_HEADER, issue_token
from backend.app.api.schemas.owner import (
    ConflictOut,
    OwnerChangeIn,
    OwnerEnabledIn,
    OwnerSecretIn,
    OwnerSetupIn,
    OwnerStatusOut,
    OwnerTokenOut,
    RestorePreviewOut,
    SyncApplyIn,
    SyncConfigureIn,
    SyncGoogleAuthOut,
    SyncGoogleConnectIn,
    SyncSecretIn,
    SyncStatusOut,
)
from backend.app.core import i18n
from backend.app.db.session import get_session
from backend.app.services.config_sync_service import (
    ConfigSyncError_,
    ConfigSyncService,
    generate_state,
)
from backend.app.services.owner_auth_service import OwnerAuthError, OwnerAuthService

router = APIRouter(prefix="/owner", tags=["owner"])


def _status_out(status) -> OwnerStatusOut:  # type: ignore[no-untyped-def]
    data = status.to_dict()
    data["local_only_note"] = i18n.translate("owner.local_only")
    return OwnerStatusOut(**data)


def _sync_out(status) -> SyncStatusOut:  # type: ignore[no-untyped-def]
    data = status.to_dict()
    data["no_live_db_note"] = i18n.translate("sync.no_live_db")
    data["appdata_scope_note"] = i18n.translate("sync.appdata_scope")
    return SyncStatusOut(**data)


def _owner_error(exc: OwnerAuthError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _sync_error(exc: ConfigSyncError_) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


# ---------------------------------------------------------------------------
# Owner Auth
# ---------------------------------------------------------------------------
@router.get("/status", response_model=OwnerStatusOut)
async def owner_status(session: AsyncSession = Depends(get_session)) -> OwnerStatusOut:
    return _status_out(await OwnerAuthService(session).status())


@router.post("/setup", response_model=OwnerTokenOut, status_code=201)
async def owner_setup(
    payload: OwnerSetupIn, session: AsyncSession = Depends(get_session)
) -> OwnerTokenOut:
    service = OwnerAuthService(session)
    try:
        owner = await service.create(
            payload.secret,
            method=payload.method,
            display_name=payload.display_name,
            recovery_hint=payload.recovery_hint,
        )
    except OwnerAuthError as exc:
        _owner_error(exc)
    return OwnerTokenOut(
        token=issue_token(owner.id), status=_status_out(await service.status())
    )


@router.post("/login", response_model=OwnerTokenOut)
async def owner_login(
    payload: OwnerSecretIn, session: AsyncSession = Depends(get_session)
) -> OwnerTokenOut:
    service = OwnerAuthService(session)
    try:
        owner = await service.login(payload.secret)
    except OwnerAuthError as exc:
        _owner_error(exc)
    return OwnerTokenOut(
        token=issue_token(owner.id), status=_status_out(await service.status())
    )


@router.post("/logout", response_model=OwnerStatusOut)
async def owner_logout(session: AsyncSession = Depends(get_session)) -> OwnerStatusOut:
    service = OwnerAuthService(session)
    await service.logout()
    return _status_out(await service.status())


@router.post("/lock", response_model=OwnerStatusOut)
async def owner_lock(session: AsyncSession = Depends(get_session)) -> OwnerStatusOut:
    service = OwnerAuthService(session)
    try:
        return _status_out(await service.lock())
    except OwnerAuthError as exc:
        _owner_error(exc)


@router.post("/unlock", response_model=OwnerTokenOut)
async def owner_unlock(
    payload: OwnerSecretIn, session: AsyncSession = Depends(get_session)
) -> OwnerTokenOut:
    service = OwnerAuthService(session)
    try:
        owner = await service.unlock(payload.secret)
    except OwnerAuthError as exc:
        _owner_error(exc)
    return OwnerTokenOut(
        token=issue_token(owner.id), status=_status_out(await service.status())
    )


@router.post("/protection", response_model=OwnerStatusOut)
async def owner_protection(
    payload: OwnerEnabledIn, session: AsyncSession = Depends(get_session)
) -> OwnerStatusOut:
    service = OwnerAuthService(session)
    try:
        return _status_out(await service.set_enabled(payload.enabled))
    except OwnerAuthError as exc:
        _owner_error(exc)


@router.post("/password", response_model=OwnerStatusOut)
async def owner_change_password(
    payload: OwnerChangeIn, session: AsyncSession = Depends(get_session)
) -> OwnerStatusOut:
    service = OwnerAuthService(session)
    try:
        await service.change_secret(payload.current, payload.new_secret)
    except OwnerAuthError as exc:
        _owner_error(exc)
    return _status_out(await service.status())


@router.delete("/profile", status_code=204)
async def owner_delete(session: AsyncSession = Depends(get_session)) -> None:
    await OwnerAuthService(session).delete()


# ---------------------------------------------------------------------------
# Config Sync
# ---------------------------------------------------------------------------
@router.get("/sync/status", response_model=SyncStatusOut)
async def sync_status(session: AsyncSession = Depends(get_session)) -> SyncStatusOut:
    return _sync_out(await ConfigSyncService(session).status())


@router.post("/sync/configure", response_model=SyncStatusOut)
async def sync_configure(
    payload: SyncConfigureIn, session: AsyncSession = Depends(get_session)
) -> SyncStatusOut:
    try:
        return _sync_out(
            await ConfigSyncService(session).configure(payload.provider, enabled=payload.enabled)
        )
    except ConfigSyncError_ as exc:
        _sync_error(exc)


@router.post("/sync/upload", response_model=SyncStatusOut)
async def sync_upload(
    payload: SyncSecretIn, session: AsyncSession = Depends(get_session)
) -> SyncStatusOut:
    try:
        return _sync_out(await ConfigSyncService(session).upload(payload.secret))
    except ConfigSyncError_ as exc:
        _sync_error(exc)


@router.post("/sync/download/preview", response_model=RestorePreviewOut)
async def sync_download_preview(
    payload: SyncSecretIn, session: AsyncSession = Depends(get_session)
) -> RestorePreviewOut:
    try:
        preview = await ConfigSyncService(session).download_preview(payload.secret)
    except ConfigSyncError_ as exc:
        _sync_error(exc)
    return RestorePreviewOut(**preview.to_dict())


@router.post("/sync/download/apply", response_model=SyncStatusOut)
async def sync_download_apply(
    payload: SyncApplyIn, session: AsyncSession = Depends(get_session)
) -> SyncStatusOut:
    try:
        return _sync_out(
            await ConfigSyncService(session).download_apply(
                payload.secret, keep_local=payload.keep_local
            )
        )
    except ConfigSyncError_ as exc:
        _sync_error(exc)


@router.get("/sync/conflict", response_model=ConflictOut)
async def sync_conflict(session: AsyncSession = Depends(get_session)) -> ConflictOut:
    return ConflictOut(**(await ConfigSyncService(session).conflict()).to_dict())


@router.post("/sync/disconnect", response_model=SyncStatusOut)
async def sync_disconnect(session: AsyncSession = Depends(get_session)) -> SyncStatusOut:
    return _sync_out(await ConfigSyncService(session).disconnect())


@router.get("/sync/google/auth", response_model=SyncGoogleAuthOut)
async def sync_google_auth() -> SyncGoogleAuthOut:
    """Return the Google consent URL for the installed-app loopback flow."""
    from backend.app.core.config import get_settings
    from backend.app.providers.config_sync_gdrive import (
        GoogleOAuthConfig,
        build_authorization_url,
    )

    settings = get_settings()
    config = GoogleOAuthConfig(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        redirect_uri=settings.google_oauth_redirect_uri,
    )
    state = generate_state()
    return SyncGoogleAuthOut(
        configured=config.configured,
        authorization_url=build_authorization_url(config, state) if config.configured else "",
        state=state,
    )


@router.post("/sync/google/connect", response_model=SyncStatusOut)
async def sync_google_connect(
    payload: SyncGoogleConnectIn, session: AsyncSession = Depends(get_session)
) -> SyncStatusOut:
    return _sync_out(
        await ConfigSyncService(session).connect_google(
            payload.access_token, payload.refresh_token
        )
    )


__all__ = ["TOKEN_HEADER", "router"]
