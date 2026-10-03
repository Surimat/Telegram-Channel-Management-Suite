"""Provider factory.

Resolves a :class:`TelegramBotProvider` for a bot token. The fake provider is
selected when ``offline_mode`` is on or when ``provider_name == "fake"``, which
lets tests and the offline demo run without real credentials (D-001).
"""

from __future__ import annotations

from backend.app.core.config import Settings, get_settings
from backend.app.providers.base import TelegramBotProvider


def build_bot_provider(
    token: str,
    *,
    provider_name: str = "auto",
    settings: Settings | None = None,
) -> TelegramBotProvider:
    """Return a provider for ``token``.

    ``provider_name`` values:
    - ``"auto"``: real provider, unless ``settings.offline_mode`` is set.
    - ``"aiogram"``: always the real provider.
    - ``"fake"``: always the deterministic fake provider.
    """
    settings = settings or get_settings()

    if provider_name == "fake" or (provider_name == "auto" and settings.offline_mode):
        from backend.app.providers.fake_bot import FakeTelegramBotProvider

        return FakeTelegramBotProvider(token)

    from backend.app.providers.aiogram_bot import AiogramBotProvider

    return AiogramBotProvider(token)


__all__ = ["TelegramBotProvider", "build_bot_provider"]
