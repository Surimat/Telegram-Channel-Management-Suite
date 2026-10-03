"""ORM models package.

Importing this package registers every model on ``Base.metadata``.
"""

from backend.app.db.models.audience import (
    AudienceSource,
    AudienceUser,
    Completeness,
    MemberStatus,
    ScanStatus,
    SourceType,
    SourceUserLink,
)
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
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.models.setting import Setting

__all__ = [
    "AudienceSource",
    "AudienceUser",
    "Bot",
    "BotHealth",
    "BotKind",
    "Completeness",
    "DelayPresetDB",
    "Event",
    "EventLevel",
    "Job",
    "JobStatus",
    "MemberStatus",
    "Post",
    "PostStatus",
    "ReactionJob",
    "ReactionJobStatus",
    "ReactionProfile",
    "ReactionRule",
    "ScanStatus",
    "SessionStatus",
    "Setting",
    "SourceType",
    "SourceUserLink",
    "UserSession",
]
