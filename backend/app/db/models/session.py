"""User-account (MTProto) model for the Session Manager (PHASE 4).

Only non-secret account data is stored here. The API hash is stored **sealed**
(encrypted at rest, see ``core.security``); the session file itself lives on disk
in the sessions directory, outside git, and its *contents* are never stored,
returned, or logged. ``phone`` is stored masked (e.g. ``+7999***4567``).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionStatus(enum.StrEnum):
    """Health/authorization state of a user account."""

    ONLINE = "online"            # authorized and reachable
    AUTH_REQUIRED = "auth_required"  # session present but must sign in again
    DISCONNECTED = "disconnected"    # no valid session file / never connected
    FLOOD_WAIT = "flood_wait"        # Telegram asked us to wait
    ERROR = "error"                  # an unexpected error occurred
    DISABLED = "disabled"            # turned off by the operator


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"

    # Telegram identity (filled after a successful sign-in / health check).
    telegram_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    # Masked phone number (safe to display, e.g. "+7999***4567") and the API id
    # (not secret). The full phone is stored sealed (PII) in ``phone_encrypted``.
    phone_masked: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    api_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    phone_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Sealed api_hash ("enc:..."). Never returned by the API.
    api_hash_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Session file reference: a UUID-based basename only, resolved against the
    # configured sessions directory. Never an absolute path from the client.
    session_ref: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"),
        default=SessionStatus.DISCONNECTED,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Wizard state (for the interactive authorization flow).
    auth_step: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    phone_code_hash: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    # Health.
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status_hint: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Free-form, non-secret metadata added later (e.g. score/tags summary).
    meta: Mapped[str] = mapped_column(Text, default="", nullable=False)

    @property
    def has_session(self) -> bool:
        return bool(self.session_ref)

    @property
    def has_api_hash(self) -> bool:
        return bool(self.api_hash_encrypted)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<UserSession username={self.username!r} status={self.status} "
            f"enabled={self.enabled}>"
        )
