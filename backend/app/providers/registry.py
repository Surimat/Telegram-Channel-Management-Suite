"""Provider factory.

Resolves a :class:`TelegramBotProvider` for a bot token. The fake provider is
selected when ``offline_mode`` is on or when ``provider_name == "fake"``, which
lets tests and the offline demo run without real credentials (D-001).
"""

from __future__ import annotations

from pathlib import Path

from backend.app.core.config import Settings, get_settings
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.session_base import SessionProvider


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


def build_session_provider(
    *,
    api_id: str = "",
    api_hash: str = "",
    session_path: Path | None = None,
    provider_name: str = "auto",
    settings: Settings | None = None,
) -> SessionProvider:
    """Return an MTProto :class:`SessionProvider` (PHASE 4).

    ``provider_name`` values match :func:`build_bot_provider`. The fake provider
    is selected when ``offline_mode`` is on or when ``provider_name == "fake"``,
    so tests and the offline demo never touch the network (D-001, D-019).
    """
    settings = settings or get_settings()

    if provider_name == "fake" or (provider_name == "auto" and settings.offline_mode):
        from backend.app.providers.fake_session import FakeSessionProvider

        return FakeSessionProvider(
            api_id=api_id, api_hash=api_hash, session_path=session_path
        )

    from backend.app.providers.telethon_session import TelethonSessionProvider

    return TelethonSessionProvider(
        api_id=api_id,
        api_hash=api_hash,
        session_path=session_path,
        provider_name=provider_name,
        settings=settings,
    )


__all__ = ["SessionProvider", "TelegramBotProvider", "build_bot_provider", "build_session_provider"]
