"""Channel model: the single shared channel/group entity (Channel Registry).

Before this entity, posts, reactions, audience sources, invites and permission
checks each referred to a channel by their own free-form string, so the owner
had to re-select the same channel in every section. The Channel Registry makes
one channel a first-class row that those modules can share (decision D-051).

Only non-secret, display-safe data is stored: a Telegram id/username/title and
the last verification result. No session contents, tokens or API hashes.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChannelKind(enum.StrEnum):
    """Kind of Telegram entity behind the channel."""

    CHANNEL = "channel"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    UNKNOWN = "unknown"


class ChannelStatus(enum.StrEnum):
    """Lifecycle of a registered channel."""

    NEW = "new"            # added, not verified yet
    VERIFIED = "verified"  # a probe succeeded (at least partial access)
    WARNING = "warning"    # reachable but with limited access
    ERROR = "error"        # last verification failed
    DISABLED = "disabled"  # kept for history, excluded from module pickers


class Channel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channels"

    # The reference the owner typed (@username, https://t.me/..., or -100... id).
    reference: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # Telegram identity, filled after verification.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    kind: Mapped[ChannelKind] = mapped_column(
        Enum(ChannelKind, name="channel_kind"), default=ChannelKind.UNKNOWN, nullable=False
    )
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus, name="channel_status"),
        default=ChannelStatus.NEW,
        index=True,
        nullable=False,
    )

    # The primary channel used as the default in every module picker.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Which modules this channel is connected to (JSON bool map, e.g.
    # {"reactions": true, "invites": false}). "Connect modules" in the UI.
    modules: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Last verification result (mirrors the permission-probe status codes).
    verification_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    verification_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verification_hint: Mapped[str] = mapped_column(Text, default="", nullable=False)
    participants_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # --- v2.0 Target Language (additive) ---
    #: Language posts to this channel should be published in. Empty/``auto`` =
    #: inherit the source, then the global default.
    target_language: Mapped[str] = mapped_column(String(8), default="auto", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Channel reference={self.reference!r} status={self.status}>"


__all__ = ["Channel", "ChannelKind", "ChannelStatus"]
