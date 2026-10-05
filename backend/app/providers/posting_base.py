"""Posting provider abstraction (v1.2: Content Studio posting engine).

A :class:`PostingProvider` publishes prepared content to a channel. Bot posting
goes through the existing :class:`TelegramBotProvider`; user-account posting goes
through the existing :class:`SessionProvider` — the Content/Posting services
never import aiogram or Telethon directly (D-001).

Capabilities: text, photo, video, document, album, edit, delete, pin (when the
Bot API and the channel's verified rights allow it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from backend.app.providers.types import (
    InlineButton,
    OutgoingMedia,
    PostSendResult,
)


@dataclass(slots=True)
class PostRequest:
    """Everything needed to publish one message/album."""

    channel: str = ""            # numeric id or @username
    text: str = ""
    #: Telegram-style entities (list of dicts) applied to ``text``.
    entities: list[dict[str, object]] = field(default_factory=list)
    media: list[OutgoingMedia] = field(default_factory=list)
    buttons: list[list[InlineButton]] = field(default_factory=list)
    disable_notification: bool = False


@dataclass(slots=True)
class PostCapability:
    """Which posting operations a provider/channel supports (honest)."""

    text: bool = True
    photo: bool = False
    video: bool = False
    document: bool = False
    album: bool = False
    edit: bool = False
    delete: bool = False
    pin: bool = False
    max_album_items: int = 10
    message: str = ""


@runtime_checkable
class PostingProvider(Protocol):
    """Publish prepared content to a Telegram channel."""

    @property
    def kind(self) -> str:
        """``bot`` or ``user``."""
        ...

    async def capabilities(self, channel: str) -> PostCapability:
        """Return the operations actually available for ``channel``."""
        ...

    async def send(self, request: PostRequest) -> PostSendResult:
        """Publish a message or album (with optional buttons)."""
        ...

    async def send_comment(
        self, channel: str, post_message_id: int, text: str,
        *, buttons: list[list[InlineButton]] | None = None,
    ) -> PostSendResult:
        """Publish a first comment into the channel's linked discussion group."""
        ...

    async def edit(self, channel: str, message_id: int, text: str) -> PostSendResult:
        """Edit an existing message."""
        ...

    async def delete(self, channel: str, message_ids: list[int]) -> PostSendResult:
        """Delete messages this suite published (never foreign messages)."""
        ...

    async def pin(self, channel: str, message_id: int) -> PostSendResult:
        """Pin a message when the channel permits it."""
        ...

    async def linked_discussion(self, channel: str) -> int | None:
        """Return the linked discussion-group id, or ``None``."""
        ...


__all__ = [
    "PostCapability",
    "PostRequest",
    "PostingProvider",
]
