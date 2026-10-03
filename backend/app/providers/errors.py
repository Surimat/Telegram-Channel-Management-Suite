"""Provider-level errors, translated into human-readable guidance.

Domain/services never see raw library exceptions: providers raise these, each
carrying a friendly ``message`` and an actionable ``how_to_fix`` so the UI can
answer "what happened?" and "how do I fix it?" (see docs/UI.md, decision D-016).

``technical`` holds diagnostic detail and MUST NEVER contain secrets.
"""

from __future__ import annotations


class TelegramProviderError(Exception):
    """Base class for all provider failures."""

    def __init__(
        self,
        message: str,
        *,
        how_to_fix: str = "",
        technical: str = "",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.technical = technical
        # Seconds to wait (Telegram FloodWait); None when not applicable.
        self.retry_after = retry_after


class InvalidTokenError(TelegramProviderError):
    """The bot token is malformed or rejected by Telegram."""


class UnauthorizedError(TelegramProviderError):
    """The token is valid but the bot is not allowed to perform the action."""


class FloodWaitError(TelegramProviderError):
    """Telegram asked us to wait before retrying (never bypassed, D-006)."""

    def __init__(self, retry_after: int, **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Подождите указанное время — это ограничение Telegram, обходить его нельзя.",
        )
        super().__init__(
            f"Telegram просит подождать {retry_after} сек. перед повтором.",
            retry_after=retry_after,
            **kwargs,  # type: ignore[arg-type]
        )


class NetworkError(TelegramProviderError):
    """Could not reach Telegram (offline, DNS, proxy)."""


class UnsupportedOperationError(TelegramProviderError):
    """The requested managed-bot operation is not available for this bot."""
