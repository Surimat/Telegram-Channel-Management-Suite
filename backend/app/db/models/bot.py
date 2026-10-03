"""Bot model: the bot inventory (manager / managed / ordinary).

Tokens are stored **sealed** (encrypted at rest, see ``core.security``); the raw
token is never placed in this table. ``has_token`` lets the UI show whether a
credential is available without ever revealing it.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BotKind(enum.StrEnum):
    MANAGER = "manager"    # the control bot that runs the system
    MANAGED = "managed"    # a child bot created via Telegram Managed Bots
    ORDINARY = "ordinary"  # any other bot added manually (e.g. for reactions)


class BotHealth(enum.StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class Bot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bots"

    kind: Mapped[BotKind] = mapped_column(
        Enum(BotKind, name="bot_kind"), default=BotKind.ORDINARY, index=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Telegram identity (filled after a successful health check).
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    # Sealed token ("enc:..."). Never returned by the API; may be empty for a
    # managed bot that was registered before its token was fetched.
    token_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    provider_name: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)

    # Managed-bot linkage.
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # Whether the manager bot advertises the "can manage bots" capability.
    can_manage_bots: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Health.
    health: Mapped[BotHealth] = mapped_column(
        Enum(BotHealth, name="bot_health"), default=BotHealth.UNKNOWN, nullable=False
    )
    health_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    health_hint: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def has_token(self) -> bool:
        return bool(self.token_encrypted)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Bot kind={self.kind} username={self.username!r} health={self.health}>"
