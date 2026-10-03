"""Telegram provider interfaces and implementations.

All Telegram access is behind these abstractions (decision D-001). Real
implementations wrap aiogram; fake implementations let the whole business logic
be tested without a real account or network access.
"""

from backend.app.providers.audience_base import AudienceProvider
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import (
    ApiCredentialsInvalidError,
    AuthCodeExpiredError,
    AuthCodeInvalidError,
    ChatAdminRequiredError,
    EntityNotFoundError,
    FloodWaitError,
    InvalidTokenError,
    NetworkError,
    PasswordInvalidError,
    PasswordRequiredError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    PrivacyRestrictedError,
    SessionInvalidError,
    TelegramProviderError,
    UnauthorizedError,
    UnsupportedOperationError,
)
from backend.app.providers.session_base import SessionProvider
from backend.app.providers.types import (
    BotIdentity,
    EntityRef,
    HealthResult,
    ManagedBotAccess,
    ManagedBotRef,
    ParticipantPage,
    SendCodeResult,
    SessionFileInfo,
    SignInResult,
    UserIdentity,
)

__all__ = [
    "ApiCredentialsInvalidError",
    "AudienceProvider",
    "AuthCodeExpiredError",
    "AuthCodeInvalidError",
    "BotIdentity",
    "ChatAdminRequiredError",
    "EntityNotFoundError",
    "EntityRef",
    "FloodWaitError",
    "HealthResult",
    "InvalidTokenError",
    "ManagedBotAccess",
    "ManagedBotRef",
    "NetworkError",
    "ParticipantPage",
    "PasswordInvalidError",
    "PasswordRequiredError",
    "PhoneNumberBannedError",
    "PhoneNumberInvalidError",
    "PrivacyRestrictedError",
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
