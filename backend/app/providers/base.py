"""Abstract Telegram bot provider (decision D-001).

Business logic depends only on this interface. Real implementations wrap a
Telegram library (aiogram); fake implementations let the whole application be
tested without real credentials or network access.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.providers.types import (
    BotIdentity,
    BotUpdate,
    ManagedBotAccess,
    ManagedBotRef,
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
