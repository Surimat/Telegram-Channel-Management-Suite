"""Promotion-wizard progress model (product slice: onboarding).

The wizard is mostly *derived*: each step's status is computed from the real
state (are bots bound? is a session present? are campaigns configured?). This
small row only stores the owner's choices — the selected preset, whether the
wizard was finished or dismissed, and the last step they were on — so the flow is
resumable and never restarts from scratch.

No secrets, no user data: just identifiers and a timestamp.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Preset identifiers (see promotion_service.PRESETS).
PRESET_MINIMAL = "minimal"
PRESET_BOT_ONLY = "bot_only"
PRESET_BASIC = "basic"
PRESET_ADVANCED = "advanced"
PRESET_PROFESSIONAL = "professional"


class PromotionProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Owner choices for the promotion wizard (single active row)."""

    __tablename__ = "promotion_progress"

    preset: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    current_step: Mapped[str] = mapped_column(String(32), default="channel", nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PromotionProgress preset={self.preset!r} step={self.current_step}>"


__all__ = [
    "PRESET_ADVANCED",
    "PRESET_BASIC",
    "PRESET_BOT_ONLY",
    "PRESET_MINIMAL",
    "PRESET_PROFESSIONAL",
    "PromotionProgress",
]
