"""Real Telegram bot provider backed by aiogram.

This is the only module that imports aiogram (decision D-001). It translates
library exceptions into :mod:`backend.app.providers.errors` and never logs or
returns tokens.

Official managed-bot methods used here (Bot API):
``getManagedBotToken``, ``replaceManagedBotToken``,
``getManagedBotAccessSettings``, ``setManagedBotAccessSettings``.
The manager bot must have "Bot Management Mode" enabled in @BotFather.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    MenuButtonWebApp,
    ReactionTypeEmoji,
    WebAppInfo,
)

from backend.app.providers.errors import (
    FloodWaitError,
    InvalidTokenError,
    NetworkError,
    TelegramProviderError,
    UnauthorizedError,
)
from backend.app.providers.types import (
    BotIdentity,
    BotUpdate,
    ManagedBotAccess,
    ManagedBotRef,
)


def _identity_from_bot(me: object) -> BotIdentity:
    return BotIdentity(
        id=int(me.id),
        username=str(getattr(me, "username", "") or ""),
        first_name=str(getattr(me, "first_name", "") or ""),
        can_join_groups=getattr(me, "can_join_groups", None),
        can_read_all_group_messages=getattr(me, "can_read_all_group_messages", None),
        supports_inline_queries=getattr(me, "supports_inline_queries", None),
        can_manage_bots=getattr(me, "can_manage_bots", None),
    )


class AiogramBotProvider:
    """Concrete :class:`TelegramBotProvider` using aiogram."""

    def __init__(self, token: str) -> None:
        self._bot = Bot(token=token, default=DefaultBotProperties())

    def _translate(self, exc: Exception) -> TelegramProviderError:
        if isinstance(exc, TelegramRetryAfter):
            return FloodWaitError(exc.retry_after, technical=type(exc).__name__)
        if isinstance(exc, TelegramUnauthorizedError):
            return InvalidTokenError(
                "Telegram отклонил токен бота.",
                how_to_fix="Проверьте токен: возможно, он отозван. Создайте новый в @BotFather.",
                technical=type(exc).__name__,
            )
        if isinstance(exc, TelegramForbiddenError):
            return UnauthorizedError(
                "Бот не имеет доступа к этой операции.",
                how_to_fix=(
                    "Проверьте права бота и включён ли режим "
                    "управления ботами в @BotFather."
                ),
                technical=type(exc).__name__,
            )
        if isinstance(exc, TelegramNetworkError):
            return NetworkError(
                "Не удалось связаться с Telegram.",
                how_to_fix="Проверьте интернет-соединение и повторите попытку.",
                technical=type(exc).__name__,
            )
        if isinstance(exc, TelegramBadRequest):
            return TelegramProviderError(
                "Telegram отклонил запрос.",
                how_to_fix="Проверьте введённые данные и повторите попытку.",
                technical=type(exc).__name__,
            )
        return TelegramProviderError(
            "Непредвиденная ошибка при обращении к Telegram.",
            technical=type(exc).__name__,
        )

    async def _call(self, coro):  # type: ignore[no-untyped-def]
        try:
            return await coro
        except TelegramProviderError:
            raise
        except Exception as exc:
            raise self._translate(exc) from exc

    async def close(self) -> None:
        await self._bot.session.close()

    async def get_me(self) -> BotIdentity:
        me = await self._call(self._bot.get_me())
        return _identity_from_bot(me)

    async def health_check(self) -> BotIdentity:
        return await self.get_me()

    async def send_message(self, chat_id: int | str, text: str) -> None:
        await self._call(self._bot.send_message(chat_id=chat_id, text=text))

    async def set_webhook(self, url: str) -> bool:
        if url:
            return bool(await self._call(self._bot.set_webhook(url=url)))
        return bool(await self._call(self._bot.delete_webhook()))

    async def set_reaction(self, chat_id: int | str, message_id: int, emoji: str) -> None:
        # Telegram allows exactly one reaction per bot per message. An empty
        # emoji removes the bot's current reaction.
        reaction = [ReactionTypeEmoji(emoji=emoji)] if emoji else None
        await self._call(
            self._bot.set_message_reaction(
                chat_id=chat_id, message_id=message_id, reaction=reaction
            )
        )

    # --- Optional manager-bot niceties ---------------------------------------
    async def set_commands(self, commands: list[tuple[str, str]]) -> bool:
        payload = [BotCommand(command=name, description=desc) for name, desc in commands]
        return bool(
            await self._call(
                self._bot.set_my_commands(payload, scope=BotCommandScopeDefault())
            )
        )

    async def set_menu_button(self, title: str, url: str) -> bool:
        return bool(
            await self._call(
                self._bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text=title, web_app=WebAppInfo(url=url))
                )
            )
        )

    # --- Managed bots (official Bot API) -------------------------------------
    async def get_managed_bot_token(self, user_id: int) -> str:
        return await self._call(self._bot.get_managed_bot_token(user_id=user_id))

    async def replace_managed_bot_token(self, user_id: int) -> str:
        return await self._call(self._bot.replace_managed_bot_token(user_id=user_id))

    async def get_managed_bot_access_settings(self, user_id: int) -> ManagedBotAccess:
        settings = await self._call(self._bot.get_managed_bot_access_settings(user_id=user_id))
        return ManagedBotAccess(
            is_access_restricted=bool(getattr(settings, "is_access_restricted", False)),
            added_user_ids=list(getattr(settings, "added_user_ids", []) or []),
        )

    async def set_managed_bot_access_settings(
        self, user_id: int, is_access_restricted: bool, added_user_ids: list[int] | None = None
    ) -> bool:
        return bool(
            await self._call(
                self._bot.set_managed_bot_access_settings(
                    user_id=user_id,
                    is_access_restricted=is_access_restricted,
                    added_user_ids=added_user_ids,
                )
            )
        )

    async def get_managed_bots(self) -> list[ManagedBotRef]:
        # Telegram delivers managed-bot creations via updates, not a list
        # endpoint; the application tracks them in its own database.
        return []

    # --- Manager bot runtime (post-1.0 hardening) ----------------------------
    async def get_updates(
        self, *, offset: int | None = None, timeout: int = 0
    ) -> list[BotUpdate]:
        kwargs: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            kwargs["offset"] = offset
        updates = await self._call(self._bot.get_updates(**kwargs))
        result: list[BotUpdate] = []
        for update in updates or []:
            message = getattr(update, "message", None) or getattr(update, "edited_message", None)
            if message is None:
                result.append(BotUpdate(update_id=int(update.update_id), kind="other"))
                continue
            chat = getattr(message, "chat", None)
            sender = getattr(message, "from_user", None)
            result.append(
                BotUpdate(
                    update_id=int(update.update_id),
                    kind="message",
                    chat_id=getattr(chat, "id", None),
                    user_id=getattr(sender, "id", None),
                    username=str(getattr(sender, "username", "") or ""),
                    text=str(getattr(message, "text", "") or ""),
                )
            )
        return result
