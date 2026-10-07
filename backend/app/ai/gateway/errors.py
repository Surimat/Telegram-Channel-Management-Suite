"""Gateway errors: friendly, RU-first, and never carrying a secret.

Mirrors the style of :mod:`backend.app.ai.errors` so the UI can render a clear
message and a fix hint. The ``category`` maps to the availability statuses in
``types.py`` so the router and health store can react without string-matching the
message text.
"""

from __future__ import annotations

from backend.app.ai.gateway.types import (
    CALL_AUTH_REQUIRED,
    CALL_NETWORK_ERROR,
    CALL_RATE_LIMITED,
    CALL_REGION_BLOCKED,
    CALL_TIMEOUT,
)


class GatewayError(Exception):
    """Base class for gateway failures."""

    def __init__(
        self,
        message: str,
        *,
        how_to_fix: str = "",
        category: str = "error",
        provider: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.category = category
        self.provider = provider


class NoProviderError(GatewayError):
    """No configured provider can serve the request."""

    def __init__(self, message: str, *, how_to_fix: str = "") -> None:
        super().__init__(
            message,
            how_to_fix=how_to_fix or "Добавьте провайдера в разделе «Центр ИИ».",
            category="no_provider",
        )


class ProviderUnavailableError(GatewayError):
    """A provider is not usable right now (disabled, offline, offline runtime)."""

    def __init__(self, message: str, *, provider: str = "", how_to_fix: str = "") -> None:
        super().__init__(
            message,
            how_to_fix=how_to_fix,
            category=CALL_NETWORK_ERROR,
            provider=provider,
        )


class ProviderAuthRequiredError(GatewayError):
    """The provider needs the owner to authenticate first."""

    def __init__(self, message: str, *, provider: str = "", how_to_fix: str = "") -> None:
        super().__init__(
            message,
            how_to_fix=how_to_fix or "Укажите ключ доступа или войдите в сервис.",
            category=CALL_AUTH_REQUIRED,
            provider=provider,
        )


class ProviderRegionBlockedError(GatewayError):
    """The provider is blocked from this region/network."""

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(
            message,
            how_to_fix=(
                "Это ограничение самого сервиса или сети. Проверьте сетевой доступ "
                "самостоятельно — Suite не обходит региональные ограничения."
            ),
            category=CALL_REGION_BLOCKED,
            provider=provider,
        )


class ProviderRateLimitedError(GatewayError):
    """The provider asked us to slow down."""

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(
            message,
            how_to_fix="Подождите немного или включите резервного провайдера.",
            category=CALL_RATE_LIMITED,
            provider=provider,
        )


class ProviderTimeoutError(GatewayError):
    """The provider did not answer in time."""

    def __init__(self, message: str = "", *, provider: str = "") -> None:
        super().__init__(
            message or "Провайдер не ответил вовремя.",
            how_to_fix="Повторим запрос или выберем резервного провайдера.",
            category=CALL_TIMEOUT,
            provider=provider,
        )


class WrapperSelectorError(GatewayError):
    """A Web UI wrapper's selectors no longer match the site (requirement 18)."""

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(
            message,
            how_to_fix=(
                "Интерфейс сайта мог измениться. Обновите определение wrapper "
                "или выберите резервного провайдера."
            ),
            category="wrapper_selector",
            provider=provider,
        )


class BrowserUnavailableError(GatewayError):
    """No browser runtime is installed (Windows portable / Docker)."""

    def __init__(self, message: str = "") -> None:
        super().__init__(
            message or "Браузерный движок не установлен.",
            how_to_fix=(
                "Установите браузерный runtime в разделе «Центр ИИ» → "
                "«Web Wrappers». Обычные API-провайдеры работают и без него."
            ),
            category="browser_unavailable",
        )


__all__ = [
    "BrowserUnavailableError",
    "GatewayError",
    "NoProviderError",
    "ProviderAuthRequiredError",
    "ProviderRateLimitedError",
    "ProviderRegionBlockedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "WrapperSelectorError",
]
