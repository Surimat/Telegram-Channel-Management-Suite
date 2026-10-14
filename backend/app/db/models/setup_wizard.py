"""End-to-end Setup Wizard progress model (D-128).

One row per wizard step records the *real* verification the server performed for
that step — when it ran, whether it passed, what the server actually saw, and how
to fix a failure. The step's status is never inferred from the fact that the owner
opened a page or pressed a button; it is the stored outcome of the last
:meth:`SetupWizardService.run_step` execution.

Only non-secret, display-safe data is stored: a machine step key, a boolean, a
short human message, an actionable hint and the channel it concerns. No tokens,
session data, phone numbers or channel contents.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SetupWizardStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The stored, real outcome of one setup step (one row per step key)."""

    __tablename__ = "setup_wizard_steps"

    key: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="unchecked", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    how_to_fix: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: The channel this check concerned (empty when the step is not channel-scoped).
    channel_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    #: When the last real verification ran (``None`` = never checked).
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SetupWizardStep key={self.key!r} verified={self.verified}>"


__all__ = ["SetupWizardStep"]
