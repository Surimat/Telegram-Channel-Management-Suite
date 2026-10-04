"""Bindings + capabilities router (product slice: bot-only reactions).

Connects a bot to a registry channel, verifies its admin rights, and probes which
reactions the channel actually allows. All calls are bot-only (no user session)
and return friendly RU messages.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_binding_service, get_capability_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.bindings import (
    BindingCheckOut,
    BindingCreate,
    BindingListOut,
    BindingOut,
    CapabilityOut,
)
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.session import get_session
from backend.app.services.binding_service import (
    BindingCheck,
    BindingService,
    BindingServiceError,
    status_label,
)
from backend.app.services.capability_service import CapabilityService

router = APIRouter(prefix="/bindings", tags=["bindings"])


def _raise(exc: BindingServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _binding_out(binding, username: str = "") -> BindingOut:  # type: ignore[no-untyped-def]
    return BindingOut(
        id=binding.id,
        bot_id=binding.bot_id,
        bot_username=username,
        channel_id=binding.channel_id,
        channel_label=binding.channel_label,
        function=binding.function,
        status=str(binding.status),
        status_label=status_label(binding.status),
        role=str(binding.role),
        can_post_messages=binding.can_post_messages,
        can_edit_messages=binding.can_edit_messages,
        can_delete_messages=binding.can_delete_messages,
        can_manage_chat=binding.can_manage_chat,
        can_invite_users=binding.can_invite_users,
        can_set_reactions=binding.can_set_reactions,
        invite_link=binding.invite_link,
        note=binding.note,
        last_checked=binding.last_checked,
        last_error=binding.last_error,
        created_at=binding.created_at,
    )


def _check_out(check: BindingCheck) -> BindingCheckOut:
    return BindingCheckOut(
        binding_id=check.binding_id,
        status=check.status,
        status_label=check.status_label,
        role=check.role,
        present=check.present,
        can_set_reactions=check.can_set_reactions,
        message=check.message,
        how_to_fix=check.how_to_fix,
    )


@router.get("", response_model=BindingListOut)
async def list_bindings(
    channel_id: str | None = Query(default=None),
    bot_id: str | None = Query(default=None),
    service: BindingService = Depends(get_binding_service),
    session=Depends(get_session),
) -> BindingListOut:
    rows = await service.list_bindings(channel_id=channel_id, bot_id=bot_id)
    bots = BotRepository(session)
    items: list[BindingOut] = []
    for row in rows:
        bot = await bots.get(row.bot_id)
        items.append(_binding_out(row, bot.username if bot else ""))
    return BindingListOut(items=items, total=len(items))


@router.post("", response_model=BindingOut, status_code=201)
async def connect_binding(
    payload: BindingCreate,
    service: BindingService = Depends(get_binding_service),
    session=Depends(get_session),
) -> BindingOut:
    try:
        binding = await service.connect(
            payload.bot_id, payload.channel_id, function=payload.function
        )
    except BindingServiceError as exc:
        _raise(exc)
        raise
    bot = await BotRepository(session).get(binding.bot_id)
    return _binding_out(binding, bot.username if bot else "")


@router.post("/{binding_id}/check", response_model=BindingCheckOut)
async def check_binding(
    binding_id: str,
    service: BindingService = Depends(get_binding_service),
) -> BindingCheckOut:
    try:
        check = await service.check(binding_id)
    except BindingServiceError as exc:
        _raise(exc)
        raise
    return _check_out(check)


@router.post("/channel/{channel_id}/check", response_model=list[BindingCheckOut])
async def check_channel_bindings(
    channel_id: str,
    service: BindingService = Depends(get_binding_service),
) -> list[BindingCheckOut]:
    checks = await service.check_all_for_channel(channel_id)
    return [_check_out(c) for c in checks]


@router.delete("/{binding_id}")
async def delete_binding(
    binding_id: str,
    service: BindingService = Depends(get_binding_service),
) -> dict[str, bool]:
    try:
        await service.delete(binding_id)
    except BindingServiceError as exc:
        _raise(exc)
        raise
    return {"deleted": True}


capabilities_router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@capabilities_router.get("/{channel_id}", response_model=CapabilityOut)
async def get_capability(
    channel_id: str,
    service: CapabilityService = Depends(get_capability_service),
) -> CapabilityOut:
    view = await service.view(channel_id)
    return CapabilityOut(
        channel_id=view.channel_id,
        status=view.status,
        available=view.available,
        bot_reactions=view.bot_reactions,
        reactions_limit=view.reactions_limit,
        paid_available=view.paid_available,
        message=view.message,
        last_checked=view.last_checked,
    )


@capabilities_router.post("/{channel_id}/probe", response_model=CapabilityOut)
async def probe_capability(
    channel_id: str,
    service: CapabilityService = Depends(get_capability_service),
) -> CapabilityOut:
    view = await service.probe(channel_id)
    return CapabilityOut(
        channel_id=view.channel_id,
        status=view.status,
        available=view.available,
        bot_reactions=view.bot_reactions,
        reactions_limit=view.reactions_limit,
        paid_available=view.paid_available,
        message=view.message,
        last_checked=view.last_checked,
    )
