"""Proxies router (v1.1: connection routes).

Owner-facing CRUD, an honest reachability check and account binding. The response
always states that a proxy does not lift Telegram limits. No password or secret
is ever returned.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.errors import ApiError
from backend.app.api.schemas.proxies import (
    BindAccountIn,
    BindResultOut,
    ProxyCheckOut,
    ProxyIn,
    ProxyListOut,
    ProxyOut,
    ProxyUpdateIn,
)
from backend.app.db.session import get_session
from backend.app.services.proxy_service import (
    NO_BYPASS_NOTICE,
    ProxyService,
    ProxyServiceError,
    ProxyView,
)

router = APIRouter(prefix="/proxies", tags=["proxies"])


def _service(session: AsyncSession) -> ProxyService:
    return ProxyService(session)


def _out(view: ProxyView) -> ProxyOut:
    return ProxyOut(**view.to_dict())


def _raise(exc: ProxyServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


@router.get("", response_model=ProxyListOut)
async def list_proxies(session: AsyncSession = Depends(get_session)) -> ProxyListOut:
    views = await _service(session).list_profiles()
    return ProxyListOut(items=[_out(v) for v in views], notice=NO_BYPASS_NOTICE)


@router.post("", response_model=ProxyOut, status_code=201)
async def create_proxy(
    payload: ProxyIn, session: AsyncSession = Depends(get_session)
) -> ProxyOut:
    service = _service(session)
    try:
        profile = await service.create(
            name=payload.name,
            kind=payload.kind,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password,
            enabled=payload.enabled,
        )
    except ProxyServiceError as exc:
        _raise(exc)
    return _out(service._view(profile))


@router.put("/{profile_id}", response_model=ProxyOut)
async def update_proxy(
    profile_id: str, payload: ProxyUpdateIn, session: AsyncSession = Depends(get_session)
) -> ProxyOut:
    service = _service(session)
    try:
        profile = await service.update(
            profile_id,
            name=payload.name,
            kind=payload.kind,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password,
            enabled=payload.enabled,
        )
    except ProxyServiceError as exc:
        _raise(exc)
    return _out(service._view(profile))


@router.delete("/{profile_id}", status_code=204)
async def delete_proxy(
    profile_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await _service(session).delete(profile_id)
    except ProxyServiceError as exc:
        _raise(exc)


@router.post("/{profile_id}/check", response_model=ProxyCheckOut)
async def check_proxy(
    profile_id: str, session: AsyncSession = Depends(get_session)
) -> ProxyCheckOut:
    try:
        result = await _service(session).check(profile_id)
    except ProxyServiceError as exc:
        _raise(exc)
    return ProxyCheckOut(**result.to_dict())


@router.post("/bind", response_model=BindResultOut)
async def bind_account(
    payload: BindAccountIn, session: AsyncSession = Depends(get_session)
) -> BindResultOut:
    try:
        account = await _service(session).bind_account(payload.account_id, payload.profile_id)
    except ProxyServiceError as exc:
        _raise(exc)
    return BindResultOut(account_id=account.id, proxy_id=account.proxy_id)


__all__ = ["router"]
