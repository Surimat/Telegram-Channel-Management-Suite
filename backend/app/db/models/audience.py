"""Audience models (PHASE 5).

Three tables model the audience subsystem:

* :class:`AudienceSource` — a Telegram channel/group/entity we scan.
* :class:`AudienceUser` — one Telegram account, de-duplicated by
  ``telegram_user_id`` (the *only* identity key).
* :class:`SourceUserLink` — a many-to-many edge recording that a user was seen
  in a given source (with per-source first/last-seen and discovery method).

A user can therefore appear in several sources without being duplicated, which
lets the UI answer "in which sources is this user?" and "how many overlaps
between sources?" (decision D-027).

Privacy: the full phone is never stored; only an optional *masked* form, and only
when ``AUDIENCE_STORE_PII`` is enabled (default off). Session contents, api_hash
and raw Telegram errors never live here.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SourceType(enum.StrEnum):
    """Kind of Telegram source."""

    CHANNEL = "channel"
    GROUP = "group"
    ENTITY = "entity"      # resolved by username/id, kind unknown up front
    UNKNOWN = "unknown"


class ScanStatus(enum.StrEnum):
    """Lifecycle of a source scan."""

    IDLE = "idle"              # never scanned / reset
    SCANNING = "scanning"      # a durable job is actively scanning
    PAUSED = "paused"          # operator paused; resumable
    COMPLETED = "completed"    # finished successfully (may still be PARTIAL)
    FAILED = "failed"          # finished with an error
    CANCELLED = "cancelled"    # operator cancelled


class Completeness(enum.StrEnum):
    """How complete the last scan's result is (decision D-026).

    Telegram sometimes returns only part of a member list; the system must make
    that explicit rather than pretending the list is complete.
    """

    UNKNOWN = "unknown"
    COMPLETE = "complete"
    PARTIAL = "partial"        # Telegram hid part of the audience
    FAILED = "failed"
    NO_ACCESS = "no_access"    # Telegram refused the list entirely


class MemberStatus(enum.StrEnum):
    """Coarse status of an audience member."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"
    BLOCKED = "blocked"   # reserved for the Invite Manager (PHASE 6)
    UNKNOWN = "unknown"


class AudienceSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audience_sources"

    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="audience_source_type"),
        default=SourceType.UNKNOWN,
        nullable=False,
    )
    # The raw reference the operator entered (username, link, or id).
    reference: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # Optional link to the shared Channel Registry (decision D-051): when the
    # owner picks a registered channel, its reference is reused here.
    channel_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Which user account performs the scan (nullable → any healthy account).
    account_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user_sessions.id", ondelete="SET NULL"), nullable=True
    )

    scan_status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="audience_scan_status"),
        default=ScanStatus.IDLE,
        index=True,
        nullable=False,
    )
    completeness: Mapped[Completeness] = mapped_column(
        Enum(Completeness, name="audience_completeness"),
        default=Completeness.UNKNOWN,
        nullable=False,
    )

    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scan_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Counters from the last scan.
    discovered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Telegram's reported participant total (may exceed what we could fetch).
    reported_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Progress of the in-flight scan (persisted so it survives a restart).
    scanned_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scan_job_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Non-secret metadata (e.g. resolved kind, flags) as JSON text.
    meta: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_audience_sources_telegram_id"),
        Index("ix_audience_sources_status", "scan_status", "enabled"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AudienceSource title={self.title!r} status={self.scan_status} "
            f"completeness={self.completeness}>"
        )


class AudienceUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audience_users"

    # De-duplication key: one Telegram account == one row.
    telegram_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    first_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    last_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Optional, masked PII — stored only when AUDIENCE_STORE_PII is enabled.
    phone_masked: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    is_premium: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    status: Mapped[MemberStatus] = mapped_column(
        Enum(MemberStatus, name="audience_member_status"),
        default=MemberStatus.UNKNOWN,
        index=True,
        nullable=False,
    )

    # Transparent, explainable technical score (see AudienceService.score_components).
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    score_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # User tags (JSON list of strings) and free-form metadata (JSON text).
    tags: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    meta: Mapped[str] = mapped_column(Text, default="", nullable=False)

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )

    # --- Invite Manager extension point (PHASE 6) ---------------------------
    invite_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    invite_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_invite_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invite_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("telegram_user_id", name="uq_audience_users_telegram_user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AudienceUser id={self.telegram_user_id} username={self.username!r}>"


class SourceUserLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Association between an :class:`AudienceUser` and an :class:`AudienceSource`."""

    __tablename__ = "audience_source_users"

    source_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("audience_sources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("audience_users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "participants" | "admin" | "import" | "manual"
    discovery_method: Mapped[str] = mapped_column(
        String(32), default="participants", nullable=False
    )
    meta: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "user_id", name="uq_source_user"),
        Index("ix_source_users_source_user", "source_id", "user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SourceUserLink source={self.source_id} user={self.user_id}>"
