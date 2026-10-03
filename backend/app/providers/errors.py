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


# --- MTProto user-account errors (PHASE 4) -----------------------------------


class SessionInvalidError(TelegramProviderError):
    """The session file is missing, corrupt or no longer authorized."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Удалите аккаунт и добавьте его заново или импортируйте актуальный "
            "session-файл.",
        )
        super().__init__(
            message or "Сессия недействительна или больше не авторизована.",
            **kwargs,  # type: ignore[arg-type]
        )


class AuthCodeInvalidError(TelegramProviderError):
    """The login code was rejected by Telegram."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Проверьте код из Telegram. Если код устарел, запросите новый.",
        )
        super().__init__(message or "Неверный код подтверждения.", **kwargs)  # type: ignore[arg-type]


class AuthCodeExpiredError(TelegramProviderError):
    """The login code expired before it was submitted."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Запросите новый код и введите его быстрее.",
        )
        super().__init__(message or "Код подтверждения истёк.", **kwargs)  # type: ignore[arg-type]


class PasswordRequiredError(TelegramProviderError):
    """The account has two-factor authentication enabled (a password is needed)."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Введите пароль двухэтапной аутентификации (облачный пароль Telegram).",
        )
        super().__init__(message or "Для входа нужен пароль двухэтапной аутентификации.", **kwargs)  # type: ignore[arg-type]


class PasswordInvalidError(TelegramProviderError):
    """The submitted two-factor password was rejected."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Проверьте облачный пароль Telegram и попробуйте снова.",
        )
        super().__init__(message or "Неверный пароль двухэтапной аутентификации.", **kwargs)  # type: ignore[arg-type]


class PhoneNumberInvalidError(TelegramProviderError):
    """The phone number format or value was rejected."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Укажите номер в международном формате, например +79991234567.",
        )
        super().__init__(message or "Номер телефона указан неверно.", **kwargs)  # type: ignore[arg-type]


class PhoneNumberBannedError(TelegramProviderError):
    """Telegram refused the phone number (banned or too many attempts)."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Этот номер временно ограничен Telegram. Попробуйте позже или другой номер.",
        )
        super().__init__(message or "Telegram отклонил этот номер телефона.", **kwargs)  # type: ignore[arg-type]


class ApiCredentialsInvalidError(TelegramProviderError):
    """The API ID / API Hash pair was rejected."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Проверьте API ID и API Hash на https://my.telegram.org "
            "(раздел API development tools).",
        )
        super().__init__(
            message or "API ID или API Hash указаны неверно.", **kwargs  # type: ignore[arg-type]
        )


# --- Audience / entity errors (PHASE 5) --------------------------------------


class EntityNotFoundError(TelegramProviderError):
    """The channel/group/entity could not be resolved."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Проверьте username или ссылку. Для закрытых источников аккаунт "
            "должен состоять в них.",
        )
        super().__init__(
            message or "Не удалось найти этот канал, группу или пользователя.",
            **kwargs,  # type: ignore[arg-type]
        )


class PrivacyRestrictedError(TelegramProviderError):
    """Telegram hides the data (participant list hidden, privacy settings)."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Telegram не раскрывает этот список для данного аккаунта. "
            "Используйте публичный источник или аккаунт с доступом.",
        )
        super().__init__(
            message or "Telegram ограничил доступ к этим данным.",
            **kwargs,  # type: ignore[arg-type]
        )


class ChatAdminRequiredError(TelegramProviderError):
    """The action requires admin rights in the target chat."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault(
            "how_to_fix",
            "Для этого действия аккаунт должен быть администратором источника.",
        )
        super().__init__(
            message or "Требуются права администратора в этом чате.", **kwargs  # type: ignore[arg-type]
        )


# --- Invite errors (PHASE 6) -------------------------------------------------


class AlreadyParticipantError(TelegramProviderError):
    """The user is already a member of the target chat (not a failure)."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        kwargs.setdefault("how_to_fix", "")
        super().__init__(
            message or "Пользователь уже состоит в целевом канале.", **kwargs  # type: ignore[arg-type]
        )
