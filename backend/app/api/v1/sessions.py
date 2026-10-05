"""Sessions router: MTProto user accounts / Session Manager (PHASE 4).

All endpoints return friendly RU errors and never expose session contents, API
hashes or full phone numbers (decisions D-010, D-025).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_session_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.sessions import (
    AccountIdentityOut,
    AuthCodeIn,
    AuthPasswordIn,
    AuthStartIn,
    AuthStartOut,
    AuthStepOut,
    ImportDetectOut,
    SessionHealthOut,
    SessionImportArtifactIn,
    SessionImportIn,
    SessionImportResultOut,
    SessionOut,
    SessionRiskOut,
    SessionSummary,
)
from backend.app.services.session_import import (
    FORMAT_TITLES,
    STATE_TITLES,
    SessionImportRequest,
)
from backend.app.services.session_service import SessionService, SessionServiceError

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _raise(exc: SessionServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _identity_out(identity) -> AccountIdentityOut | None:  # type: ignore[no-untyped-def]
    if identity is None:
        return None
    return AccountIdentityOut(
        id=identity.id,
        username=identity.username,
        first_name=identity.first_name,
        last_name=identity.last_name,
        display_name=identity.display_name,
    )


def _out(service: SessionService, account) -> SessionOut:  # type: ignore[no-untyped-def]
    info = service.session_file_info(account)
    return SessionOut.from_model(account, file_exists=info.exists, file_size=info.size_bytes)


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    status: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    service: SessionService = Depends(get_session_service),
) -> list[SessionOut]:
    accounts = await service.list_accounts(enabled=enabled)
    return [
        _out(service, a)
        for a in accounts
        if status is None or a.status.value == status
    ]


@router.get("/summary", response_model=SessionSummary)
async def sessions_summary(
    service: SessionService = Depends(get_session_service),
) -> SessionSummary:
    return SessionSummary(**await service.summary())


# --- authorization wizard ----------------------------------------------------
@router.post("/auth/start", response_model=AuthStartOut)
async def auth_start(
    payload: AuthStartIn, service: SessionService = Depends(get_session_service)
) -> AuthStartOut:
    try:
        result = await service.start_auth(
            api_id=payload.api_id,
            api_hash=payload.api_hash,
            phone=payload.phone,
            display_name=payload.display_name,
        )
    except SessionServiceError as exc:
        _raise(exc)
    return AuthStartOut(
        account_id=result.account_id,
        next_step=result.next_step,
        message=result.message,
        how_to_fix=result.how_to_fix,
        phone_masked=result.phone_masked,
    )


@router.post("/{account_id}/code", response_model=AuthStepOut)
async def auth_code(
    account_id: str, payload: AuthCodeIn, service: SessionService = Depends(get_session_service)
) -> AuthStepOut:
    try:
        result = await service.submit_code(account_id, payload.code)
    except SessionServiceError as exc:
        _raise(exc)
    return AuthStepOut(
        account_id=result.account_id,
        next_step=result.next_step,
        done=result.done,
        message=result.message,
        how_to_fix=result.how_to_fix,
        identity=_identity_out(result.identity),
    )


@router.post("/{account_id}/password", response_model=AuthStepOut)
async def auth_password(
    account_id: str,
    payload: AuthPasswordIn,
    service: SessionService = Depends(get_session_service),
) -> AuthStepOut:
    try:
        result = await service.submit_password(account_id, payload.password)
    except SessionServiceError as exc:
        _raise(exc)
    return AuthStepOut(
        account_id=result.account_id,
        next_step=result.next_step,
        done=result.done,
        message=result.message,
        how_to_fix=result.how_to_fix,
        identity=_identity_out(result.identity),
    )


@router.get("/{account_id}", response_model=SessionOut)
async def get_session(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> SessionOut:
    account = await service.get(account_id)
    if account is None:
        raise ApiError(404, "Аккаунт не найден.", "Обновите список аккаунтов.")
    return _out(service, account)


@router.post("/import", response_model=SessionOut, status_code=201)
async def import_session(
    payload: SessionImportIn, service: SessionService = Depends(get_session_service)
) -> SessionOut:
    try:
        account = await service.import_session(
            api_id=payload.api_id,
            api_hash=payload.api_hash,
            phone=payload.phone,
            session_file=Path(payload.session_file_path),
            display_name=payload.display_name,
        )
    except SessionServiceError as exc:
        _raise(exc)
    return _out(service, account)


@router.post("/import/detect", response_model=ImportDetectOut)
async def detect_import(
    payload: SessionImportArtifactIn, service: SessionService = Depends(get_session_service)
) -> ImportDetectOut:
    """Detect an import artifact's format/state without importing it."""
    request = SessionImportRequest(
        path=Path(payload.path) if payload.path else None,
        string_session=payload.string_session,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
        phone=payload.phone,
        display_name=payload.display_name,
    )
    result = await service.detect_import(request)
    return ImportDetectOut(
        format=result.format,
        format_title=FORMAT_TITLES.get(result.format, result.format),
        state=result.state,
        state_title=STATE_TITLES.get(result.state, result.state),
        available=result.available,
        message=result.message,
        how_to_fix=result.how_to_fix,
        notes=result.notes,
    )


@router.post("/import/artifact", response_model=SessionImportResultOut, status_code=201)
async def import_artifact(
    payload: SessionImportArtifactIn, service: SessionService = Depends(get_session_service)
) -> SessionImportResultOut:
    """Import a local .session / +JSON / StringSession / TDATA artifact."""
    request = SessionImportRequest(
        path=Path(payload.path) if payload.path else None,
        string_session=payload.string_session,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
        phone=payload.phone,
        display_name=payload.display_name,
    )
    try:
        account, result = await service.import_artifact(request)
    except SessionServiceError as exc:
        _raise(exc)
    return SessionImportResultOut(
        account=_out(service, account),
        format=result.format,
        format_title=FORMAT_TITLES.get(result.format, result.format),
        notes=result.notes,
        message=result.message,
    )


@router.get("/{account_id}/risk", response_model=SessionRiskOut)
async def account_risk(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> SessionRiskOut:
    account = await service.get(account_id)
    if account is None:
        raise ApiError(404, "Аккаунт не найден.", "Обновите список аккаунтов.")
    return SessionRiskOut(**service.risk_for(account))


@router.post("/{account_id}/health", response_model=SessionHealthOut)
async def check_health(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> SessionHealthOut:
    try:
        account = await service.health_check(account_id)
    except SessionServiceError as exc:
        _raise(exc)
    return SessionHealthOut(
        account_id=account.id,
        ok=account.status.value == "online",
        status=account.status.value,
        message=account.status_message,
        how_to_fix=account.status_hint,
    )


@router.post("/{account_id}/enable", response_model=SessionOut)
async def enable_session(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> SessionOut:
    try:
        account = await service.set_enabled(account_id, True)
    except SessionServiceError as exc:
        _raise(exc)
    return _out(service, account)


@router.post("/{account_id}/disable", response_model=SessionOut)
async def disable_session(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> SessionOut:
    try:
        account = await service.set_enabled(account_id, False)
    except SessionServiceError as exc:
        _raise(exc)
    return _out(service, account)


@router.post("/{account_id}/logout", response_model=SessionOut)
async def logout_session(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> SessionOut:
    try:
        account = await service.logout(account_id)
    except SessionServiceError as exc:
        _raise(exc)
    return _out(service, account)


@router.delete("/{account_id}", status_code=204)
async def delete_session(
    account_id: str, service: SessionService = Depends(get_session_service)
) -> None:
    try:
        await service.delete_account(account_id)
    except SessionServiceError as exc:
        _raise(exc)
