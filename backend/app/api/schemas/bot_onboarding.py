"""Bot onboarding API schemas (v2.0).

No field here is a secret. A bot token is never part of any request or response —
only the bot's public username and Telegram's own deep link are exposed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RightsProfileOut(BaseModel):
    key: str
    title_ru: str
    title_en: str
    function: str
    admin_rights: list[str]
    description_ru: str
    description_en: str


class OnboardingCreateIn(BaseModel):
    bot_ids: list[str] = Field(default_factory=list)
    channel_id: str
    rights_profile: str = "reactions"


class OnboardingCandidateOut(BaseModel):
    id: str
    batch_id: str
    index: int
    bot_id: str
    bot_username: str
    bot_title: str
    channel_id: str
    rights_profile: str
    function: str
    deep_link: str
    status: str
    status_label: str
    attempts: int
    binding_id: str
    last_error: str


class OnboardingBatchOut(BaseModel):
    id: str
    channel_id: str
    channel_label: str
    rights_profile: str
    rights_profile_title: str
    function: str
    requested_count: int
    ready_count: int
    permission_count: int
    failed_count: int
    skipped_count: int
    queue_paused: bool
    completed: bool
    last_error: str


class OnboardingBatchDetailOut(BaseModel):
    batch: OnboardingBatchOut
    candidates: list[OnboardingCandidateOut]


class OnboardingBatchListOut(BaseModel):
    items: list[OnboardingBatchOut]
    total: int


class OnboardingProgressOut(BaseModel):
    total: int
    queued: int
    waiting: int
    verifying: int
    ready: int
    needs_permission: int
    failed: int
    skipped: int
    paused: bool
    active: int
    done: int


class OnboardingDashboardOut(BaseModel):
    batch_id: str
    channel_id: str
    channel_label: str
    rights_profile: str
    rights_profile_title: str
    function: str
    queue_paused: bool
    completed: bool
    progress: OnboardingProgressOut


class OnboardingActionResultOut(BaseModel):
    candidate_id: str
    bot_id: str
    bot_username: str
    status: str
    status_label: str
    binding_id: str = ""
    deep_link: str = ""
    error: str = ""


__all__ = [
    "OnboardingActionResultOut",
    "OnboardingBatchDetailOut",
    "OnboardingBatchListOut",
    "OnboardingBatchOut",
    "OnboardingCandidateOut",
    "OnboardingCreateIn",
    "OnboardingDashboardOut",
    "OnboardingProgressOut",
    "RightsProfileOut",
]
