"""Editorial Workspace router (v1.4: редакционная комната).

Rooms, verified bot rights, roles, the publication queue (board + reorder) and
the audit log. Secrets are never returned; roles are always identified by the
numeric Telegram user id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_editorial_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.editorial import (
    EditorialActionResultOut,
    EditorialAuditOut,
    EditorialBoardOut,
    EditorialEnqueueIn,
    EditorialItemOut,
    EditorialMemberIn,
    EditorialMemberOut,
    EditorialMoveIn,
    EditorialReorderIn,
    EditorialRoomCheckOut,
    EditorialRoomIn,
    EditorialRoomListOut,
    EditorialRoomOut,
)
from backend.app.db.models.editorial import (
    ROLE_TITLES,
    STATUS_TITLES,
    EditorialMember,
    EditorialRoom,
)
from backend.app.services.editorial_service import (
    ActionResult,
    EditorialError,
    EditorialService,
    _load_topics,
    _room_status_label,
)

router = APIRouter(prefix="/editorial", tags=["editorial"])


def _raise(exc: EditorialError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _room_out(room: EditorialRoom) -> EditorialRoomOut:
    return EditorialRoomOut(
        id=room.id,
        channel_id=room.channel_id,
        channel_label=room.channel_label,
        bot_id=room.bot_id,
        group_chat_id=room.group_chat_id,
        group_title=room.group_title,
        status=str(room.status),
        status_label=_room_status_label(room.status),
        topics=_load_topics(room),
        bot_is_member=room.bot_is_member,
        bot_is_admin=room.bot_is_admin,
        can_send_messages=room.can_send_messages,
        can_manage_topics=room.can_manage_topics,
        last_checked=room.last_checked.isoformat() if room.last_checked else "",
        last_error=room.last_error,
    )


def _member_out(member: EditorialMember) -> EditorialMemberOut:
    return EditorialMemberOut(
        id=member.id,
        telegram_user_id=member.telegram_user_id,
        display_name=member.display_name,
        username=member.username,
        role=str(member.role),
        role_title=ROLE_TITLES.get(member.role, str(member.role)),
        enabled=member.enabled,
    )


def _action_out(result: ActionResult) -> EditorialActionResultOut:
    return EditorialActionResultOut(
        ok=result.ok,
        action=result.action,
        message=result.message,
        item_id=result.item_id,
        status=result.status,
    )


@router.get("/rooms", response_model=EditorialRoomListOut)
async def list_rooms(
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialRoomListOut:
    rooms = await service.list_rooms()
    return EditorialRoomListOut(
        items=[_room_out(r) for r in rooms],
        status_titles={str(s): t for s, t in STATUS_TITLES.items()},
    )


@router.post("/rooms", response_model=EditorialRoomOut)
async def create_room(
    payload: EditorialRoomIn,
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialRoomOut:
    try:
        room = await service.create_room(
            channel_id=payload.channel_id,
            group_chat_id=payload.group_chat_id,
            bot_id=payload.bot_id,
            group_title=payload.group_title,
        )
    except EditorialError as exc:
        _raise(exc)
    return _room_out(room)


@router.post("/rooms/{room_id}/check", response_model=EditorialRoomCheckOut)
async def check_room(
    room_id: str,
    create_topics: bool = Query(default=True),
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialRoomCheckOut:
    try:
        check = await service.check_room(room_id, create_topics=create_topics)
    except EditorialError as exc:
        _raise(exc)
    return EditorialRoomCheckOut(
        room_id=check.room_id,
        status=check.status,
        status_label=check.status_label,
        message=check.message,
        how_to_fix=check.how_to_fix,
        topics=check.topics,
    )


@router.delete("/rooms/{room_id}")
async def delete_room(
    room_id: str,
    service: EditorialService = Depends(get_editorial_service),
) -> dict[str, bool]:
    try:
        await service.delete_room(room_id)
    except EditorialError as exc:
        _raise(exc)
    return {"ok": True}


@router.get("/rooms/{room_id}/members", response_model=list[EditorialMemberOut])
async def list_members(
    room_id: str,
    service: EditorialService = Depends(get_editorial_service),
) -> list[EditorialMemberOut]:
    return [_member_out(m) for m in await service.list_members(room_id)]


@router.put("/rooms/{room_id}/members", response_model=EditorialMemberOut)
async def set_member(
    room_id: str,
    payload: EditorialMemberIn,
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialMemberOut:
    try:
        member = await service.set_member(
            room_id,
            telegram_user_id=payload.telegram_user_id,
            role=payload.role,
            display_name=payload.display_name,
            username=payload.username,
            enabled=payload.enabled,
        )
    except EditorialError as exc:
        _raise(exc)
    return _member_out(member)


@router.delete("/rooms/{room_id}/members/{telegram_user_id}")
async def remove_member(
    room_id: str,
    telegram_user_id: int,
    service: EditorialService = Depends(get_editorial_service),
) -> dict[str, bool]:
    await service.remove_member(room_id, telegram_user_id)
    return {"ok": True}


@router.get("/rooms/{room_id}/board", response_model=EditorialBoardOut)
async def board(
    room_id: str,
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialBoardOut:
    try:
        data = await service.board(room_id)
    except EditorialError as exc:
        _raise(exc)
    return EditorialBoardOut(**data)


@router.post("/rooms/{room_id}/items", response_model=EditorialItemOut)
async def enqueue_item(
    room_id: str,
    payload: EditorialEnqueueIn,
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialItemOut:
    try:
        item = await service.enqueue_item(
            room_id,
            content_item_id=payload.content_item_id,
            channel_id=payload.channel_id,
            title=payload.title,
        )
    except EditorialError as exc:
        _raise(exc)
    from backend.app.services.editorial_service import _item_view

    return EditorialItemOut(**_item_view(item))


@router.post("/rooms/{room_id}/items/{item_id}/move", response_model=EditorialActionResultOut)
async def move_item(
    room_id: str,
    item_id: str,
    payload: EditorialMoveIn,
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialActionResultOut:
    try:
        result = await service.move(
            room_id,
            item_id,
            payload.status,
            actor_telegram_id=payload.actor_telegram_id,
            actor_name=payload.actor_name,
            expected_version=payload.expected_version,
        )
    except EditorialError as exc:
        _raise(exc)
    return _action_out(result)


@router.post("/rooms/{room_id}/reorder", response_model=EditorialBoardOut)
async def reorder(
    room_id: str,
    payload: EditorialReorderIn,
    service: EditorialService = Depends(get_editorial_service),
) -> EditorialBoardOut:
    try:
        await service.reorder(
            room_id,
            status=payload.status,
            ordered_ids=payload.ordered_ids,
            actor_telegram_id=payload.actor_telegram_id,
            actor_name=payload.actor_name,
        )
        data = await service.board(room_id)
    except EditorialError as exc:
        _raise(exc)
    return EditorialBoardOut(**data)


@router.get("/rooms/{room_id}/audit", response_model=list[EditorialAuditOut])
async def audit(
    room_id: str,
    item_id: str = Query(default=""),
    service: EditorialService = Depends(get_editorial_service),
) -> list[EditorialAuditOut]:
    entries = await service.history(room_id, item_id=item_id)
    return [
        EditorialAuditOut(
            id=e.id,
            item_id=e.item_id,
            actor_telegram_id=e.actor_telegram_id,
            actor_name=e.actor_name,
            action=e.action,
            old_status=e.old_status,
            new_status=e.new_status,
            detail=e.detail,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in entries
    ]


__all__ = ["router"]
