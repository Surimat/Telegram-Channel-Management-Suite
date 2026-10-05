"""Concrete posting providers (v1.2: Content Studio posting engine).

* :class:`BotPostingProvider` wraps the existing
  :class:`~backend.app.providers.base.TelegramBotProvider` (bot-only mode).
* :class:`UserPostingProvider` wraps the existing
  :class:`~backend.app.providers.session_base.SessionProvider` and is used only
  in the expanded (session) mode where a user account is truly required.

Neither the Content Service nor the Posting Service imports aiogram/Telethon;
all Telegram detail stays behind these adapters (D-001).
"""

from __future__ import annotations

import contextlib

from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.posting_base import PostCapability, PostRequest
from backend.app.providers.session_base import SessionProvider
from backend.app.providers.types import (
    InlineButton,
    PostSendResult,
)


def _button_dicts(buttons: list[list[InlineButton]] | None) -> list[list[dict[str, object]]]:
    rows: list[list[dict[str, object]]] = []
    for row in buttons or []:
        out_row = [
            {"text": b.text, "action": b.action, "value": b.value} for b in row if b.text
        ]
        if out_row:
            rows.append(out_row)
    return rows


class BotPostingProvider:
    """Publish through a Telegram bot (bot-only mode)."""

    kind = "bot"

    def __init__(self, provider: TelegramBotProvider) -> None:
        self._provider = provider

    async def capabilities(self, channel: str) -> PostCapability:
        caps = PostCapability(
            text=True,
            photo=True,
            video=True,
            document=True,
            album=True,
            edit=True,
            delete=True,
            pin=False,
            max_album_items=10,
        )
        # The bot's real rights decide what is actually possible.
        try:
            chat = await self._provider.get_chat(channel)
            caps.message = str(chat.get("title", "") or "")
        except Exception:
            caps.message = "Канал недоступен для бота."
        return caps

    async def send(self, request: PostRequest) -> PostSendResult:
        return await self._provider.send_post(
            request.channel,
            text=request.text,
            entities=request.entities,
            media=list(request.media),
            buttons=_button_dicts(request.buttons),
            disable_notification=request.disable_notification,
        )

    async def send_comment(
        self,
        channel: str,
        post_message_id: int,
        text: str,
        *,
        buttons: list[list[InlineButton]] | None = None,
    ) -> PostSendResult:
        return await self._provider.send_comment(
            channel, post_message_id, text, buttons=_button_dicts(buttons)
        )

    async def edit(self, channel: str, message_id: int, text: str) -> PostSendResult:
        return await self._provider.edit_message(channel, message_id, text)

    async def delete(self, channel: str, message_ids: list[int]) -> PostSendResult:
        return await self._provider.delete_messages(channel, message_ids)

    async def pin(self, channel: str, message_id: int) -> PostSendResult:
        return await self._provider.pin_message(channel, message_id)

    async def linked_discussion(self, channel: str) -> int | None:
        return await self._provider.get_linked_chat(channel)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._provider.close()


class UserPostingProvider:
    """Publish through a Telegram user account (expanded mode only)."""

    kind = "user"

    def __init__(self, provider: SessionProvider) -> None:
        self._provider = provider

    async def capabilities(self, channel: str) -> PostCapability:
        return PostCapability(
            text=True,
            photo=True,
            video=True,
            document=True,
            album=True,
            edit=False,
            delete=True,
            pin=False,
            max_album_items=10,
            message="Публикация от имени аккаунта (расширенный режим).",
        )

    async def send(self, request: PostRequest) -> PostSendResult:
        media_paths = [m.path for m in request.media if m.path]
        result = await self._provider.send_channel_post(
            request.channel,
            text=request.text,
            media_paths=media_paths,
            buttons=_button_dicts(request.buttons),
        )
        return PostSendResult(
            ok=result.ok,
            message_ids=[m.message_id for m in result.items],
            message=result.message,
            how_to_fix=result.how_to_fix,
        )

    async def send_comment(
        self,
        channel: str,
        post_message_id: int,
        text: str,
        *,
        buttons: list[list[InlineButton]] | None = None,
    ) -> PostSendResult:
        # A user account cannot post a "comment" into a channel's discussion
        # group generically; report honestly rather than pretend.
        return PostSendResult(
            ok=False,
            message="Комментарии доступны только через бота канала.",
            how_to_fix="Подключите бота к каналу для первого комментария.",
        )

    async def edit(self, channel: str, message_id: int, text: str) -> PostSendResult:
        return PostSendResult(ok=False, message="Редактирование недоступно аккаунту.")

    async def delete(self, channel: str, message_ids: list[int]) -> PostSendResult:
        ok = await self._provider.delete_channel_messages(channel, message_ids)
        return PostSendResult(ok=ok, message_ids=list(message_ids), message="Удалено.")

    async def pin(self, channel: str, message_id: int) -> PostSendResult:
        return PostSendResult(ok=False, message="Закрепление недоступно аккаунту.")

    async def linked_discussion(self, channel: str) -> int | None:
        return None

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._provider.aclose()


__all__ = ["BotPostingProvider", "UserPostingProvider"]
