"""Donor quality heuristics (pure, explainable, conservative).

Computes an **analytical indicator** of a donor channel's quality from
observable signals. It deliberately never states an exact number of bots: it
returns a probability band, a confidence level, and the list of observed signals
with plain-language explanations.

All thresholds are named constants so they can be reviewed and tuned; nothing is
hidden. If participant-level data is unavailable (no session, hidden member
list), the bot-share signal is simply not used and confidence stays low.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.db.models.donor import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    PROBABILITY_HIGH,
    PROBABILITY_LOW,
    PROBABILITY_MEDIUM,
    QUALITY_AVERAGE,
    QUALITY_GOOD,
    QUALITY_SUSPECT,
    QUALITY_UNKNOWN,
)

# --- Named thresholds (reviewable, not magic) --------------------------------
#: view/subscriber ratio below which reach looks artificially low.
LOW_REACH_RATIO = 0.05
#: reaction/view ratio below which engagement looks hollow.
LOW_ENGAGEMENT_RATIO = 0.005
#: days without a post after which a channel looks abandoned.
STALE_DAYS = 30
#: participant bot share at/above which artificial activity is likely.
BOT_SHARE_HIGH = 0.30
#: participant bot share at/above which it is probable.
BOT_SHARE_MEDIUM = 0.15
#: growth spike (percent) that looks inorganic on a small channel.
GROWTH_SPIKE_PERCENT = 100.0

#: Signal keys with their human explanation (one source of truth for the UI).
SIGNALS: dict[str, str] = {
    "low_reach": "Просмотров мало относительно числа подписчиков.",
    "high_subscriber_low_views": "Много подписчиков, но очень мало просмотров.",
    "low_engagement": "Очень мало реакций на просмотры.",
    "no_comments": "Почти нет комментариев.",
    "stale": "Канал давно не публикует посты.",
    "high_bot_share": "В выборке участников высокая доля ботов.",
    "medium_bot_share": "В выборке участников заметная доля ботов.",
    "growth_spike": "Резкий рост подписчиков выглядит неестественно.",
}


@dataclass(slots=True)
class DonorInput:
    """Observable inputs for one donor source (0/None when not exposed)."""

    subscribers: int = 0
    posts_count: int = 0
    posts_per_week: float = 0.0
    avg_views: float = 0.0
    avg_comments: float = 0.0
    reaction_view_ratio: float = 0.0
    days_since_last_post: int = 0
    growth_percent: float | None = None
    # Participant sample (when available): how many users, how many were bots.
    sample_size: int = 0
    sample_bots: int = 0
    participant_data: bool = False
    completeness: str = "unknown"


@dataclass(slots=True)
class DonorAssessment:
    quality: str
    quality_score: float
    bot_probability: str
    confidence: str
    participant_data: bool
    bot_share_estimate: float | None
    signals: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    summary: str = ""


def assess_donor(data: DonorInput) -> DonorAssessment:
    """Return a conservative quality assessment for a donor channel."""
    signals: list[str] = []

    subscribers = max(int(data.subscribers), 0)
    view_ratio = 0.0
    if subscribers > 0:
        view_ratio = max(data.avg_views, 0.0) / subscribers
    elif data.avg_views > 0:
        # No subscriber count: cannot compute reach, do not claim anything.
        view_ratio = 0.0

    if subscribers > 0 and data.avg_views > 0:
        if view_ratio < LOW_REACH_RATIO:
            signals.append("low_reach")
        if subscribers >= 1000 and view_ratio < LOW_REACH_RATIO / 2:
            signals.append("high_subscriber_low_views")
    if data.avg_views > 0 and data.reaction_view_ratio < LOW_ENGAGEMENT_RATIO:
        signals.append("low_engagement")
    if data.avg_views > 0 and data.avg_comments <= 0:
        signals.append("no_comments")
    if data.days_since_last_post >= STALE_DAYS and data.posts_count > 0:
        signals.append("stale")
    if data.growth_percent is not None and data.growth_percent >= GROWTH_SPIKE_PERCENT:
        signals.append("growth_spike")

    bot_share: float | None = None
    if data.participant_data and data.sample_size > 0:
        bot_share = data.sample_bots / data.sample_size
        if bot_share >= BOT_SHARE_HIGH:
            signals.append("high_bot_share")
        elif bot_share >= BOT_SHARE_MEDIUM:
            signals.append("medium_bot_share")

    score = _score(signals)
    quality = _quality(signals, score, has_data=_has_any_data(data))
    probability = _probability(signals, bot_share)
    confidence = _confidence(data, bot_share)
    explanations = [SIGNALS[s] for s in signals if s in SIGNALS]

    return DonorAssessment(
        quality=quality,
        quality_score=round(score, 1),
        bot_probability=probability,
        confidence=confidence,
        participant_data=data.participant_data,
        bot_share_estimate=round(bot_share, 4) if bot_share is not None else None,
        signals=signals,
        explanations=explanations,
        summary=_summary(quality, probability, signals, bot_share),
    )


def _score(signals: list[str]) -> float:
    """Start at 100 and subtract a fixed penalty per observed signal."""
    penalties = {
        "low_reach": 20.0,
        "high_subscriber_low_views": 15.0,
        "low_engagement": 15.0,
        "no_comments": 5.0,
        "stale": 10.0,
        "growth_spike": 10.0,
        "high_bot_share": 30.0,
        "medium_bot_share": 15.0,
    }
    score = 100.0
    for signal in signals:
        score -= penalties.get(signal, 0.0)
    return max(score, 0.0)


def _quality(signals: list[str], score: float, *, has_data: bool) -> str:
    if not has_data:
        return QUALITY_UNKNOWN
    if "high_bot_share" in signals or score < 40:
        return QUALITY_SUSPECT
    if score >= 80:
        return QUALITY_GOOD
    return QUALITY_AVERAGE


def _probability(signals: list[str], bot_share: float | None) -> str:
    if bot_share is not None and bot_share >= BOT_SHARE_HIGH:
        return PROBABILITY_HIGH
    strong = {"high_subscriber_low_views", "low_reach", "stale"}
    if len(strong & set(signals)) >= 2 or (
        bot_share is not None and bot_share >= BOT_SHARE_MEDIUM
    ):
        return PROBABILITY_MEDIUM
    if "high_bot_share" in signals:
        return PROBABILITY_HIGH
    return PROBABILITY_LOW


def _confidence(data: DonorInput, bot_share: float | None) -> str:
    if bot_share is not None and data.sample_size >= 200:
        return CONFIDENCE_HIGH
    if bot_share is not None and data.sample_size >= 50:
        return CONFIDENCE_MEDIUM
    if _has_any_data(data):
        return CONFIDENCE_MEDIUM if data.completeness == "complete" else CONFIDENCE_LOW
    return CONFIDENCE_LOW


def _has_any_data(data: DonorInput) -> bool:
    return any(
        [
            data.subscribers > 0,
            data.posts_count > 0,
            data.avg_views > 0,
            data.sample_size > 0,
        ]
    )


def _summary(
    quality: str, probability: str, signals: list[str], bot_share: float | None
) -> str:
    if quality == QUALITY_UNKNOWN:
        return (
            "Недостаточно данных для оценки. Просканируйте источник или подключите аккаунт, "
            "чтобы увидеть метрики."
        )
    parts: list[str] = []
    if quality == QUALITY_GOOD:
        parts.append("Источник выглядит здоровым.")
    elif quality == QUALITY_AVERAGE:
        parts.append("Источник среднего качества: есть отдельные тревожные признаки.")
    else:
        parts.append("У источника заметны признаки искусственной активности.")
    if bot_share is not None:
        percent = round(bot_share * 100)
        parts.append(f"В выборке примерно {percent}% ботов.")
    if signals:
        parts.append(f"Сигналов: {len(signals)}.")
    return " ".join(parts)


__all__ = [
    "SIGNALS",
    "DonorAssessment",
    "DonorInput",
    "assess_donor",
]
