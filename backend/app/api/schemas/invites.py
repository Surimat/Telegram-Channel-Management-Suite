"""Invite API schemas (PHASE 6).

Responses expose only non-secret, display-safe fields — never session contents,
api_hash, tokens or raw phone numbers. The preview response mirrors the mandatory
confirmation summary shown before any bulk operation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InviteFiltersIn(BaseModel):
    search: str = ""
    source_ids: list[str] = Field(default_factory=list)
    tag: str | None = None
    status: str | None = None
    is_bot: bool | None = None
    is_deleted: bool | None = None
    has_username: bool | None = None
    is_premium: bool | None = None
    telegram_user_id: int | None = None


class InvitePreviewIn(BaseModel):
    target: str = ""
    channel_id: str = ""
    account_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    max_total: int = 0
    sample_limit: int = 10


class InvitePreviewSample(BaseModel):
    id: str
    telegram_user_id: int
    username: str = ""
    display_name: str = ""


class InvitePreviewOut(BaseModel):
    target: str
    source_ids: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)
    account_labels: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    total_candidates: int = 0
    planned_operations: int = 0
    accounts_count: int = 0
    max_total: int = 0
    sample: list[InvitePreviewSample] = Field(default_factory=list)
    explanation: str = ""
    requires_confirmation: bool = True


class InviteJobCreateIn(BaseModel):
    name: str = ""
    target: str = ""
    channel_id: str = ""
    account_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    per_account_delay_min: float | None = None
    per_account_delay_max: float | None = None
    max_per_account: int | None = None
    max_total: int | None = None


class InviteJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str = ""
    target: str = ""
    target_title: str = ""
    channel_id: str = ""
    status: str
    dry_run: bool = False
    confirmed_at: datetime | None = None
    account_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    total_tasks: int = 0
    processed_count: int = 0
    invited_count: int = 0
    already_count: int = 0
    privacy_count: int = 0
    flood_count: int = 0
    error_count: int = 0
    waiting_account_id: str = ""
    wait_until: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str = ""
    explanation: str = ""
    created_at: datetime
    updated_at: datetime


class InviteJobListOut(BaseModel):
    items: list[InviteJobOut]
    total: int
    limit: int
    offset: int


class InviteTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    user_id: str
    telegram_user_id: int
    account_id: str = ""
    status: str
    attempts: int = 0
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    wait_until: datetime | None = None
    error: str = ""


class InviteTaskListOut(BaseModel):
    items: list[InviteTaskOut]
    total: int
    limit: int
    offset: int
    status_counts: dict[str, int] = Field(default_factory=dict)


class InviteSummaryOut(BaseModel):
    by_status: dict[str, int] = Field(default_factory=dict)
