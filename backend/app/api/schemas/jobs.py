"""Job queue schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.db.models.job import JobStatus


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: JobStatus
    priority: int
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    attempts: int
    max_attempts: int
    error: str
    group_key: str
    created_at: datetime
