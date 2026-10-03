"""Telegram provider interfaces and implementations.

All Telegram access is behind these abstractions (decision D-001). Real
implementations wrap aiogram; fake implementations let the whole business logic
be tested without a real account or network access.
"""

from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import (
    ApiCredentialsInvalidError,
    AuthCodeExpiredError,
    AuthCodeInvalidError,
    FloodWaitError,
    InvalidTokenError,
    NetworkError,
    PasswordInvalidError,
    PasswordRequiredError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    SessionInvalidError,
    TelegramProviderError,
    UnauthorizedError,
    UnsupportedOperationError,
)
from backend.app.providers.session_base import SessionProvider
from backend.app.providers.types import (
    BotIdentity,
    HealthResult,
    ManagedBotAccess,
    ManagedBotRef,
    SendCodeResult,
    SessionFileInfo,
    SignInResult,
    UserIdentity,
)

__all__ = [
    "ApiCredentialsInvalidError",
    "AuthCodeExpiredError",
    "AuthCodeInvalidError",
    "BotIdentity",
    "FloodWaitError",
    "HealthResult",
    "InvalidTokenError",
    "ManagedBotAccess",
    "ManagedBotRef",
    "NetworkError",
    "PasswordInvalidError",
    "PasswordRequiredError",
    "PhoneNumberBannedError",
    "PhoneNumberInvalidError",
    "SendCodeResult",
    "SessionFileInfo",
    "SessionInvalidError",
    "SessionProvider",
    "SignInResult",
    "TelegramBotProvider",
    "TelegramProviderError",
    "UnauthorizedError",
    "UnsupportedOperationError",
    "UserIdentity",
]
