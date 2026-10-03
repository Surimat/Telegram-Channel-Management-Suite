"""ORM models package.

Importing this package registers every model on ``Base.metadata``.
"""

from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.models.event import Event, EventLevel
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.models.post import Post, PostStatus
from backend.app.db.models.reaction import (
    DelayPresetDB,
    ReactionJob,
    ReactionJobStatus,
    ReactionProfile,
    ReactionRule,
)
from backend.app.db.models.setting import Setting

__all__ = [
    "Bot",
    "BotHealth",
    "BotKind",
    "DelayPresetDB",
    "Event",
    "EventLevel",
    "Job",
    "JobStatus",
    "Post",
    "PostStatus",
    "ReactionJob",
    "ReactionJobStatus",
    "ReactionProfile",
    "ReactionRule",
    "Setting",
]
