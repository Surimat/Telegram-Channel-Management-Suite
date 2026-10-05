"""Discovered donor candidate model (v1.1: automated donor discovery).

A :class:`DonorCandidate` is a channel/group the discovery providers *suggested*
as a possible donor source. It is a **proposal**, never an automatic addition: the
owner reviews candidates and explicitly adds the ones they want to
``audience_sources``. Candidates carry only what the provider actually observed
(public metadata), plus an explainable suitability band.

Nothing here is invented: fields the provider could not observe stay zero/empty,
and the suitability band carries a confidence and a list of signals.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Suitability bands (shown verbatim in the UI).
FIT_SUITABLE = "suitable"     # looks like a good donor
FIT_CHECK = "check"           # worth checking
FIT_DOUBTFUL = "doubtful"     # suspicious / poor fit
FIT_UNKNOWN = "unknown"       # not enough data

FIT_TITLES = {
    FIT_SUITABLE: "Подходит",
    FIT_CHECK: "Стоит проверить",
    FIT_DOUBTFUL: "Сомнительно",
    FIT_UNKNOWN: "Мало данных",
}

#: Where a candidate came from (transparency for the owner).
SOURCE_TELEGRAM = "telegram"
SOURCE_WEB = "web"
SOURCE_MANUAL = "manual"

SOURCE_TITLES = {
    SOURCE_TELEGRAM: "Поиск Telegram",
    SOURCE_WEB: "Веб-поиск",
    SOURCE_MANUAL: "Введено вручную",
}


class DonorCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "donor_candidates"

    #: Query that produced this candidate (so results can be grouped/cleared).
    query: Mapped[str] = mapped_column(String(255), default="", index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default=SOURCE_TELEGRAM, nullable=False)

    username: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="channel", nullable=False)

    # --- Observed public metrics (0 when not exposed) ---
    subscribers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_views: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    activity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="", nullable=False)

    # --- Explainable assessment ---
    fit: Mapped[str] = mapped_column(String(16), default=FIT_UNKNOWN, nullable=False)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    signals: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    explanations: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)

    #: True once the owner added it to the audience sources.
    added: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_source_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DonorCandidate {self.username or self.telegram_id} fit={self.fit}>"


__all__ = [
    "FIT_CHECK",
    "FIT_DOUBTFUL",
    "FIT_SUITABLE",
    "FIT_TITLES",
    "FIT_UNKNOWN",
    "SOURCE_MANUAL",
    "SOURCE_TELEGRAM",
    "SOURCE_TITLES",
    "SOURCE_WEB",
    "DonorCandidate",
]
