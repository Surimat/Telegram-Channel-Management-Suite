"""Owner identity model (v1.6: Owner Auth + Config Sync).

A single local identity that protects the Suite's configuration. It is **not**
linked to any Telegram account or session: it works fully offline and exists only
to lock the app and to derive the encryption key for the config-sync bundle
(D-105).

The password/PIN is never stored. Only a slow PBKDF2 verifier is kept, together
with a non-secret per-owner ``sync_salt`` used to derive the config-bundle key
from the password the owner types at unlock time. Neither the verifier nor the
derived key is ever returned by the API, logged or included in diagnostics.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OwnerAuthMethod(enum.StrEnum):
    """How the owner unlocks the app."""

    PASSWORD = "password"
    PIN = "pin"


METHOD_TITLES = {
    OwnerAuthMethod.PASSWORD: "Пароль",
    OwnerAuthMethod.PIN: "PIN-код",
}


class OwnerIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The local owner identity (at most one row is used)."""

    __tablename__ = "owner_identities"

    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    method: Mapped[OwnerAuthMethod] = mapped_column(
        Enum(OwnerAuthMethod, name="owner_auth_method"),
        default=OwnerAuthMethod.PASSWORD,
        nullable=False,
    )
    # Slow PBKDF2 verifier ("pbkdf2_sha256$iter$salt$hash"). Never returned.
    verifier: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Non-secret salt used to derive the config-bundle key from the password.
    sync_salt: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # Whether app protection is active. When off, the API is open (local-first).
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Consecutive failed unlock attempts (rate limiting).
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Unlock is refused until this moment after too many failures.
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Optional reminder text chosen by the owner (never the password itself).
    recovery_hint: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OwnerIdentity {self.display_name or 'owner'} enabled={self.enabled}>"


__all__ = ["METHOD_TITLES", "OwnerAuthMethod", "OwnerIdentity"]
