"""Telegram provider interfaces and implementations.

All Telegram access is behind these abstractions (decision D-001). Real
implementations wrap aiogram; fake implementations let the whole business logic
be tested without a real account or network access.
"""

from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import (
    FloodWaitError,
    InvalidTokenError,
    NetworkError,
    TelegramProviderError,
    UnauthorizedError,
    UnsupportedOperationError,
)
from backend.app.providers.types import (
    BotIdentity,
    HealthResult,
    ManagedBotAccess,
    ManagedBotRef,
)

__all__ = [
    "BotIdentity",
    "FloodWaitError",
    "HealthResult",
    "InvalidTokenError",
    "ManagedBotAccess",
    "ManagedBotRef",
    "NetworkError",
    "TelegramBotProvider",
    "TelegramProviderError",
    "UnauthorizedError",
    "UnsupportedOperationError",
]
