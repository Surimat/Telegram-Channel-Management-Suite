"""Backup destination model (product slice: pluggable backup providers).

A backup can be delivered to a pluggable :class:`BackupProvider`: local disk
(always available), Google Drive, Yandex Disk, or a Telegram chat via the
manager bot. Every remote destination is optional and off by default; the product
works fully with local backups alone.

OAuth/access credentials are stored **sealed** (encrypted at rest, see
``core.security``) or, preferably, not stored at all — a provider may keep only a
token *reference*. Nothing here is ever returned by the API in plaintext.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DestinationKind(enum.StrEnum):
    LOCAL = "local"
    GOOGLE_DRIVE = "google_drive"
    YANDEX_DISK = "yandex_disk"
    TELEGRAM = "telegram"


class DestinationStatus(enum.StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    WARNING = "warning"
    ERROR = "error"
    DISABLED = "disabled"


DESTINATION_TITLES = {
    DestinationKind.LOCAL: "Локально (этот компьютер)",
    DestinationKind.GOOGLE_DRIVE: "Google Drive",
    DestinationKind.YANDEX_DISK: "Яндекс Диск",
    DestinationKind.TELEGRAM: "Telegram (через бота)",
}


class BackupDestination(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One configured backup destination."""

    __tablename__ = "backup_destinations"

    kind: Mapped[DestinationKind] = mapped_column(
        Enum(DestinationKind, name="destination_kind"),
        default=DestinationKind.LOCAL,
        index=True,
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[DestinationStatus] = mapped_column(
        Enum(DestinationStatus, name="destination_status"),
        default=DestinationStatus.NOT_CONFIGURED,
        nullable=False,
    )

    # Non-secret configuration (folder id, chat id, remote path, account name).
    config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    # Sealed OAuth/token payload ("enc:..."). Never returned by the API.
    credentials_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Human-readable account label (e.g. an email) — safe to display.
    account_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Bytes of free space reported by the provider, when the API exposes it.
    available_space: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BackupDestination kind={self.kind} status={self.status}>"


__all__ = [
    "DESTINATION_TITLES",
    "BackupDestination",
    "DestinationKind",
    "DestinationStatus",
]
