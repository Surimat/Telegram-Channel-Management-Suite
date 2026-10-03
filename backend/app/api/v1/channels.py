"""Channels router: the shared Channel Registry (hardening).

Add → verify → connect modules → health. All endpoints return friendly RU errors
and never expose secrets.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_channel_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.channels import (
    ChannelCreate,
    ChannelListOut,
    ChannelModulesIn,
    ChannelOut,
    ChannelSummaryOut,
    ChannelUpdate,
    ChannelVerificationOut,
    ChannelVerifyIn,
)
from backend.app.db.models.channel import ChannelKind, ChannelStatus
from backend.app.services.channel_service import ChannelService, ChannelServiceError

router = APIRouter(prefix="/channels", tags=["channels"])


def _raise(exc: ChannelServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _to_out(service: ChannelService, channel) -> ChannelOut:  # type: ignore[no-untyped-def]
    modules = {}
    try:
        modules = json.loads(channel.modules or "{}")
    except (ValueError, TypeError):
        modules = {}
    return ChannelOut(
        id=channel.id,
        reference=channel.reference,
        telegram_id=channel.telegram_id,
        username=channel.username,
        title=channel.title,
        kind=str(channel.kind),
        status=str(channel.status),
        is_default=channel.is_default,
        modules={str(k): bool(v) for k, v in modules.items()},
        verification_status=channel.verification_status,
        verification_message=channel.verification_message,
        verification_hint=channel.verification_hint,
        participants_count=channel.participants_count,
        last_verified_at=channel.last_verified_at,
        note=channel.note,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def _parse_status(value: str) -> ChannelStatus:
    try:
        return ChannelStatus(value)
    except ValueError as exc:
        raise ApiError(
            422,
            "Неизвестное состояние канала.",
            "Выберите состояние из списка.",
        ) from exc


def _parse_kind(value: str) -> ChannelKind:
    try:
        return ChannelKind(value)
    except ValueError as exc:
        raise ApiError(
            422,
            "Неизвестный тип канала. Допустимо: channel, group, supergroup, unknown.",
            "Выберите тип из списка.",
        ) from exc


@router.get("", response_model=ChannelListOut)
async def list_channels(
    status: str | None = Query(default=None),
    search: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ChannelService = Depends(get_channel_service),
) -> ChannelListOut:
    channels, total = await service.list_channels(
        status=_parse_status(status) if status else None, search=search
    )
    items = [_to_out(service, c) for c in channels[offset : offset + limit]]
    return ChannelListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=ChannelSummaryOut)
async def channels_summary(
    service: ChannelService = Depends(get_channel_service),
) -> ChannelSummaryOut:
    channels, total = await service.list_channels()
    verified = sum(1 for c in channels if c.status == ChannelStatus.VERIFIED)
    warning = sum(1 for c in channels if c.status == ChannelStatus.WARNING)
    error = sum(1 for c in channels if c.status == ChannelStatus.ERROR)
    default = await service.get_default()
    return ChannelSummaryOut(
        total=total,
        verified=verified,
        with_warning=warning,
        with_error=error,
        default_channel_id=default.id if default else None,
        default_channel_label=(default.title or default.reference) if default else "",
    )


@router.post("", response_model=ChannelOut, status_code=201)
async def add_channel(
    payload: ChannelCreate, service: ChannelService = Depends(get_channel_service)
) -> ChannelOut:
    try:
        channel = await service.add(
            payload.reference,
            title=payload.title,
            kind=_parse_kind(payload.kind),
            make_default=payload.make_default,
            note=payload.note,
        )
    except ChannelServiceError as exc:
        _raise(exc)
    return _to_out(service, channel)


@router.get("/{channel_id}", response_model=ChannelOut)
async def get_channel(
    channel_id: str, service: ChannelService = Depends(get_channel_service)
) -> ChannelOut:
    channel = await service.get(channel_id)
    if channel is None:
        raise ApiError(404, "Канал не найден.", "Обновите список каналов.")
    return _to_out(service, channel)


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: str,
    payload: ChannelUpdate,
    service: ChannelService = Depends(get_channel_service),
) -> ChannelOut:
    try:
        channel = await service.update(
            channel_id,
            reference=payload.reference,
            title=payload.title,
            note=payload.note,
            status=_parse_status(payload.status) if payload.status else None,
        )
    except ChannelServiceError as exc:
        _raise(exc)
    return _to_out(service, channel)


@router.post("/{channel_id}/default", response_model=ChannelOut)
async def set_default(
    channel_id: str, service: ChannelService = Depends(get_channel_service)
) -> ChannelOut:
    try:
        channel = await service.set_default(channel_id)
    except ChannelServiceError as exc:
        _raise(exc)
    return _to_out(service, channel)


@router.post("/{channel_id}/modules", response_model=ChannelOut)
async def set_modules(
    channel_id: str,
    payload: ChannelModulesIn,
    service: ChannelService = Depends(get_channel_service),
) -> ChannelOut:
    try:
        channel = await service.set_modules(channel_id, payload.modules)
    except ChannelServiceError as exc:
        _raise(exc)
    return _to_out(service, channel)


@router.post("/{channel_id}/verify", response_model=ChannelVerificationOut)
async def verify_channel(
    channel_id: str,
    payload: ChannelVerifyIn,
    service: ChannelService = Depends(get_channel_service),
) -> ChannelVerificationOut:
    try:
        result = await service.verify(channel_id, payload.account_id)
    except ChannelServiceError as exc:
        _raise(exc)
    return ChannelVerificationOut(
        channel_id=result.channel_id,
        status=result.status,
        status_label=result.status_label,
        found=result.found,
        title=result.title,
        username=result.username,
        kind=result.kind,
        participants_count=result.participants_count,
        message=result.message,
        how_to_fix=result.how_to_fix,
        retry_after=result.retry_after,
    )


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: str, service: ChannelService = Depends(get_channel_service)
) -> None:
    try:
        await service.delete(channel_id)
    except ChannelServiceError as exc:
        _raise(exc)
