"""Reaction models (PHASE 3): profile, rule and job.

* :class:`ReactionProfile` — a named, UI-editable reaction configuration.
* :class:`ReactionRule` — an editable classification rule (Rules Engine data).
* :class:`ReactionJob` — one scheduled reaction: post × bot × emoji.

Reaction jobs are durable rows so the React Manager survives restarts: on start
the scheduler re-claims them (see ``agent/DECISIONS.md`` D-008). A job's
``id`` is also the payload reference of the underlying durable queue ``Job``.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DelayPresetDB(enum.StrEnum):
    EARLY = "early"
    NORMAL = "normal"
    SPREAD = "spread"


class ReactionJobStatus(enum.StrEnum):
    PLANNED = "planned"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ReactionProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named reaction configuration, editable from the Web UI."""

    __tablename__ = "reaction_profiles"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Emoji policy: JSON arrays of emoji strings (see services/reaction_service).
    allowed_emoji: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    emoji_weights: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # "Вероятность участия бота" — chance a given active bot takes part.
    participation_probability: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    # "Вероятность пропуска" — chance a participating bot still skips.
    skip_probability: Mapped[float] = mapped_column(Float, default=0.1, nullable=False)

    # Per-bot delay window (seconds), randomized within it.
    delay_min: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    delay_max: Mapped[float] = mapped_column(Float, default=900.0, nullable=False)
    delay_preset: Mapped[DelayPresetDB] = mapped_column(
        Enum(DelayPresetDB, name="delay_preset"), default=DelayPresetDB.NORMAL, nullable=False
    )

    max_bots_per_post: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReactionProfile name={self.name!r} enabled={self.enabled}>"


class ReactionRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An editable classification rule consumed by the Rules Engine."""

    __tablename__ = "reaction_rules"

    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="", nullable=False)

    # JSON arrays.
    keywords: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    phrases: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    regexes: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    exclusions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    allowed_reactions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    preferred_reactions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    forbidden_reactions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReactionRule category={self.category!r} priority={self.priority}>"


class ReactionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One scheduled reaction: a single bot reacting to a single post."""

    __tablename__ = "reaction_jobs"

    post_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    bot_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    reaction: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    status: Mapped[ReactionJobStatus] = mapped_column(
        Enum(ReactionJobStatus, name="reaction_job_status"),
        default=ReactionJobStatus.PLANNED,
        index=True,
        nullable=False,
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Durable queue job that drives execution (empty for pure simulations).
    queue_job_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ReactionJob post={self.post_id} bot={self.bot_id} status={self.status}>"


__all__ = [
    "DelayPresetDB",
    "ReactionJob",
    "ReactionJobStatus",
    "ReactionProfile",
    "ReactionRule",
]
