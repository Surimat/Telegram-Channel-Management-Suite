"""Bot↔channel binding service (product slice: bot-only mode).

This is the missing "connect a bot to a channel" step. It stores the *verified*
relationship between a bot and a registry channel and answers the only question
the Reaction Manager really needs: **can this bot do the job in this channel?** —
using the official Bot API, with no user session involved.

Nothing is assumed. A binding only reaches ``ready`` after Telegram confirmed
the bot is present and has the right the function needs. A failed check is
recorded as a friendly status, never raised as a crash.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.base import utcnow
from backend.app.db.models.binding import (
    FUNCTION_REACTIONS,
    BindingRole,
    BindingStatus,
    BotChannelBinding,
)
from backend.app.db.models.bot import Bot
from backend.app.db.repositories.bindings import BindingRepository
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.providers.types import BotChannelStatus
from backend.app.services.events_service import EventsService

ProviderFactory = Callable[..., TelegramBotProvider]

MODULE = "bindings"

#: Which verified permission a function requires. ``can_set_reactions`` is the
#: provider's interpretation of "an admin (or open reactions) can react".
_FUNCTION_PERMISSION = {
    FUNCTION_REACTIONS: "can_set_reactions",
    "posting": "can_post_messages",
    "editing": "can_edit_messages",
}


class BindingServiceError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class BindingCheck:
    binding_id: str
    status: str
    status_label: str
    role: str
    present: bool
    can_set_reactions: bool
    message: str
    how_to_fix: str = ""


_STATUS_LABELS = {
    BindingStatus.NOT_CONNECTED: "Не подключён",
    BindingStatus.CONNECTED: "Подключён",
    BindingStatus.NEEDS_PERMISSION: "Нужны права",
    BindingStatus.READY: "Готов",
    BindingStatus.ERROR: "Ошибка",
}


def status_label(status: BindingStatus | str) -> str:
    try:
        return _STATUS_LABELS[BindingStatus(str(status))]
    except (ValueError, KeyError):
        return str(status)


def invite_link_for(bot_username: str, channel_ref: str) -> str:
    """Return the official Telegram link that adds a bot to a channel.

    Telegram's own deep link: ``https://t.me/<bot>?startgroup=...`` opens the
    "add to group/channel" flow. We keep the bot username and the target so the
    UI can present a single "Открыть в Telegram" button.
    """
    username = (bot_username or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?startgroup=true"


class BindingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = BindingRepository(session)
        self.bots = BotRepository(session)
        self.channels = ChannelRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory

    # --- provider helpers ----------------------------------------------------
    def _provider_for(self, bot: Bot) -> TelegramBotProvider:
        if not bot.token_encrypted:
            raise BindingServiceError(
                "У этого бота нет сохранённого токена.",
                how_to_fix="Добавьте бота заново или получите токен управляемого бота.",
            )
        try:
            token = open_secret(bot.token_encrypted, self.settings)
        except ValueError as exc:
            raise BindingServiceError(
                "Не удалось прочитать токен бота.",
                how_to_fix="Проверьте, что APP_SECRET_KEY не менялся.",
            ) from exc
        return self._provider_factory(
            token, provider_name=bot.provider_name, settings=self.settings
        )

    # --- inventory -----------------------------------------------------------
    async def list_bindings(
        self, *, channel_id: str | None = None, bot_id: str | None = None
    ) -> list[BotChannelBinding]:
        if channel_id:
            return await self.repo.list_for_channel(channel_id)
        if bot_id:
            return await self.repo.list_for_bot(bot_id)
        return await self.repo.list_all()

    async def get(self, binding_id: str) -> BotChannelBinding | None:
        return await self.repo.get(binding_id)

    # --- connect -------------------------------------------------------------
    async def connect(
        self, bot_id: str, channel_id: str, *, function: str = FUNCTION_REACTIONS
    ) -> BotChannelBinding:
        """Create (or refresh) a binding and return it un-verified."""
        bot = await self.bots.get(bot_id)
        if bot is None:
            raise BindingServiceError("Бот не найден.", status_code=404)
        channel = await self.channels.get(channel_id)
        if channel is None:
            raise BindingServiceError("Канал не найден.", status_code=404)

        binding = await self.repo.find(bot_id, channel_id, function)
        if binding is None:
            binding = BotChannelBinding(
                bot_id=bot_id,
                channel_id=channel_id,
                function=function,
            )
            await self.repo.add(binding)
        binding.channel_label = channel.title or channel.reference
        binding.invite_link = invite_link_for(bot.username, channel.reference)
        if binding.status is BindingStatus.ERROR:
            binding.status = BindingStatus.NOT_CONNECTED
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Бот подключён к каналу: {binding.channel_label}.",
            explanation="Теперь можно проверить подключение и права бота.",
            operation="connect",
            status="ok",
        )
        await self.session.commit()
        return binding

    async def delete(self, binding_id: str) -> None:
        binding = await self.repo.get(binding_id)
        if binding is None:
            raise BindingServiceError("Подключение не найдено.", status_code=404)
        await self.repo.delete(binding)
        await self.session.commit()

    # --- verify --------------------------------------------------------------
    async def check(self, binding_id: str) -> BindingCheck:
        """Verify the binding against Telegram and persist the real state."""
        binding = await self.repo.get(binding_id)
        if binding is None:
            raise BindingServiceError("Подключение не найдено.", status_code=404)
        bot = await self.bots.get(binding.bot_id)
        if bot is None:
            raise BindingServiceError("Бот для этого подключения не найден.", status_code=404)
        channel = await self.channels.get(binding.channel_id)
        target: int | str = binding.channel_id
        if channel is not None:
            target = channel.telegram_id or channel.reference or binding.channel_id

        provider = self._provider_for(bot)
        try:
            if bot.telegram_id is None:
                identity = await provider.get_me()
                bot.telegram_id = identity.id
                bot.username = bot.username or identity.username
            status = await provider.get_bot_channel_status(target, int(bot.telegram_id or 0))
        except TelegramProviderError as exc:
            self._apply_error(binding, exc.message, exc.how_to_fix)
            await self.session.commit()
            return self._check_result(binding, status=None, message=exc.message, fix=exc.how_to_fix)
        finally:
            await provider.close()

        self._apply_status(binding, status)
        binding.last_error = "" if status.present else status.message
        await self.session.flush()
        await self.session.commit()
        return self._check_result(
            binding, status=status, message=status.message, fix=status.how_to_fix
        )

    async def check_all_for_channel(self, channel_id: str) -> list[BindingCheck]:
        results: list[BindingCheck] = []
        for binding in await self.repo.list_for_channel(channel_id):
            results.append(await self.check(binding.id))
        return results

    def _apply_status(self, binding: BotChannelBinding, status: BotChannelStatus) -> None:
        binding.last_checked = utcnow()
        binding.can_post_messages = status.can_post_messages
        binding.can_edit_messages = status.can_edit_messages
        binding.can_delete_messages = status.can_delete_messages
        binding.can_manage_chat = status.can_manage_chat
        binding.can_invite_users = status.can_invite_users
        binding.can_set_reactions = status.can_set_reactions
        binding.permissions = json.dumps(
            {
                "can_post_messages": status.can_post_messages,
                "can_edit_messages": status.can_edit_messages,
                "can_delete_messages": status.can_delete_messages,
                "can_manage_chat": status.can_manage_chat,
                "can_invite_users": status.can_invite_users,
                "can_set_reactions": status.can_set_reactions,
            }
        )
        binding.role = _role_from_status(status.status)

        if not status.present:
            binding.status = BindingStatus.NOT_CONNECTED
            binding.last_error = status.message or "Бот не найден в этом канале."
            return

        required = _FUNCTION_PERMISSION.get(binding.function, "can_set_reactions")
        has_required = bool(getattr(status, required, False)) or status.is_admin
        if has_required:
            binding.status = BindingStatus.READY
        else:
            binding.status = BindingStatus.NEEDS_PERMISSION
            binding.last_error = ""

    def _apply_error(self, binding: BotChannelBinding, message: str, fix: str) -> None:
        binding.status = BindingStatus.ERROR
        binding.last_checked = utcnow()
        binding.last_error = message

    @staticmethod
    def _check_result(
        binding: BotChannelBinding,
        *,
        status: BotChannelStatus | None,
        message: str,
        fix: str,
    ) -> BindingCheck:
        return BindingCheck(
            binding_id=binding.id,
            status=str(binding.status),
            status_label=status_label(binding.status),
            role=str(binding.role),
            present=bool(status.present) if status else False,
            can_set_reactions=binding.can_set_reactions,
            message=message or _default_message(binding.status),
            how_to_fix=fix,
        )


def _role_from_status(value: str) -> BindingRole:
    if value in {"administrator", "creator"}:
        return BindingRole.ADMINISTRATOR
    if value in {"member", "restricted"}:
        return BindingRole.MEMBER
    if value in {"left", "kicked"}:
        return BindingRole.LEFT
    return BindingRole.UNKNOWN


def _default_message(status: BindingStatus) -> str:
    return {
        BindingStatus.NOT_CONNECTED: "Бот ещё не добавлен в канал.",
        BindingStatus.CONNECTED: "Бот в канале.",
        BindingStatus.NEEDS_PERMISSION: "Боту не хватает прав для этой функции.",
        BindingStatus.READY: "Бот готов выполнять эту функцию.",
        BindingStatus.ERROR: "Не удалось проверить подключение.",
    }.get(status, "")


__all__ = [
    "BindingCheck",
    "BindingService",
    "BindingServiceError",
    "invite_link_for",
    "status_label",
]
