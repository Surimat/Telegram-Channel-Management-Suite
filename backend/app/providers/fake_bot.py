"""Deterministic fake Telegram bot provider.

Used by tests and by the app's offline/dev mode so the full business logic can
run without real credentials or network access. It never performs I/O.
"""

from __future__ import annotations

from backend.app.providers.errors import InvalidTokenError
from backend.app.providers.types import (
    BotIdentity,
    ManagedBotAccess,
    ManagedBotRef,
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
        self.webhook_url: str | None = None
        self.closed = False

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
