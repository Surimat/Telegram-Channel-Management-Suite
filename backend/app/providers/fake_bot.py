"""Deterministic fake Telegram bot provider.

Used by tests and by the app's offline/dev mode so the full business logic can
run without real credentials or network access. It never performs I/O.
"""

from __future__ import annotations

import time

from backend.app.providers.errors import InvalidTokenError
from backend.app.providers.types import (
    BotChannelStatus,
    BotIdentity,
    BotUpdate,
    InviteLinkResult,
    ManagedBotAccess,
    ManagedBotRef,
    PostSendResult,
    ReactionCapability,
    ReactionRecord,
)


class FakeTelegramBotProvider:
    """In-memory :class:`TelegramBotProvider` implementation."""

    def __init__(
        self,
        token: str,
        *,
        identity: BotIdentity | None = None,
        managed_bots: list[ManagedBotRef] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        # The token is held only to validate presence; it is never returned.
        self._token = token
        self._identity = identity
        self._managed_bots = list(managed_bots or [])
        self._fail_with = fail_with
        self.sent_messages: list[tuple[int | str, str]] = []
        self.reactions: list[ReactionRecord] = []
        self.webhook_url: str | None = None
        self.closed = False
        # Manager-bot runtime (post-1.0): a scripted queue of incoming updates.
        self._updates: list[BotUpdate] = []
        self.commands: list[tuple[str, str]] = []
        self.menu_button: tuple[str, str] | None = None
        # Bot↔channel admin (product slice): scripted channel scenarios.
        self.chats: dict[str, dict[str, object]] = {}
        self.channel_status: dict[str, BotChannelStatus] = {}
        self.reaction_capabilities: dict[str, ReactionCapability] = {}
        self.documents: list[tuple[int | str, str, int]] = []
        self.created_links: list[InviteLinkResult] = []
        # Content Studio posting (v1.2): recorded, deterministic side effects.
        self.posts: list[dict[str, object]] = []
        self.comments: list[tuple[int | str, int, str]] = []
        self.edits: list[tuple[int | str, int, str]] = []
        self.deleted: list[int] = []
        self.pinned: list[int] = []
        self.linked_chats: dict[str, int] = {}
        self.fail_posting: bool = False
        self.fail_deletion: bool = False
        self._next_message_id: int = 1000
        # Editorial Workspace (v1.4).
        self.topics: list[tuple[int | str, int, str]] = []
        self.topic_edits: list[tuple[int | str, int, str]] = []
        self.topic_messages: list[tuple[int | str, int, str]] = []
        self.card_buttons: list[list[list[object]]] = []
        self.markup_edits: list[tuple[int | str, int, list[list[object]]]] = []
        self.answered_callbacks: list[tuple[str, str, bool]] = []
        self._next_topic_id: int = 100

    def script_linked_chat(self, chat_id: int | str, discussion_id: int) -> None:
        """Link a discussion group to ``chat_id`` (tests)."""
        self.linked_chats[str(chat_id)] = discussion_id

    def queue_updates(self, updates: list[BotUpdate]) -> None:
        """Enqueue updates for the next :meth:`get_updates` call (tests)."""
        self._updates.extend(updates)

    def _ensure_token(self) -> None:
        if not self._token or ":" not in self._token:
            raise InvalidTokenError(
                "Токен бота выглядит неверно.",
                how_to_fix="Скопируйте токен из @BotFather целиком, вида 123456:ABC-DEF.",
            )

    def _maybe_fail(self) -> None:
        if self._fail_with is not None:
            raise self._fail_with

    async def close(self) -> None:
        self.closed = True

    async def get_me(self) -> BotIdentity:
        self._ensure_token()
        self._maybe_fail()
        if self._identity is not None:
            return self._identity
        numeric = self._token.split(":", 1)[0]
        bot_id = int(numeric) if numeric.isdigit() else 1
        return BotIdentity(id=bot_id, username=f"bot{bot_id}", first_name=f"Bot {bot_id}")

    async def health_check(self) -> BotIdentity:
        return await self.get_me()

    async def send_message(self, chat_id: int | str, text: str) -> None:
        self._ensure_token()
        self._maybe_fail()
        self.sent_messages.append((chat_id, text))

    async def set_webhook(self, url: str) -> bool:
        self._ensure_token()
        self._maybe_fail()
        self.webhook_url = url or None
        return True

    async def set_reaction(self, chat_id: int | str, message_id: int, emoji: str) -> None:
        self._ensure_token()
        self._maybe_fail()
        identity = await self.get_me()
        self.reactions.append(
            ReactionRecord(
                chat_id=chat_id,
                message_id=message_id,
                emoji=emoji,
                applied_at=time.time(),
                bot_id=identity.id,
                bot_username=identity.username,
            )
        )

    async def get_managed_bot_token(self, user_id: int) -> str:
        self._ensure_token()
        self._maybe_fail()
        return f"{user_id}:FAKE-MANAGED-TOKEN"

    async def replace_managed_bot_token(self, user_id: int) -> str:
        self._ensure_token()
        self._maybe_fail()
        return f"{user_id}:FAKE-MANAGED-TOKEN-NEW"

    async def get_managed_bot_access_settings(self, user_id: int) -> ManagedBotAccess:
        self._ensure_token()
        self._maybe_fail()
        return ManagedBotAccess()

    async def set_managed_bot_access_settings(
        self, user_id: int, is_access_restricted: bool, added_user_ids: list[int] | None = None
    ) -> bool:
        self._ensure_token()
        self._maybe_fail()
        return True

    async def get_managed_bots(self) -> list[ManagedBotRef]:
        self._ensure_token()
        self._maybe_fail()
        return list(self._managed_bots)

    # --- Manager bot runtime (post-1.0 hardening) ----------------------------
    async def set_commands(self, commands: list[tuple[str, str]]) -> bool:
        self._ensure_token()
        self._maybe_fail()
        self.commands = list(commands)
        return True

    async def set_menu_button(self, title: str, url: str) -> bool:
        self._ensure_token()
        self._maybe_fail()
        self.menu_button = (title, url)
        return True

    async def get_updates(
        self, *, offset: int | None = None, timeout: int = 0
    ) -> list[BotUpdate]:
        self._ensure_token()
        self._maybe_fail()
        if offset is not None:
            # Acknowledge updates below ``offset`` (mirrors Telegram semantics).
            self._updates = [u for u in self._updates if u.update_id >= offset]
        pending = list(self._updates)
        self._updates = []
        return pending

    # --- Bot ↔ channel administration (product slice: bot-only mode) ---------
    def script_chat(self, chat_id: int | str, **fields: object) -> None:
        """Pre-seed a chat so ``get_chat`` returns it (tests)."""
        self.chats[str(chat_id)] = {"id": chat_id, **fields}

    def script_bot_status(self, chat_id: int | str, status: BotChannelStatus) -> None:
        """Pre-seed a bot's verified channel status (tests)."""
        self.channel_status[str(chat_id)] = status

    def script_capabilities(self, chat_id: int | str, caps: ReactionCapability) -> None:
        """Pre-seed a chat's reaction capabilities (tests)."""
        self.reaction_capabilities[str(chat_id)] = caps

    async def get_chat(self, chat_id: int | str) -> dict[str, object]:
        self._ensure_token()
        self._maybe_fail()
        data = self.chats.get(str(chat_id))
        if data is None:
            return {
                "id": chat_id,
                "title": f"Chat {chat_id}",
                "username": "",
                "type": "channel",
                "description": "",
                "members_count": None,
            }
        return dict(data)

    async def get_bot_channel_status(
        self, chat_id: int | str, bot_id: int
    ) -> BotChannelStatus:
        self._ensure_token()
        self._maybe_fail()
        scripted = self.channel_status.get(str(chat_id))
        if scripted is not None:
            return scripted
        # Default: the bot is an administrator with the reaction capability, so
        # the happy path is testable without scripting every call.
        return BotChannelStatus(
            found=True,
            present=True,
            status="administrator",
            is_admin=True,
            can_post_messages=True,
            can_edit_messages=True,
            can_delete_messages=True,
            can_manage_chat=True,
            can_invite_users=True,
            can_set_reactions=True,
        )

    async def get_reaction_capabilities(self, chat_id: int | str) -> ReactionCapability:
        self._ensure_token()
        self._maybe_fail()
        scripted = self.reaction_capabilities.get(str(chat_id))
        if scripted is not None:
            return scripted
        return ReactionCapability(
            determined=True,
            available=["👍", "❤️", "🔥", "😂", "😢", "🙏"],
            bot_compatible=["👍", "❤️", "🔥", "😂", "😢", "🙏"],
            reactions_limit=1,
            paid_available=False,
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
        self._ensure_token()
        self._maybe_fail()
        result = InviteLinkResult(
            ok=True,
            link=f"https://t.me/+fake{abs(hash(str(chat_id))) % 100000}",
            name=name,
            join_request=join_request,
            member_limit=member_limit,
        )
        self.created_links.append(result)
        return result

    async def export_invite_link(self, chat_id: int | str) -> InviteLinkResult:
        self._ensure_token()
        self._maybe_fail()
        slug = abs(hash(str(chat_id))) % 100000
        return InviteLinkResult(ok=True, link=f"https://t.me/+fake{slug}")

    async def revoke_invite_link(self, chat_id: int | str, link: str) -> bool:
        self._ensure_token()
        self._maybe_fail()
        return True

    async def send_document(
        self,
        chat_id: int | str,
        *,
        filename: str,
        content: bytes,
        caption: str = "",
    ) -> bool:
        self._ensure_token()
        self._maybe_fail()
        self.documents.append((chat_id, filename, len(content)))
        return True

    # --- Content Studio posting (v1.2) ---------------------------------------
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
        self._ensure_token()
        self._maybe_fail()
        if self.fail_posting:
            return PostSendResult(
                ok=False,
                message="Тестовый сбой отправки.",
                how_to_fix="Проверьте права бота в канале.",
            )
        media_list = list(media or [])
        self.posts.append(
            {
                "chat_id": chat_id,
                "text": text,
                "entities": entities or [],
                "media": media_list,
                "buttons": buttons or [],
                "album": len(media_list) > 1,
            }
        )
        start = self._next_message_id
        self._next_message_id += max(1, len(media_list))
        ids = list(range(start, self._next_message_id))
        return PostSendResult(ok=True, message_ids=ids, message="Опубликовано.")

    async def send_comment(
        self,
        chat_id: int | str,
        post_message_id: int,
        text: str,
        *,
        buttons: list[list[object]] | None = None,
    ) -> PostSendResult:
        self._ensure_token()
        self._maybe_fail()
        if not self.linked_chats.get(str(chat_id)):
            return PostSendResult(
                ok=False,
                message="У канала нет связанной группы обсуждений.",
                how_to_fix="Свяжите группу обсуждений с каналом в Telegram.",
            )
        self.comments.append((chat_id, post_message_id, text))
        mid = self._next_message_id
        self._next_message_id += 1
        return PostSendResult(ok=True, message_ids=[mid], message="Комментарий опубликован.")

    async def edit_message(
        self, chat_id: int | str, message_id: int, text: str
    ) -> PostSendResult:
        self._ensure_token()
        self._maybe_fail()
        self.edits.append((chat_id, message_id, text))
        return PostSendResult(ok=True, message_ids=[message_id], message="Изменено.")

    async def delete_messages(
        self, chat_id: int | str, message_ids: list[int]
    ) -> PostSendResult:
        self._ensure_token()
        self._maybe_fail()
        if self.fail_deletion:
            return PostSendResult(ok=False, message="Не удалось удалить сообщение.")
        self.deleted.extend(message_ids)
        return PostSendResult(ok=True, message_ids=list(message_ids), message="Удалено.")

    async def pin_message(self, chat_id: int | str, message_id: int) -> PostSendResult:
        self._ensure_token()
        self._maybe_fail()
        self.pinned.append(message_id)
        return PostSendResult(ok=True, message_ids=[message_id], message="Закреплено.")

    async def get_linked_chat(self, chat_id: int | str) -> int | None:
        self._ensure_token()
        self._maybe_fail()
        return self.linked_chats.get(str(chat_id))

    # --- Editorial Workspace (v1.4) ------------------------------------------
    def script_topic(self, chat_id: int | str, topic_id: int) -> None:
        """Pre-seed a topic id returned by ``create_forum_topic`` (tests)."""
        self._next_topic_id = max(self._next_topic_id, topic_id + 1)

    async def create_forum_topic(
        self, chat_id: int | str, name: str, *, icon_color: int = 0
    ) -> int | None:
        self._ensure_token()
        self._maybe_fail()
        topic_id = self._next_topic_id
        self._next_topic_id += 1
        self.topics.append((chat_id, topic_id, name))
        return topic_id

    async def edit_forum_topic(
        self, chat_id: int | str, topic_id: int, name: str
    ) -> bool:
        self._ensure_token()
        self._maybe_fail()
        self.topic_edits.append((chat_id, topic_id, name))
        return True

    async def send_topic_message(
        self,
        chat_id: int | str,
        topic_id: int,
        text: str,
        *,
        buttons: list[list[object]] | None = None,
    ) -> PostSendResult:
        self._ensure_token()
        self._maybe_fail()
        self.topic_messages.append((chat_id, topic_id, text))
        self.card_buttons.append(buttons or [])
        mid = self._next_message_id
        self._next_message_id += 1
        return PostSendResult(ok=True, message_ids=[mid], message="Карточка создана.")

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        *,
        buttons: list[list[object]] | None = None,
    ) -> PostSendResult:
        self._ensure_token()
        self._maybe_fail()
        self.markup_edits.append((chat_id, message_id, buttons or []))
        return PostSendResult(ok=True, message_ids=[message_id], message="Кнопки обновлены.")

    async def answer_callback_query(
        self, callback_query_id: str, *, text: str = "", show_alert: bool = False
    ) -> bool:
        self._ensure_token()
        self._maybe_fail()
        self.answered_callbacks.append((callback_query_id, text, show_alert))
        return True
