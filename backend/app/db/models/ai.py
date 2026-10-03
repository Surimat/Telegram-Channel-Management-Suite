"""AI metrics and diagnostics models (PHASE 7).

Storing every inference would bloat the DB pointlessly (requirement 17). Instead
we keep:

* a single-row aggregate counter table (:class:`AiMetric`) updated in place;
* a bounded ring of recent records (:class:`AiRecord`) for diagnostics, trimmed
  to ``AI_HISTORY_LIMIT``.

No original post text is stored here — only the classification *outcome* and a
short, safe error/description. The post text lives in ``posts`` under its own
retention.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Aggregate AI/classification counters (one logical row, keyed by name)."""

    __tablename__ = "ai_metrics"

    # A fixed key ("global") keeps this a single-row aggregate without magic ids.
    name: Mapped[str] = mapped_column(String(32), default="global", unique=True, nullable=False)

    rules_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_load_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AiMetric rules={self.rules_count} ai={self.ai_count} "
            f"fallback={self.fallback_count}>"
        )


class AiRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single recent classification record, for diagnostics only."""

    __tablename__ = "ai_records"

    source: Mapped[str] = mapped_column(String(16), default="", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    tone: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Short, safe, human-readable reason. Never the post text or a stack trace.
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiRecord source={self.source} category={self.category} ok={self.ok}>"


__all__ = ["AiMetric", "AiRecord"]
