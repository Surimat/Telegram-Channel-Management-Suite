"""Channel reaction capabilities (product slice: capability negotiation).

Telegram does not offer one global list of reactions that works in every
channel: the set of available reactions, the per-message limit, and whether paid
reactions are enabled are all *per chat* and can change. Assuming a fixed global
list would silently produce reactions Telegram then rejects.

This table stores what Telegram actually reported for a registry channel, so the
Reaction Planner can intersect a profile's emoji with the channel's real
available set and the bot-compatible subset — and, when nothing survives the
intersection, skip the reaction and explain why instead of failing.

Only display-safe data is stored (emoji strings, counts, booleans).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Capability probe outcomes (shown in the UI verbatim).
CAPABILITY_UNKNOWN = "unknown"          # never probed
CAPABILITY_OK = "ok"                    # Telegram reported the available set
CAPABILITY_UNAVAILABLE = "unavailable"  # could not be determined
CAPABILITY_ERROR = "error"              # probe failed

CAPABILITY_MESSAGES = {
    CAPABILITY_UNKNOWN: "Набор реакций канала ещё не проверялся.",
    CAPABILITY_OK: "Набор реакций канала получен от Telegram.",
    CAPABILITY_UNAVAILABLE: "Не удалось определить набор реакций этого канала.",
    CAPABILITY_ERROR: "Не удалось проверить реакции канала.",
}


class ChannelCapabilities(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The last-known reaction capabilities of one registry channel."""

    __tablename__ = "channel_capabilities"

    channel_id: Mapped[str] = mapped_column(
        String(32), index=True, unique=True, nullable=False
    )

    status: Mapped[str] = mapped_column(String(32), default=CAPABILITY_UNKNOWN, nullable=False)

    # JSON array of emoji strings Telegram reports as available in this channel.
    available_reactions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # JSON array of the subset a bot may set (bot-compatible reactions).
    bot_reactions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    # Telegram's per-message reaction limit (0 = unknown).
    reactions_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_reactions_available: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ChannelCapabilities channel={self.channel_id} status={self.status}>"


__all__ = [
    "CAPABILITY_ERROR",
    "CAPABILITY_MESSAGES",
    "CAPABILITY_OK",
    "CAPABILITY_UNAVAILABLE",
    "CAPABILITY_UNKNOWN",
    "ChannelCapabilities",
]
