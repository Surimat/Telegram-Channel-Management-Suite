"""Bot Factory API schemas (v1.3: bulk managed-bot preparation).

No field here is a secret. Tokens are never part of any response (they are sealed
at rest and only ``has_token`` is exposed elsewhere).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BatchCreateIn(BaseModel):
    title: str = ""
    prefix: str
    topic: str = ""
    style: str = "neutral"
    count: int = Field(default=0, ge=0, le=50)
    name_template: str = ""
    username_template: str = ""
    manager_bot_id: str = ""
    account_id: str = ""
    channel_id: str = ""


class BatchOut(BaseModel):
    id: str
    title: str
    prefix: str
    topic: str
    style: str
    requested_count: int
    created_count: int
    failed_count: int
    skipped_count: int
    status: str
    status_label: str
    manager_username: str
    channel_id: str
    queue_cancelled: bool
    limit_note: str


class CandidateOut(BaseModel):
    id: str
    batch_id: str
    index: int
    suggested_name: str
    suggested_username: str
    username_status: str
    username_message: str
    creation_status: str
    creation_status_label: str
    queue_state: str
    queue_state_label: str
    attempts: int
    bot_id: str
    telegram_id: int | None = None
    token_mask: str
    deep_link: str
    error: str


class BatchDetailOut(BaseModel):
    batch: BatchOut
    candidates: list[CandidateOut]


class BatchListOut(BaseModel):
    items: list[BatchOut]
    total: int


class QueueProgressOut(BaseModel):
    total: int
    pending: int
    queued: int
    running: int
    success: int
    failed: int
    skipped: int
    cancelled: int


class DashboardOut(BaseModel):
    batch_id: str
    title: str
    status: str
    status_label: str
    requested_count: int
    created_count: int
    failed_count: int
    skipped_count: int
    queue_cancelled: bool
    counts: dict[str, int]
    queue: QueueProgressOut
    manager_username: str
    channel_id: str
    limit_note: str


class TemplateOut(BaseModel):
    key: str
    name_template: str
    username_template: str


class BindIn(BaseModel):
    channel_id: str
    function: str = "reactions"


class BindResultOut(BaseModel):
    candidate_id: str
    bot_id: str
    username: str
    binding_id: str
    status: str
    status_label: str


class AdoptIn(BaseModel):
    username: str
    telegram_id: int
    title: str = ""


class TokenRegisterOut(BaseModel):
    imported: int
    pending: int


__all__ = [
    "AdoptIn",
    "BatchCreateIn",
    "BatchDetailOut",
    "BatchListOut",
    "BatchOut",
    "BindIn",
    "BindResultOut",
    "CandidateOut",
    "DashboardOut",
    "QueueProgressOut",
    "TemplateOut",
    "TokenRegisterOut",
]
