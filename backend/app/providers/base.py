"""Abstract Telegram bot provider (decision D-001).

Business logic depends only on this interface. Real implementations wrap a
Telegram library (aiogram); fake implementations let the whole application be
tested without real credentials or network access.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class TelegramBotProvider(Protocol):
    """Operations a manager/reaction bot must support.

    Implementations MUST NOT log or return bot tokens and MUST translate library
    exceptions into :mod:`backend.app.providers.errors`.
    """

    async def close(self) -> None:
        """Release network resources held by the provider."""

    async def get_me(self) -> BotIdentity:
        """Return the bot's own identity (raises on invalid token)."""

    async def health_check(self) -> BotIdentity:
        """Verify the bot is reachable and the token is valid."""

    async def send_message(self, chat_id: int | str, text: str) -> None:
        """Send a text message to a chat."""

    async def set_webhook(self, url: str) -> bool:
        """Register a webhook URL (empty url removes it)."""

    async def set_reaction(
        self, chat_id: int | str, message_id: int, emoji: str
    ) -> None:
        """Set a reaction on a message.

        Telegram allows one reaction per bot per message; passing an empty
        ``emoji`` removes the bot's reaction. Raises
        :class:`~backend.app.providers.errors.FloodWaitError` when Telegram asks
        to wait (never bypassed, D-006).
        """

    # --- Managed bots (official Bot API) -------------------------------------
    async def get_managed_bot_token(self, user_id: int) -> str:
        """Return the access token of a managed bot by its user id."""

    async def replace_managed_bot_token(self, user_id: int) -> str:
        """Revoke the managed bot's current token and return a new one."""

    async def get_managed_bot_access_settings(self, user_id: int) -> ManagedBotAccess:
        """Return the managed bot's access settings."""

    async def set_managed_bot_access_settings(
        self, user_id: int, is_access_restricted: bool, added_user_ids: list[int] | None = None
    ) -> bool:
        """Update the managed bot's access settings."""

    async def get_managed_bots(self) -> list[ManagedBotRef]:
        """Return locally known managed bots.

        Telegram delivers managed-bot creations through updates rather than a
        list endpoint, so this returns what the application has recorded so far.
        """

    # --- Manager bot runtime (post-1.0 hardening) ----------------------------
    async def set_commands(self, commands: list[tuple[str, str]]) -> bool:
        """Register the bot's command menu (best effort).

        Optional: providers without a command-menu API may return ``False``.
        """
        ...

    async def set_menu_button(self, title: str, url: str) -> bool:
        """Point the bot's chat menu button at a Web App (Mini App) URL.

        Optional: providers without a menu-button API may return ``False``. The
        URL must be a public HTTPS URL that Telegram can reach.
        """
        ...

    async def get_updates(
        self, *, offset: int | None = None, timeout: int = 0
    ) -> list[BotUpdate]:
        """Return pending incoming updates for the manager bot.

        ``offset`` acknowledges everything with a smaller ``update_id``. A
        ``timeout`` of 0 returns immediately (used by the short-poll loop). The
        fake provider serves updates from a scripted queue so the whole command
        loop can be tested without Telegram.
        """
        ...

    # --- Bot ↔ channel administration (product slice: bot-only mode) ---------
    async def get_chat(self, chat_id: int | str) -> dict[str, object]:
        """Return basic chat info (id, title, username, type, counts).

        Raises :class:`~backend.app.providers.errors` when the chat cannot be
        resolved. The returned mapping holds only display-safe fields.
        """
        ...

    async def get_bot_channel_status(
        self, chat_id: int | str, bot_id: int
    ) -> BotChannelStatus:
        """Return the *verified* status of ``bot_id`` inside ``chat_id``.

        Uses the official ``getChatMember`` call. Never assumes a permission:
        an unconfirmed right stays ``False``. This is what lets the Reaction
        Manager run without a user session — the bot's own rights are checked
        directly.
        """
        ...

    async def get_reaction_capabilities(self, chat_id: int | str) -> ReactionCapability:
        """Return the reactions Telegram reports as available in ``chat_id``.

        Telegram exposes this per chat (not globally). When it cannot be
        determined, returns ``determined=False`` rather than guessing.
        """
        ...

    async def create_invite_link(
        self,
        chat_id: int | str,
        *,
        name: str = "",
        join_request: bool = False,
        member_limit: int = 0,
        expire_date: int | None = None,
    ) -> InviteLinkResult:
        """Create a named invite link (optionally a join-request link).

        Works with the official Bot API, so promotion via links is available in
        bot-only mode (no user session required).
        """
        ...

    async def export_invite_link(self, chat_id: int | str) -> InviteLinkResult:
        """Return the chat's primary invite link (``exportChatInviteLink``)."""
        ...

    async def revoke_invite_link(self, chat_id: int | str, link: str) -> bool:
        """Revoke an invite link (``revokeChatInviteLink``)."""
        ...

    async def send_document(
        self,
        chat_id: int | str,
        *,
        filename: str,
        content: bytes,
        caption: str = "",
    ) -> bool:
        """Send a file as a document (used by the Telegram backup destination).

        Returns True on success. Callers must never pass session files here
        without an explicit, confirmed opt-in.
        """
        ...

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
        """Publish a message or album with optional inline buttons (v1.2).

        ``media`` is a list of :class:`~backend.app.providers.types.OutgoingMedia`
        and ``buttons`` a list of rows of
        :class:`~backend.app.providers.types.InlineButton`. Albums must respect
        Telegram's item limit (validated before calling). Implementations must
        never log or return tokens.
        """
        ...

    async def send_comment(
        self,
        chat_id: int | str,
        post_message_id: int,
        text: str,
        *,
        buttons: list[list[object]] | None = None,
    ) -> PostSendResult:
        """Post a comment into the discussion group linked to ``chat_id`` (v1.2).

        Returns a result with ``ok=False`` and a clear reason when no discussion
        group is linked (a comment can never be sent as a plain channel post).
        """
        ...

    async def edit_message(
        self, chat_id: int | str, message_id: int, text: str
    ) -> PostSendResult:
        """Edit a message this suite published (v1.2)."""
        ...

    async def delete_messages(
        self, chat_id: int | str, message_ids: list[int]
    ) -> PostSendResult:
        """Delete messages this suite published (v1.2). Never foreign messages."""
        ...

    async def pin_message(
        self, chat_id: int | str, message_id: int
    ) -> PostSendResult:
        """Pin a message when the channel permits it (v1.2)."""
        ...

    async def get_linked_chat(self, chat_id: int | str) -> int | None:
        """Return the linked discussion-group id, or ``None`` (v1.2)."""
        ...
