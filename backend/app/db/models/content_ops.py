"""Content Operations 2.0 models (v1.9).

Additive models that extend the existing Content Studio without a second studio:

* :class:`AiProfile` — a reusable, named AI processing profile (instructions,
  language, tone, max length, provider policy). Prompts live here as data, never
  hardcoded in business logic.
* :class:`AutomationRule` — a declarative ``SOURCE + CONDITION → ACTION`` rule.
  Deliberately not a scripting engine: conditions match on fields, actions are a
  fixed allow-list of pipeline steps.
* :class:`ContentOperation` — an append-only analytics/audit record for one
  pipeline stage (gather/ai/moderation/schedule/publish/comment/delete). It
  stores metadata only — never text, keys or credentials.

Nothing here stores secrets or session data.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reusable AI processing profile (pipeline requirement 12)."""

    __tablename__ = "ai_profiles"

    #: Stable key (e.g. ``news``), unique so a profile is addressable by name.
    key: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    tone: Mapped[str] = mapped_column(String(32), default="neutral", nullable=False)
    max_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: System instructions the pipeline sends to the AI (never secret).
    system_instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Provider policy: a routing strategy id (``auto``, ``free_first``, ...).
    provider_policy: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    #: Pipeline actions this profile applies (JSON list of action ids).
    actions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Built-in profiles are seeded and marked so the UI can distinguish them.
    builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiProfile key={self.key!r}>"


class AutomationRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A declarative ``SOURCE + CONDITION → ACTION`` rule (requirement 14)."""

    __tablename__ = "automation_rules"

    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Source kind the rule applies to (``""`` = any).
    source_kind: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    #: JSON condition object: {"contains": [...], "min_length": n, "language": "ru"}.
    condition: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    #: JSON list of action ids from the fixed allow-list (``ACTIONS``).
    actions: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    #: Applied profile key (optional).
    profile_key: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AutomationRule name={self.name!r} src={self.source_kind!r}>"


class ContentOperation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One pipeline stage event for analytics/audit (requirement 11)."""

    __tablename__ = "content_operations"

    item_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    publication_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    #: Pipeline stage: gather|clean|dedup|ai|moderation|schedule|publish|comment|delete.
    stage: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    #: AI metadata (never prompt text or a key).
    provider: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: A short, secret-free explanation.
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ContentOperation stage={self.stage!r} status={self.status!r}>"


#: Pipeline stages, in order. Used by the consistency auditor and analytics.
STAGES = (
    "gather",
    "clean",
    "dedup",
    "ai",
    "moderation",
    "schedule",
    "publish",
    "comment",
    "delete",
)

#: AI processing outcomes on an item.
AI_STATUS_NONE = "none"
AI_STATUS_OK = "ok"
AI_STATUS_UNAVAILABLE = "ai_unavailable"
AI_STATUS_ERROR = "error"

__all__ = [
    "AI_STATUS_ERROR",
    "AI_STATUS_NONE",
    "AI_STATUS_OK",
    "AI_STATUS_UNAVAILABLE",
    "STAGES",
    "AiProfile",
    "AutomationRule",
    "ContentOperation",
]
