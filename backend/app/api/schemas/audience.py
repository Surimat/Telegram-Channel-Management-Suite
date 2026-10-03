"""Audience API schemas (PHASE 5).

Responses expose only non-secret, display-safe fields. Phone numbers appear only
as an optional masked form. Every "scan" response explains Telegram's
completeness so the UI can be honest about partial results (decision D-026).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Sources -----------------------------------------------------------------
class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str = ""
    username: str = ""
    telegram_id: int | None = None
    source_type: str
    reference: str = ""
    enabled: bool
    account_id: str | None = None
    scan_status: str
    completeness: str
    last_scan_at: datetime | None = None
    last_scan_finished_at: datetime | None = None
    discovered_count: int = 0
    imported_count: int = 0
    new_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    reported_total: int | None = None
    scanned_offset: int = 0
    scan_job_id: str = ""
    last_error: str = ""
    created_at: datetime
    updated_at: datetime


class SourceCreateIn(BaseModel):
    reference: str = Field(description="Username (@name), ссылка t.me/... или Telegram ID")
    title: str = ""
    source_type: str = "unknown"
    account_id: str | None = None


class SourceUpdateIn(BaseModel):
    title: str | None = None
    enabled: bool | None = None
    account_id: str | None = None
    source_type: str | None = None


class SourceCheckOut(BaseModel):
    ok: bool
    title: str = ""
    username: str = ""
    telegram_id: int | None = None
    kind: str = ""
    participants_count: int | None = None
    participants_hidden: bool = False
    message: str = ""
    how_to_fix: str = ""
    completeness: str = "unknown"


class ScanPreviewOut(BaseModel):
    source_id: str
    title: str = ""
    username: str = ""
    source_type: str
    reference: str = ""
    account_id: str = ""
    account_label: str = ""
    mode: str = ""
    batch_size: int = 100
    chunk_size: int = 500
    estimated_total: int | None = None
    filters: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ScanResultOut(BaseModel):
    source_id: str
    scan_status: str
    completeness: str
    discovered: int = 0
    new: int = 0
    duplicates: int = 0
    errors: int = 0
    reported_total: int | None = None
    offset: int = 0
    explanation: str = ""
    completed: bool = False


# --- Users -------------------------------------------------------------------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    telegram_user_id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    phone_masked: str = ""
    is_bot: bool = False
    is_deleted: bool = False
    is_premium: bool | None = None
    status: str
    score: float = 0.0
    score_reason: str = ""
    tags: list[str] = Field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    # Invite Manager extension point (PHASE 6), neutral fields.
    invite_status: str = ""
    invite_attempts: int = 0
    last_invite_at: datetime | None = None
    last_invite_error: str = ""


class UserDetailOut(UserOut):
    sources: list[str] = Field(default_factory=list)
    score_components: list[dict] = Field(default_factory=list)


class UserListOut(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int


class SourceListOut(BaseModel):
    items: list[SourceOut]
    total: int
    limit: int
    offset: int


# --- Tags --------------------------------------------------------------------
class TagOut(BaseModel):
    name: str
    count: int


class TagsBulkIn(BaseModel):
    user_ids: list[str]
    tags: list[str]


class StatusBulkIn(BaseModel):
    user_ids: list[str]
    status: str


class TagRenameIn(BaseModel):
    old: str
    new: str


class FilterPresetOut(BaseModel):
    key: str
    label: str
    description: str
    filters: dict


# --- Export / import ---------------------------------------------------------
class ExportIn(BaseModel):
    format: str = "csv"
    source_id: str | None = None
    tag: str | None = None
    include_pii: bool = False
    limit: int = 0


class ExportPreviewOut(BaseModel):
    count: int
    fields: list[str]
    includes_pii: bool
    destination: str
    note: str = ""


class ExportOut(BaseModel):
    filename: str
    path: str
    format: str
    fields: list[str]
    includes_pii: bool
    row_count: int
    size_bytes: int


class ImportIn(BaseModel):
    data: str
    format: str = "csv"
    source_id: str | None = None


class ImportOut(BaseModel):
    created: int
    merged: int
    invalid: int


# --- Dashboard ---------------------------------------------------------------
class AudienceDashboardOut(BaseModel):
    sources_total: int
    unique_users: int
    total_records: int
    new_users_7d: int
    scans_total: int
    partial_sources: int
    errors_total: int
    bots: int
    by_scan_status: dict[str, int] = Field(default_factory=dict)
    by_completeness: dict[str, int] = Field(default_factory=dict)
    source_overlap: list[dict] = Field(default_factory=list)
    discovered_per_day: list[dict] = Field(default_factory=list)
