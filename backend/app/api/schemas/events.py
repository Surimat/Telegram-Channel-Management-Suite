"""Event (log/error center) schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.db.models.event import EventLevel


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    level: EventLevel
    module: str
    actor: str
    operation: str
    status: str
    message: str
    explanation: str
    how_to_fix: str
    resolved: bool
    created_at: datetime
