"""Backup provider registry: build a provider by destination kind.

The single switchboard for backup destinations. Adding a destination means adding
a builder here; nothing else in the codebase needs to know the concrete class.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.models.backup_destination import BackupDestination, DestinationKind
from backend.app.db.models.bot import Bot
from backend.app.services.backup_backends.base import BackupProvider, ProviderInfo
from backend.app.services.backup_backends.gdrive import GoogleDriveBackupProvider
from backend.app.services.backup_backends.local import LocalBackupProvider
from backend.app.services.backup_backends.telegram import TelegramBackupProvider
from backend.app.services.backup_backends.yandex import YandexDiskBackupProvider

BotProviderFactory = Callable[..., object]


def _config_of(destination: BackupDestination) -> dict[str, object]:
    import json

    try:
        value = json.loads(destination.config or "{}")
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _token_of(destination: BackupDestination, settings: Settings) -> str:
    if not destination.credentials_encrypted:
        return ""
    try:
        return open_secret(destination.credentials_encrypted, settings)
    except ValueError:
        return ""


def build_backup_provider(
    destination: BackupDestination,
    *,
    settings: Settings | None = None,
    local_dir: Path | None = None,
    manager_bot: Bot | None = None,
    provider_factory: BotProviderFactory | None = None,
) -> BackupProvider:
    """Build the provider for ``destination`` (never raises for bad config)."""
    settings = settings or get_settings()
    config = _config_of(destination)

    if destination.kind is DestinationKind.LOCAL:
        directory = local_dir or settings.resolve_backup_dir()
        return LocalBackupProvider(directory)

    if destination.kind is DestinationKind.TELEGRAM:
        kwargs: dict[str, object] = {}
        if provider_factory is not None:
            kwargs["provider_factory"] = provider_factory
        return TelegramBackupProvider(
            bot=manager_bot, config=config, settings=settings, **kwargs
        )

    if destination.kind is DestinationKind.YANDEX_DISK:
        return YandexDiskBackupProvider(
            token=_token_of(destination, settings),
            folder=str(config.get("folder", "tcms-backups")),
        )

    if destination.kind is DestinationKind.GOOGLE_DRIVE:
        return GoogleDriveBackupProvider(
            token=_token_of(destination, settings),
            folder_id=str(config.get("folder_id", "")),
        )

    # Unknown kind: fall back to local so a backup is never lost.
    return LocalBackupProvider(local_dir or settings.resolve_backup_dir())


PROVIDER_INFOS: tuple[ProviderInfo, ...] = (
    ProviderInfo(
        name=DestinationKind.LOCAL.value,
        title="Локально (этот компьютер)",
        requires_credentials=False,
        help="Копия сохраняется в папку backups рядом с программой.",
    ),
    ProviderInfo(
        name=DestinationKind.GOOGLE_DRIVE.value,
        title="Google Drive",
        requires_credentials=True,
        config_fields=["folder_id"],
        help="Нужен токен доступа Google Drive (хранится зашифрованным).",
    ),
    ProviderInfo(
        name=DestinationKind.YANDEX_DISK.value,
        title="Яндекс Диск",
        requires_credentials=True,
        config_fields=["folder"],
        help="Нужен OAuth-токен Яндекс Диска (хранится зашифрованным).",
    ),
    ProviderInfo(
        name=DestinationKind.TELEGRAM.value,
        title="Telegram (через бота)",
        requires_credentials=False,
        config_fields=["chat_id"],
        help="Копия отправляется в указанный чат управляющим ботом.",
    ),
)


__all__ = ["PROVIDER_INFOS", "build_backup_provider"]
