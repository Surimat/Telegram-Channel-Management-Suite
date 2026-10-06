"""Notification Center models (v1.4).

Turns the in-process notification bus into a durable, inspectable center:

* :class:`NotificationRecord` — one notification (category, priority, message,
  routing destination, delivery status, dedup key). History is queryable so the
  owner can see what happened and what failed.
* :class:`NotificationDelivery` — one delivery attempt per destination, so a
  notification that could not be delivered (e.g. Windows toast unavailable) is
  visible without breaking the app.

Only non-secret, display-safe data is stored: no tokens, session contents or
API hashes ever reach these tables.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationPriority(enum.StrEnum):
    """How urgent a notification is (drives quiet-hours behaviour)."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


PRIORITY_ORDER = {
    NotificationPriority.INFO: 0,
    NotificationPriority.SUCCESS: 1,
    NotificationPriority.WARNING: 2,
    NotificationPriority.ERROR: 3,
    NotificationPriority.CRITICAL: 4,
}

PRIORITY_TITLES = {
    NotificationPriority.INFO: "Информация",
    NotificationPriority.SUCCESS: "Успех",
    NotificationPriority.WARNING: "Предупреждение",
    NotificationPriority.ERROR: "Ошибка",
    NotificationPriority.CRITICAL: "Критично",
}

#: Priorities that are delivered immediately even during quiet hours.
URGENT_PRIORITIES = frozenset(
    {NotificationPriority.WARNING, NotificationPriority.ERROR, NotificationPriority.CRITICAL}
)


class NotificationDestination(enum.StrEnum):
    """Where a notification can be delivered."""

    TELEGRAM_OWNER = "telegram_owner"  # manager/notification bot → owner DM
    TELEGRAM_GROUP = "telegram_group"  # an editorial / notification group
    WINDOWS_TOAST = "windows_toast"
    NONE = "none"


NOTIFICATION_DESTINATION_TITLES = {
    NotificationDestination.TELEGRAM_OWNER: "Telegram владельцу",
    NotificationDestination.TELEGRAM_GROUP: "Telegram-группа",
    NotificationDestination.WINDOWS_TOAST: "Windows-уведомление",
    NotificationDestination.NONE: "Не отправлять",
}


class NotificationStatus(enum.StrEnum):
    """Delivery lifecycle of one notification."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"          # category disabled / routed to none
    POSTPONED = "postponed"      # held until quiet hours end
    AGGREGATED = "aggregated"    # merged into a summary notification


STATUS_TITLES = {
    NotificationStatus.PENDING: "В очереди",
    NotificationStatus.SENT: "Отправлено",
    NotificationStatus.FAILED: "Ошибка отправки",
    NotificationStatus.SKIPPED: "Пропущено",
    NotificationStatus.POSTPONED: "Отложено",
    NotificationStatus.AGGREGATED: "Объединено",
}


class NotificationRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    category: Mapped[str] = mapped_column(String(32), default="system", index=True, nullable=False)
    priority: Mapped[NotificationPriority] = mapped_column(
        Enum(NotificationPriority, name="notification_priority"),
        default=NotificationPriority.INFO,
        index=True,
        nullable=False,
    )
    destination: Mapped[NotificationDestination] = mapped_column(
        Enum(NotificationDestination, name="notification_destination"),
        default=NotificationDestination.TELEGRAM_OWNER,
        nullable=False,
    )
    # Stable identifier used for routing and de-duplication (e.g. app.started).
    event_key: Mapped[str] = mapped_column(String(128), default="", index=True, nullable=False)
    # Deterministic key for anti-spam aggregation (category + event_key).
    dedup_key: Mapped[str] = mapped_column(String(160), default="", index=True, nullable=False)
    # Source module for diagnostics (never a secret).
    source_module: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    how_to_fix: Mapped[str] = mapped_column(Text, default="", nullable=False)

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"),
        default=NotificationStatus.PENDING,
        index=True,
        nullable=False,
    )
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Number of identical notifications merged into this one (anti-spam).
    aggregate_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # When set, a postponed (quiet-hours) notification becomes due at this time.
    postponed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read: Mapped[bool] = mapped_column(default=False, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<NotificationRecord {self.category}/{self.priority} "
            f"status={self.status} key={self.event_key!r}>"
        )


class NotificationDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notification_deliveries"

    notification_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    destination: Mapped[NotificationDestination] = mapped_column(
        Enum(NotificationDestination, name="notification_destination"),
        default=NotificationDestination.TELEGRAM_OWNER,
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"),
        default=NotificationStatus.PENDING,
        nullable=False,
    )
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<NotificationDelivery {self.destination} status={self.status}>"


__all__ = [
    "NOTIFICATION_DESTINATION_TITLES",
    "PRIORITY_ORDER",
    "PRIORITY_TITLES",
    "STATUS_TITLES",
    "URGENT_PRIORITIES",
    "NotificationDelivery",
    "NotificationDestination",
    "NotificationPriority",
    "NotificationRecord",
    "NotificationStatus",
]
