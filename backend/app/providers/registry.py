"""Provider factory.

Resolves a :class:`TelegramBotProvider` for a bot token. The fake provider is
selected when ``offline_mode`` is on or when ``provider_name == "fake"``, which
lets tests and the offline demo run without real credentials (D-001).

The deterministic fakes exist for the offline demo and the test suite, never as a
silent production fallback. Outside ``app_env`` ``demo``/``test`` a fake is refused
with a typed :class:`ProviderConfigurationError` and a warning is logged, so the
panel can never "work" on fabricated data without the owner noticing.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.providers.audience_base import AudienceProvider
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import ProviderConfigurationError
from backend.app.providers.session_base import SessionProvider

logger = get_logger(__name__)

#: The only environments in which the deterministic fake providers may be used.
#: Everywhere else they are refused, because a stub that silently fabricates data
#: instead of talking to Telegram is a lie the owner cannot see.
FAKE_ENVIRONMENTS = {"demo", "test"}


def _env_of(settings: Settings) -> str:
    return (settings.app_env or "").strip().lower()


def _reject_fake_outside_allowed_envs(settings: Settings, *, what: str) -> None:
    """Refuse a fake provider outside demo/test; raise with an actionable hint.

    The demo and the test suite legitimately need the fakes, so ``app_env``
    ``demo``/``test`` are allowed. Any other environment — including
    ``production`` and a bare default ``development`` — is refused: a silent
    fallback to fabricated data would be a lie the owner cannot see (D-001).
    """
    env = _env_of(settings)
    if env in FAKE_ENVIRONMENTS:
        return
    logger.warning(
        "Запрошен режим «эмуляция» (%s) в окружении %r — отказ: заглушка "
        "недопустима вне режимов «demo»/«test».",
        what,
        env,
    )
    raise ProviderConfigurationError(
        f"Режим «эмуляция» ({what}) доступен только в режимах «demo» и «test».",
        how_to_fix=(
            "Укажите настоящий режим подключения (aiogram/telethon) или "
            "запустите приложение в режиме «demo»/«test»."
        ),
        technical=f"fake {what} requested with app_env={env!r}",
    )


def _wants_fake(provider_name: str, settings: Settings) -> bool:
    return provider_name == "fake" or (
        provider_name == "auto" and settings.offline_mode
    )


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
    - ``"fake"``: the deterministic fake provider (refused in production).
    """
    settings = settings or get_settings()

    if _wants_fake(provider_name, settings):
        _reject_fake_outside_allowed_envs(settings, what="telegram_provider=fake")
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
    proxy: dict[str, object] | None = None,
) -> SessionProvider:
    """Return an MTProto :class:`SessionProvider` (PHASE 4).

    ``provider_name`` values match :func:`build_bot_provider`. The fake provider
    is selected when ``offline_mode`` is on or when ``provider_name == "fake"``,
    so tests and the offline demo never touch the network (D-001, D-019). A real
    session provider is returned otherwise, and it raises
    :class:`ProviderConfigurationError` itself when no session/API credentials
    exist — the service layer surfaces that as an honest configuration error
    instead of fabricating data.

    ``proxy`` is an optional Telethon proxy dict (a normal network route, never a
    limit-bypass mechanism — D-006/D-066).
    """
    settings = settings or get_settings()

    if _wants_fake(provider_name, settings):
        _reject_fake_outside_allowed_envs(settings, what="telegram_provider=fake")
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
        proxy=proxy,
    )


def build_config_sync_provider(
    kind: str,
    *,
    directory: Path | None = None,
    transport: object | None = None,
) -> object:
    """Return a :class:`ConfigSyncProvider` for ``kind`` (v1.6).

    ``"local"`` uses a folder on disk; ``"google_drive"`` uses an authorized
    Drive transport (``None`` when the owner has not connected Google Drive yet,
    in which case the provider reports itself unavailable). ``"none"`` returns a
    provider that is never available. The fake transport is injected in tests, so
    CI never touches Google (D-106).
    """
    if kind == "local":
        from backend.app.providers.config_sync_local import LocalConfigSyncProvider

        return LocalConfigSyncProvider(directory or Path("./sync"))

    if kind == "google_drive":
        from backend.app.providers.config_sync_gdrive import (
            GoogleDriveConfigSyncProvider,
        )

        return GoogleDriveConfigSyncProvider(transport)  # type: ignore[arg-type]

    from backend.app.providers.config_sync_local import LocalConfigSyncProvider

    return LocalConfigSyncProvider(Path("./sync-disabled"))


def build_audience_provider(
    session_provider: SessionProvider,
    *,
    provider_name: str = "auto",
    settings: Settings | None = None,
) -> AudienceProvider:
    """Return an :class:`AudienceProvider` for scanning (PHASE 5).

    The real adapter delegates to ``session_provider`` (so MTProto access stays
    behind the PHASE 4 interface); offline/test mode uses a pure fake when
    ``offline_mode`` is on or ``provider_name == "fake"``.
    """
    settings = settings or get_settings()

    if _wants_fake(provider_name, settings):
        _reject_fake_outside_allowed_envs(settings, what="telegram_provider=fake")
        from backend.app.providers.fake_audience import FakeAudienceProvider

        return FakeAudienceProvider()

    from backend.app.providers.session_audience import SessionAudienceProvider

    return SessionAudienceProvider(session_provider)


__all__ = [
    "SessionProvider",
    "TelegramBotProvider",
    "build_audience_provider",
    "build_bot_provider",
    "build_session_provider",
]
