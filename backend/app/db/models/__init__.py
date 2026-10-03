"""ORM models package.

Importing this package registers every model on ``Base.metadata``.
"""

from backend.app.db.models.event import Event, EventLevel
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.models.setting import Setting

__all__ = [
    "Event",
    "EventLevel",
    "Job",
    "JobStatus",
    "Setting",
]
