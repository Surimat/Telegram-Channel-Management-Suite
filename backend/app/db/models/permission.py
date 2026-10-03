"""Permission-probe result model (post-1.0 hardening).

Stores the last "check account access to channel" result so the Dashboard can
show it and the operator can review history. Only non-secret data is kept; no
session contents, tokens or API hashes are ever stored here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PermissionCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permission_checks"

    account_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    account_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    target: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    target_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Machine code: ok | partial | no_access | auth_required | admin_required |
    # privacy_restricted | flood_wait | error
    status: Mapped[str] = mapped_column(String(32), default="error", index=True, nullable=False)

    channel_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_read_info: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_read_participants: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_invite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    participants_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    how_to_fix: Mapped[str] = mapped_column(Text, default="", nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PermissionCheck target={self.target!r} status={self.status}>"
