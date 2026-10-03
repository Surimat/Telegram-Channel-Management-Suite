"""Invite models (PHASE 6): a durable, restart-safe invite queue.

An :class:`InviteJob` is one operator-initiated bulk-invite run: a set of source
filters, a target channel, and the chosen user accounts. Its per-target work is
split into :class:`InviteTask` rows (one audience user → one target, assigned to
one account), which are the durable unit the scheduler executes.

Design notes
------------
* Nothing runs until the operator confirms the dry-run summary
  (``confirmed_at``), satisfying the mass-operation safeguard (docs/SECURITY.md).
* Limits are configurable per job, never hard-coded.
* Telegram server limits (FloodWait / privacy / admin) are recorded as honest
  task/account state, never bypassed (decision D-006).
* A job is a durable row so an interrupted run is recovered on restart (D-008);
  the underlying queue ``Job`` shares the same id via ``queue_job_id``.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InviteJobStatus(enum.StrEnum):
    """Lifecycle of an invite run."""

    DRAFT = "draft"            # created but not confirmed/started
    READY = "ready"            # confirmed, tasks planned, not started
    RUNNING = "running"        # actively inviting
    PAUSED = "paused"          # operator or FloodWait paused it; resumable
    COMPLETED = "completed"    # all tasks finished (some may have failed)
    STOPPED = "stopped"        # operator stopped it
    FAILED = "failed"          # unrecoverable error


class InviteStatus(enum.StrEnum):
    """Per-target invite outcome."""

    PENDING = "pending"        # queued, not attempted yet
    RUNNING = "running"        # an attempt is in flight
    INVITED = "invited"        # successfully invited
    ALREADY_MEMBER = "already_member"  # was already in the target
    SKIPPED = "skipped"        # filtered out by the dry-run rarely; reserved
    PRIVACY = "privacy"        # target's privacy settings forbid invites
    FLOOD_WAIT = "flood_wait"  # account asked to wait
    ADMIN_REQUIRED = "admin_required"  # account lacks rights on the target
    FAILED = "failed"          # other error


# Statuses that mean "no further attempt is expected by this run".
TERMINAL_INVITE_STATUSES = frozenset(
    {
        InviteStatus.INVITED,
        InviteStatus.ALREADY_MEMBER,
        InviteStatus.PRIVACY,
        InviteStatus.ADMIN_REQUIRED,
        InviteStatus.SKIPPED,
    }
)


class InviteJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A bulk-invite run, confirmed before it starts."""

    __tablename__ = "invite_jobs"

    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    # Target channel/group (what people are invited *to*).
    target: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    target_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # Optional link to the shared Channel Registry (decision D-051).
    channel_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)

    # Chosen accounts (JSON list of session ids) and sources (JSON list of ids).
    account_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # Snapshot of the filters applied when the job was built (JSON object).
    filters: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    status: Mapped[InviteJobStatus] = mapped_column(
        Enum(InviteJobStatus, name="invite_job_status"),
        default=InviteJobStatus.DRAFT,
        index=True,
        nullable=False,
    )

    # Confirmation (mass-operation safeguard). Set when the operator confirms
    # the dry-run summary; nothing is enqueued before this.
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_summary: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Configurable limits/behaviour for this run.
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    per_account_delay_min: Mapped[float] = mapped_column(default=20.0, nullable=False)
    per_account_delay_max: Mapped[float] = mapped_column(default=60.0, nullable=False)
    max_per_account: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Progress counters (kept denormalised for cheap UI polling).
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invited_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    already_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    privacy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flood_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # FloodWait reporting: the account to wait on and until when.
    waiting_account_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    queue_job_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        Index("ix_invite_jobs_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<InviteJob name={self.name!r} status={self.status}>"


class InviteTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One audience user → one target channel, run by one account."""

    __tablename__ = "invite_tasks"

    job_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    # The audience user to invite and the account that performs it.
    user_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)

    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status"),
        default=InviteStatus.PENDING,
        index=True,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("job_id", "user_id", name="uq_invite_task_job_user"),
        Index("ix_invite_tasks_job_status", "job_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<InviteTask user={self.telegram_user_id} status={self.status}>"


__all__ = [
    "TERMINAL_INVITE_STATUSES",
    "InviteJob",
    "InviteJobStatus",
    "InviteStatus",
    "InviteTask",
]
