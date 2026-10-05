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
    BotChannelStatus,
    BotIdentity,
    BotUpdate,
    InviteLinkResult,
    ManagedBotAccess,
    ManagedBotRef,
    PostSendResult,
    ReactionCapability,
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

    # --- Bot ↔ channel administration (product slice: bot-only mode) ---------
    async def get_chat(self, chat_id: int | str) -> dict[str, object]:
        chat = await self._call(self._bot.get_chat(chat_id=chat_id))
        return {
            "id": getattr(chat, "id", None),
            "title": str(getattr(chat, "title", "") or ""),
            "username": str(getattr(chat, "username", "") or ""),
            "type": str(getattr(chat, "type", "") or ""),
            "description": str(getattr(chat, "description", "") or ""),
            "members_count": getattr(chat, "members_count", None),
        }

    async def get_bot_channel_status(
        self, chat_id: int | str, bot_id: int
    ) -> BotChannelStatus:
        try:
            member = await self._call(
                self._bot.get_chat_member(chat_id=chat_id, user_id=bot_id)
            )
        except TelegramProviderError as exc:
            # A "user not found / not a member" is a normal negative result, not
            # a hard failure: report it as not-present so the UI can offer the
            # "add the bot" step.
            return BotChannelStatus(
                found=False,
                present=False,
                status="unknown",
                message=exc.message,
                how_to_fix=exc.how_to_fix,
            )
        status = str(getattr(member, "status", "") or "unknown")
        present = status in {"administrator", "creator", "member", "restricted"}
        is_admin = status in {"administrator", "creator"}
        return BotChannelStatus(
            found=True,
            present=present,
            status=status,
            is_admin=is_admin,
            can_post_messages=bool(getattr(member, "can_post_messages", False)),
            can_edit_messages=bool(getattr(member, "can_edit_messages", False)),
            can_delete_messages=bool(getattr(member, "can_delete_messages", False)),
            can_manage_chat=bool(getattr(member, "can_manage_chat", False)),
            can_invite_users=bool(getattr(member, "can_invite_users", False)),
            can_restrict_members=bool(getattr(member, "can_restrict_members", False)),
            can_pin_messages=bool(getattr(member, "can_pin_messages", False)),
            # Telegram's Bot API has no dedicated "can set reactions" right; an
            # administrator (or a member in a channel where reactions are open)
            # may react. We treat administrator/creator as allowed and otherwise
            # leave it False until a real reaction succeeds.
            can_set_reactions=is_admin,
        )

    async def get_reaction_capabilities(self, chat_id: int | str) -> ReactionCapability:
        try:
            chat = await self._call(self._bot.get_chat(chat_id=chat_id))
        except TelegramProviderError as exc:
            return ReactionCapability(
                determined=False,
                message=exc.message,
            )
        available_raw = getattr(chat, "available_reactions", None)
        if available_raw is None:
            return ReactionCapability(
                determined=False,
                message="Telegram не сообщил набор реакций для этого канала.",
            )
        emoji: list[str] = []
        for item in available_raw or []:
            value = getattr(item, "emoji", None)
            if value:
                emoji.append(str(value))
        return ReactionCapability(
            determined=True,
            available=emoji,
            bot_compatible=list(emoji),
            reactions_limit=int(getattr(chat, "max_reaction_count", 0) or 0),
            paid_available=bool(getattr(chat, "has_paid_media", False)),
            message="Набор реакций получен от Telegram.",
        )

    async def create_invite_link(
        self,
        chat_id: int | str,
        *,
        name: str = "",
        join_request: bool = False,
        member_limit: int = 0,
        expire_date: int | None = None,
    ) -> InviteLinkResult:
        kwargs: dict[str, object] = {}
        if name:
            kwargs["name"] = name
        if join_request:
            kwargs["creates_join_request"] = True
        if member_limit:
            kwargs["member_limit"] = member_limit
        if expire_date:
            kwargs["expire_date"] = expire_date
        try:
            link = await self._call(self._bot.create_chat_invite_link(chat_id=chat_id, **kwargs))
        except TelegramProviderError as exc:
            return InviteLinkResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)
        return InviteLinkResult(
            ok=True,
            link=str(getattr(link, "invite_link", "") or ""),
            name=str(getattr(link, "name", "") or name),
            join_request=bool(getattr(link, "creates_join_request", join_request)),
            member_limit=int(getattr(link, "member_limit", 0) or 0),
        )

    async def export_invite_link(self, chat_id: int | str) -> InviteLinkResult:
        try:
            link = await self._call(self._bot.export_chat_invite_link(chat_id=chat_id))
        except TelegramProviderError as exc:
            return InviteLinkResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)
        return InviteLinkResult(ok=True, link=str(link or ""))

    async def revoke_invite_link(self, chat_id: int | str, link: str) -> bool:
        result = await self._call(
            self._bot.revoke_chat_invite_link(chat_id=chat_id, invite_link=link)
        )
        return bool(result)

    async def send_document(
        self,
        chat_id: int | str,
        *,
        filename: str,
        content: bytes,
        caption: str = "",
    ) -> bool:
        from aiogram.types import BufferedInputFile

        document = BufferedInputFile(content, filename=filename)
        await self._call(
            self._bot.send_document(chat_id=chat_id, document=document, caption=caption or None)
        )
        return True

    # --- Content Studio posting (v1.2) ---------------------------------------
    def _reply_markup(self, buttons: list[list[object]] | None):  # type: ignore[no-untyped-def]
        if not buttons:
            return None
        from aiogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            WebAppInfo,
        )

        rows: list[list[object]] = []
        for row in buttons:
            out_row: list[object] = []
            for btn in row:
                text = str(getattr(btn, "text", "") or "")
                action = str(getattr(btn, "action", "url") or "url")
                value = str(getattr(btn, "value", "") or "")
                if not text:
                    continue
                if action == "url":
                    out_row.append(InlineKeyboardButton(text=text, url=value))
                elif action == "callback":
                    out_row.append(InlineKeyboardButton(text=text, callback_data=value[:64]))
                elif action == "webapp":
                    out_row.append(
                        InlineKeyboardButton(text=text, web_app=WebAppInfo(url=value))
                    )
                elif action == "copy":
                    out_row.append(
                        InlineKeyboardButton(text=text, copy_text={"text": value})
                    )
            if out_row:
                rows.append(out_row)
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    async def send_post(
        self,
        chat_id: int | str,
        *,
        text: str,
        entities: list[dict[str, object]] | None = None,
        media: list[object] | None = None,
        buttons: list[list[object]] | None = None,
        disable_notification: bool = False,
    ) -> PostSendResult:
        from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

        reply_markup = self._reply_markup(buttons)
        media_list = list(media or [])
        try:
            if not media_list:
                message = await self._call(
                    self._bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        disable_notification=disable_notification,
                    )
                )
                return PostSendResult(
                    ok=True, message_ids=[int(message.message_id)], message="Опубликовано."
                )
            if len(media_list) == 1:
                item = media_list[0]
                kind = str(getattr(item, "kind", "photo") or "photo")
                path = str(getattr(item, "path", "") or "")
                caption = str(getattr(item, "caption", "") or text)
                if kind == "video":
                    message = await self._call(
                        self._bot.send_video(
                            chat_id=chat_id,
                            video=FSInputFile(path),
                            caption=caption or None,
                            reply_markup=reply_markup,
                        )
                    )
                elif kind == "document":
                    message = await self._call(
                        self._bot.send_document(
                            chat_id=chat_id,
                            document=FSInputFile(path),
                            caption=caption or None,
                            reply_markup=reply_markup,
                        )
                    )
                else:
                    message = await self._call(
                        self._bot.send_photo(
                            chat_id=chat_id,
                            photo=FSInputFile(path),
                            caption=caption or None,
                            reply_markup=reply_markup,
                        )
                    )
                return PostSendResult(
                    ok=True, message_ids=[int(message.message_id)], message="Опубликовано."
                )
            # Album (grouped media). Item count is validated before this call.
            group: list[object] = []
            for item in media_list:
                path = str(getattr(item, "path", "") or "")
                caption = str(getattr(item, "caption", "") or "")
                kind = str(getattr(item, "kind", "photo") or "photo")
                if kind == "video":
                    group.append(InputMediaVideo(media=FSInputFile(path), caption=caption or None))
                else:
                    group.append(InputMediaPhoto(media=FSInputFile(path), caption=caption or None))
            messages = await self._call(
                self._bot.send_media_group(chat_id=chat_id, media=group)
            )
            ids = [int(m.message_id) for m in messages]
            return PostSendResult(ok=True, message_ids=ids, message="Альбом опубликован.")
        except TelegramProviderError as exc:
            # A lost connection after the request may have reached Telegram.
            uncertain = isinstance(exc, NetworkError)
            return PostSendResult(
                ok=False,
                message=exc.message,
                how_to_fix=exc.how_to_fix,
                uncertain=uncertain,
            )

    async def send_comment(
        self,
        chat_id: int | str,
        post_message_id: int,
        text: str,
        *,
        buttons: list[list[object]] | None = None,
    ) -> PostSendResult:
        discussion = await self.get_linked_chat(chat_id)
        if discussion is None:
            return PostSendResult(
                ok=False,
                message="У канала нет связанной группы обсуждений.",
                how_to_fix="Свяжите группу обсуждений с каналом в Telegram.",
            )
        try:
            message = await self._call(
                self._bot.send_message(
                    chat_id=discussion,
                    text=text,
                    reply_to_message_id=post_message_id,
                    reply_markup=self._reply_markup(buttons),
                )
            )
            return PostSendResult(
                ok=True, message_ids=[int(message.message_id)], message="Комментарий опубликован."
            )
        except TelegramProviderError as exc:
            return PostSendResult(
                ok=False, message=exc.message, how_to_fix=exc.how_to_fix,
                uncertain=isinstance(exc, NetworkError),
            )

    async def edit_message(
        self, chat_id: int | str, message_id: int, text: str
    ) -> PostSendResult:
        try:
            message = await self._call(
                self._bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=text
                )
            )
            return PostSendResult(
                ok=True, message_ids=[int(message.message_id)], message="Изменено."
            )
        except TelegramProviderError as exc:
            return PostSendResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)

    async def delete_messages(
        self, chat_id: int | str, message_ids: list[int]
    ) -> PostSendResult:
        try:
            await self._call(
                self._bot.delete_messages(chat_id=chat_id, message_ids=message_ids)
            )
            return PostSendResult(ok=True, message_ids=list(message_ids), message="Удалено.")
        except TelegramProviderError as exc:
            return PostSendResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)

    async def pin_message(self, chat_id: int | str, message_id: int) -> PostSendResult:
        try:
            await self._call(
                self._bot.pin_chat_message(
                    chat_id=chat_id, message_id=message_id, disable_notification=True
                )
            )
            return PostSendResult(ok=True, message_ids=[message_id], message="Закреплено.")
        except TelegramProviderError as exc:
            return PostSendResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)

    async def get_linked_chat(self, chat_id: int | str) -> int | None:
        try:
            chat = await self._call(self._bot.get_chat(chat_id=chat_id))
        except TelegramProviderError:
            return None
        linked = getattr(chat, "linked_chat_id", None)
        return int(linked) if linked else None
