"""Event model: central log / error center.

Each event carries structured context plus human-readable guidance so the UI can
answer "What happened?" and "How to fix it?" without exposing stack traces.
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EventLevel(enum.StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"

    level: Mapped[EventLevel] = mapped_column(
        Enum(EventLevel, name="event_level"), default=EventLevel.INFO, nullable=False
    )
    module: Mapped[str] = mapped_column(String(64), default="app", nullable=False)
    # e.g. "@mybot", account username, or source label. Never a secret.
    actor: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    operation: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Plain-language guidance shown in the UI.
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    how_to_fix: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Technical detail kept for diagnostics; never the primary UI message.
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_events_level_created", "level", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Event level={self.level} module={self.module!r}>"
