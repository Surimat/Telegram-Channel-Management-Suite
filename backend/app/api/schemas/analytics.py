"""Analytics API schemas (PHASE 8).

Responses are read-only aggregates plus plain-language summaries. They contain no
secrets and no per-person PII — only counts and titles (D-010/D-029).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DayPoint(BaseModel):
    date: str
    count: int


class TitledCount(BaseModel):
    key: str
    title: str
    count: int


class EmojiCount(BaseModel):
    reaction: str
    count: int


class BotCount(BaseModel):
    bot_id: str
    count: int


class SourceCount(BaseModel):
    id: str
    title: str
    username: str
    users: int


class SourceEffectiveness(BaseModel):
    id: str
    title: str
    username: str
    discovered: int
    new: int
    duplicates: int
    errors: int
    completeness: str


class ContentAnalyticsOut(BaseModel):
    days: int
    posts_total: int
    posts_window: int
    posts_previous_window: int
    change_percent: float | None = None
    average_per_day: float
    per_day: list[DayPoint]
    by_category: list[TitledCount]
    by_source: list[TitledCount]
    by_status: dict[str, int]
    summary: str


class ReactionsAnalyticsOut(BaseModel):
    days: int
    reactions_total: int
    by_status: dict[str, int]
    success_rate: float | None = None
    per_day: list[DayPoint]
    completed_per_day: list[DayPoint]
    by_emoji: list[EmojiCount]
    by_category: list[TitledCount]
    by_bot: list[BotCount]
    summary: str


class AudienceAnalyticsOut(BaseModel):
    days: int
    audience_total: int
    new_7d: int
    per_day: list[DayPoint]
    by_status: list[TitledCount]
    sources_total: int
    links_total: int
    top_sources: list[SourceCount]
    source_effectiveness: list[SourceEffectiveness]
    invites: dict[str, int]
    summary: str


class AnalyticsHeadline(BaseModel):
    posts_total: int
    posts_window: int
    posts_change_percent: float | None = None
    reactions_total: int
    reaction_success_rate: float | None = None
    audience_total: int
    audience_new_7d: int
    sources_total: int


class AnalyticsOverviewOut(BaseModel):
    days: int
    channel_id: str = ""
    generated_at: datetime
    account_connected: bool = True
    account_note: str = ""
    headline: AnalyticsHeadline
    content: ContentAnalyticsOut
    reactions: ReactionsAnalyticsOut
    audience: AudienceAnalyticsOut
    summary: list[str] = Field(default_factory=list)


__all__ = [
    "AnalyticsHeadline",
    "AnalyticsOverviewOut",
    "AudienceAnalyticsOut",
    "BotCount",
    "ContentAnalyticsOut",
    "DayPoint",
    "EmojiCount",
    "ReactionsAnalyticsOut",
    "SourceCount",
    "SourceEffectiveness",
    "TitledCount",
]
