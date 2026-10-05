"""Donor discovery API schemas (v1.1: automated donor search).

Candidates are proposals. Adding one to audience sources is a separate, explicit
action. No field here is a secret; metrics that Telegram hid stay at zero and the
``partial``/``confidence`` fields say so.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiscoverQueryIn(BaseModel):
    topic: str = ""
    keywords: list[str] = Field(default_factory=list)
    language: str = ""
    min_subscribers: int = 0
    max_subscribers: int = 0
    active_only: bool = False
    period_days: int = 0
    providers: list[str] = Field(default_factory=lambda: ["telegram"])
    account_id: str = ""
    #: Optional channel already in the registry; Telegram returns similar
    #: channels for it (official recommendations). Works even with no keywords.
    seed_channel: str = ""


class DiscoveryProviderStatus(BaseModel):
    name: str
    title: str
    available: bool
    message: str


class DiscoveryProviderReport(BaseModel):
    provider: str
    title: str
    ok: bool
    message: str
    how_to_fix: str = ""
    found: int = 0


class DonorCandidateOut(BaseModel):
    id: str
    query: str
    provider: str
    provider_title: str
    username: str
    title: str
    telegram_id: int | None = None
    kind: str
    subscribers: int
    avg_views: float
    activity: float
    language: str
    fit: str
    fit_title: str
    fit_score: float
    confidence: str
    signals: list[str]
    explanations: list[str]
    summary: str
    added: bool
    added_source_id: str
    #: Derived comparison metrics (0 when the underlying data is unavailable).
    reach_ratio: float = 0.0
    reaction_ratio: float = 0.0
    #: Human-readable fit score (e.g. "62/100").
    score_label: str = ""


class DiscoveryResultOut(BaseModel):
    query: str
    stored: int
    providers: list[DiscoveryProviderReport]
    candidates: list[DonorCandidateOut]


class CandidateListOut(BaseModel):
    items: list[DonorCandidateOut]
    providers: list[DiscoveryProviderStatus]


class CompareIn(BaseModel):
    candidate_ids: list[str]


class CompareOut(BaseModel):
    items: list[DonorCandidateOut]
    best_id: str
    best_title: str
    best_reason: str


class AddToSourcesOut(BaseModel):
    candidate: DonorCandidateOut
    source_id: str


__all__ = [
    "AddToSourcesOut",
    "CandidateListOut",
    "CompareIn",
    "CompareOut",
    "DiscoverQueryIn",
    "DiscoveryProviderReport",
    "DiscoveryProviderStatus",
    "DiscoveryResultOut",
    "DonorCandidateOut",
]
