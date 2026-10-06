"""Config-sync state model (v1.6: Owner Auth + Config Sync).

Stores only **non-secret** bookkeeping about the versioned encrypted bundle:
which provider is selected, the last known cloud revision and device, and the
last sync outcome. The bundle itself lives in the provider (a local file or
Google Drive app-data) and is always encrypted; no plaintext configuration is
ever stored here (D-106).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SyncProviderKind(enum.StrEnum):
    """Available config-sync providers."""

    NONE = "none"
    LOCAL = "local"
    GOOGLE_DRIVE = "google_drive"


PROVIDER_TITLES = {
    SyncProviderKind.NONE: "Не выбран",
    SyncProviderKind.LOCAL: "Локальная папка",
    SyncProviderKind.GOOGLE_DRIVE: "Google Drive",
}

#: Capability-ish states for the config-sync subsystem.
SYNC_STATE_UNAVAILABLE = "unavailable"
SYNC_STATE_NEEDS_SETUP = "needs_setup"
SYNC_STATE_AVAILABLE = "available"
SYNC_STATE_ERROR = "error"

STATE_TITLES = {
    SYNC_STATE_UNAVAILABLE: "Недоступно",
    SYNC_STATE_NEEDS_SETUP: "Требуется настройка",
    SYNC_STATE_AVAILABLE: "Доступно",
    SYNC_STATE_ERROR: "Ошибка",
}


class ConfigSyncState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-row state of the config-sync subsystem."""

    __tablename__ = "config_sync_state"

    provider: Mapped[SyncProviderKind] = mapped_column(
        Enum(SyncProviderKind, name="sync_provider_kind"),
        default=SyncProviderKind.NONE,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # OAuth tokens for Google Drive, sealed (Fernet). Never returned by the API.
    oauth_token_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # OAuth refresh token, sealed. Never returned.
    oauth_refresh_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Stable per-install device id (random, non-secret) used for conflict labels.
    device_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    device_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # Local bundle revision (incremented on every local config change).
    local_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Last known cloud bundle revision + owning device.
    cloud_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cloud_device: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    cloud_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    last_message: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ConfigSyncState {self.provider} enabled={self.enabled}>"


__all__ = [
    "PROVIDER_TITLES",
    "STATE_TITLES",
    "SYNC_STATE_AVAILABLE",
    "SYNC_STATE_ERROR",
    "SYNC_STATE_NEEDS_SETUP",
    "SYNC_STATE_UNAVAILABLE",
    "ConfigSyncState",
    "SyncProviderKind",
]
