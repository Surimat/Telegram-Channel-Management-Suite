"""Bots router: the bot inventory and managed-bot workflow.

All endpoints return friendly RU errors via :class:`BotServiceError` and never
expose bot tokens (decision D-010).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_bot_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.bots import (
    BotCreate,
    BotHealthOut,
    BotOut,
    BotSummary,
    ManagedBotPreview,
    ManagedBotRegister,
)
from backend.app.db.models.bot import BotKind
from backend.app.services.bot_service import BotService, BotServiceError

router = APIRouter(prefix="/bots", tags=["bots"])


def _parse_kind(value: str) -> BotKind:
    try:
        return BotKind(value)
    except ValueError as exc:
        raise ApiError(
            422,
            "Неизвестный тип бота. Допустимо: manager, managed, ordinary.",
            "Выберите тип из списка.",
        ) from exc


def _raise(exc: BotServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


@router.get("", response_model=list[BotOut])
async def list_bots(
    kind: str | None = Query(default=None, description="manager | managed | ordinary"),
    enabled: bool | None = Query(default=None),
    service: BotService = Depends(get_bot_service),
) -> list[BotOut]:
    bots = await service.list_bots(
        kind=_parse_kind(kind) if kind else None,
        enabled=enabled,
    )
    return [BotOut.from_model(b) for b in bots]


@router.get("/summary", response_model=BotSummary)
async def bots_summary(service: BotService = Depends(get_bot_service)) -> BotSummary:
    return BotSummary(**await service.summary())


@router.post("", response_model=BotOut, status_code=201)
async def add_bot(
    payload: BotCreate, service: BotService = Depends(get_bot_service)
) -> BotOut:
    try:
        bot = await service.add_bot(
            payload.token,
            kind=_parse_kind(payload.kind),
            provider_name=payload.provider_name,
            title=payload.title,
        )
    except BotServiceError as exc:
        _raise(exc)
    return BotOut.from_model(bot)


@router.get("/{bot_id}", response_model=BotOut)
async def get_bot(bot_id: str, service: BotService = Depends(get_bot_service)) -> BotOut:
    bot = await service.get(bot_id)
    if bot is None:
        raise ApiError(404, "Бот не найден.", "Обновите список ботов.")
    return BotOut.from_model(bot)


@router.post("/{bot_id}/health", response_model=BotHealthOut)
async def check_bot_health(
    bot_id: str, service: BotService = Depends(get_bot_service)
) -> BotHealthOut:
    try:
        result = await service.health_check(bot_id)
    except BotServiceError as exc:
        _raise(exc)
    return BotHealthOut(
        bot_id=result.bot_id,
        ok=result.ok,
        status=result.status,
        message=result.message,
        how_to_fix=result.how_to_fix,
        username=result.username,
        telegram_id=result.telegram_id,
    )


@router.post("/{bot_id}/enable", response_model=BotOut)
async def enable_bot(bot_id: str, service: BotService = Depends(get_bot_service)) -> BotOut:
    try:
        return BotOut.from_model(await service.set_enabled(bot_id, True))
    except BotServiceError as exc:
        _raise(exc)


@router.post("/{bot_id}/disable", response_model=BotOut)
async def disable_bot(bot_id: str, service: BotService = Depends(get_bot_service)) -> BotOut:
    try:
        return BotOut.from_model(await service.set_enabled(bot_id, False))
    except BotServiceError as exc:
        _raise(exc)


@router.delete("/{bot_id}", status_code=204)
async def remove_bot(bot_id: str, service: BotService = Depends(get_bot_service)) -> None:
    try:
        await service.remove(bot_id)
    except BotServiceError as exc:
        _raise(exc)


# --- Managed bots ------------------------------------------------------------
@router.get("/managed/all", response_model=list[BotOut])
async def list_managed_bots(
    service: BotService = Depends(get_bot_service),
) -> list[BotOut]:
    return [BotOut.from_model(b) for b in await service.list_managed()]


@router.get("/managed/preview", response_model=ManagedBotPreview)
async def managed_preview(
    username: str = Query(description="Желаемый @username нового бота"),
    name: str = Query(default=""),
    service: BotService = Depends(get_bot_service),
) -> ManagedBotPreview:
    link = await service.manager_link(username, name)
    return ManagedBotPreview(
        create_link=link,
        instructions=(
            "Откройте ссылку в Telegram. Новый бот будет создан, а управляющий бот "
            "получит уведомление. После этого нажмите «Получить токен»."
        ),
    )


@router.post("/managed/register", response_model=BotOut, status_code=201)
async def register_managed_bot(
    payload: ManagedBotRegister, service: BotService = Depends(get_bot_service)
) -> BotOut:
    bot = await service.register_managed_bot(
        payload.user_id,
        username=payload.username,
        title=payload.title,
        owner_id=payload.owner_id,
        owner_username=payload.owner_username,
    )
    return BotOut.from_model(bot)


@router.post("/{bot_id}/managed/token", response_model=BotOut)
async def fetch_managed_token(
    bot_id: str, service: BotService = Depends(get_bot_service)
) -> BotOut:
    try:
        return BotOut.from_model(await service.fetch_managed_bot_token(bot_id))
    except BotServiceError as exc:
        _raise(exc)


@router.post("/{bot_id}/managed/replace-token", response_model=BotOut)
async def replace_managed_token(
    bot_id: str, service: BotService = Depends(get_bot_service)
) -> BotOut:
    try:
        return BotOut.from_model(await service.replace_managed_bot_token(bot_id))
    except BotServiceError as exc:
        _raise(exc)
