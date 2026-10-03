"""Job model: durable, restart-resilient queue rows.

Every queueable operation (a scheduled reaction, an invite task, a source scan)
is a :class:`Job`. Keeping jobs in the database means the app can re-hydrate
unfinished work after a restart or crash.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_queue"

    kind: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.PENDING, index=True, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Free-form JSON payload; kept as text so no DB-specific JSON type is needed.
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Optional grouping key (e.g. an invite_job id or a post id).
    group_key: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)

    __table_args__ = (
        Index("ix_job_queue_status_scheduled", "status", "scheduled_at"),
    )

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = utcnow()
        self.attempts += 1

    def mark_done(self) -> None:
        self.status = JobStatus.DONE
        self.completed_at = utcnow()
        self.error = ""

    def mark_failed(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = utcnow()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Job kind={self.kind!r} status={self.status}>"
