"""Donor channel analytics model (product slice: source quality).

For every audience source that acts as a *donor* (a place we look for an
audience), we compute observable metrics and a conservative, explainable quality
score. This is an **analytical indicator, not proof**: the model never claims an
exact number of bots. Instead it reports the probability band of artificial
activity and lists the observed signals behind it, with a confidence level.

If participant-level data is not available (no session, hidden member list), the
"share of bots" cannot be computed and the model says so explicitly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Quality bands (shown verbatim in the UI).
QUALITY_UNKNOWN = "unknown"
QUALITY_GOOD = "good"
QUALITY_AVERAGE = "average"
QUALITY_SUSPECT = "suspect"

QUALITY_TITLES = {
    QUALITY_UNKNOWN: "Недостаточно данных",
    QUALITY_GOOD: "Хорошее качество",
    QUALITY_AVERAGE: "Среднее качество",
    QUALITY_SUSPECT: "Признаки искусственной активности",
}

#: Confidence of the assessment.
CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

#: Probability band of artificial activity (never an exact count).
PROBABILITY_LOW = "low"
PROBABILITY_MEDIUM = "medium"
PROBABILITY_HIGH = "high"

PROBABILITY_TITLES = {
    PROBABILITY_LOW: "Низкая вероятность",
    PROBABILITY_MEDIUM: "Средняя вероятность",
    PROBABILITY_HIGH: "Высокая вероятность",
}


class DonorMetrics(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Last-known observable metrics + heuristic quality for one donor source."""

    __tablename__ = "donor_metrics"

    channel_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(
        String(32), default="", index=True, unique=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # --- Observable metrics (0/None when Telegram does not expose them) ---
    subscribers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    posts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    posts_per_week: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_views: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Views divided by subscribers — a classic "reach" ratio.
    view_subscriber_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Reactions divided by views.
    reaction_view_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_comments: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    days_since_last_post: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    growth_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Assessment ---
    quality: Mapped[str] = mapped_column(String(16), default=QUALITY_UNKNOWN, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bot_probability: Mapped[str] = mapped_column(
        String(16), default=PROBABILITY_LOW, nullable=False
    )
    confidence: Mapped[str] = mapped_column(String(16), default=CONFIDENCE_LOW, nullable=False)
    # True when participant-level data exists to estimate the bot share.
    participant_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Estimated share of bots in the sample (0..1) when participant data exists.
    bot_share_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # JSON list of observed signal keys (see donor_heuristics.SIGNALS).
    signals: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # JSON list of plain-language explanations for those signals.
    explanations: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)

    source_completeness: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    last_analyzed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DonorMetrics source={self.source_id} quality={self.quality}>"


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "PROBABILITY_HIGH",
    "PROBABILITY_LOW",
    "PROBABILITY_MEDIUM",
    "PROBABILITY_TITLES",
    "QUALITY_AVERAGE",
    "QUALITY_GOOD",
    "QUALITY_SUSPECT",
    "QUALITY_TITLES",
    "QUALITY_UNKNOWN",
    "DonorMetrics",
]
