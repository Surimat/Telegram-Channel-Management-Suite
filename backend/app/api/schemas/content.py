"""Content Studio API schemas (v1.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContentSourceOut(BaseModel):
    id: str
    kind: str
    kind_title: str
    title: str
    reference: str
    enabled: bool
    channel_id: str
    status: str
    status_title: str
    last_error: str
    last_fetch: str = ""
    last_fetch_new: int = 0
    etag: str = ""
    last_modified: str = ""
    last_seen_item: str = ""
    blocked_keywords: list[str] = Field(default_factory=list)
    quiet_hours_enabled: bool = False
    quiet_hours_start: int = 23
    quiet_hours_end: int = 8
    quiet_hours_tz: str = "UTC"


class ContentSourceListOut(BaseModel):
    items: list[ContentSourceOut]
    providers: list[dict[str, object]]


class ContentSourceIn(BaseModel):
    kind: str = "manual"
    reference: str
    title: str = ""
    enabled: bool = True
    channel_id: str = ""
    account_id: str = ""


class GrabOut(BaseModel):
    source_id: str
    ok: bool
    new_items: int
    duplicates: int
    protected: bool
    message: str
    how_to_fix: str = ""
    item_ids: list[str] = Field(default_factory=list)
    blocked: int = 0
    held: int = 0


class ContentItemOut(BaseModel):
    id: str
    title: str
    text: str
    cleaned_text: str
    entities: list[dict[str, object]]
    buttons: list[dict[str, object]]
    status: str
    status_title: str
    mode: str
    source_id: str
    source_message_id: int | None
    source_url: str
    source_channel: str
    source_author: str
    imported_at: str = ""
    rights_status: str
    rights_title: str
    attribution_enabled: bool
    protected: bool
    content_hash: str
    language: str
    note: str
    scheduled_at: str = ""
    rights_warning: str = ""
    held: bool = False
    moderation_note: str = ""
    original_text: str = ""
    ai_status: str = "none"
    ai_category: str = ""
    ai_intent: str = ""
    ai_profile: str = ""
    ai_note: str = ""
    created_at: str
    updated_at: str


class ContentItemListOut(BaseModel):
    items: list[ContentItemOut]
    total: int
    limit: int
    offset: int


class ContentItemUpdateIn(BaseModel):
    title: str | None = None
    text: str | None = None
    note: str | None = None
    status: str | None = None
    rights_status: str | None = None
    attribution_enabled: bool | None = None
    mode: str | None = None
    scheduled_at: str | None = None


class CleanPreviewOut(BaseModel):
    original: str
    cleaned: str
    changed: bool
    changes: list[dict[str, object]]
    removed_lines: int


class ApplyCleanIn(BaseModel):
    cleaned: str | None = None


class RewriteIn(BaseModel):
    mode: str = "rephrase"


class RewriteOut(BaseModel):
    ok: bool
    text: str
    mode: str
    mode_title: str
    message: str
    how_to_fix: str
    used_model: str = ""


class RightsOut(BaseModel):
    rights_status: str
    rights_title: str
    attribution_block: str
    warning: str


class ContentDashboardOut(BaseModel):
    drafts: int
    imported: int
    ready: int
    scheduled: int
    published_today: int
    failed: int
    status_counts: dict[str, int]
    publication_counts: dict[str, int]


# --- posting / calendar / buttons / preview (v1.2) -------------------------


class ButtonIn(BaseModel):
    text: str
    action: str = "url"
    value: str = ""


class ButtonSetIn(BaseModel):
    rows: list[list[ButtonIn]] = Field(default_factory=list)


class ButtonSetOut(BaseModel):
    item_id: str
    rows: list[list[ButtonIn]]
    enabled: bool


class TargetIn(BaseModel):
    channel_id: str
    scheduled_at: str | None = None
    text_override: str = ""
    profile_key: str = ""
    ai_instructions: str = ""


class PlanIn(BaseModel):
    targets: list[TargetIn] = Field(default_factory=list)
    mode: str | None = None


class PublicationOut(BaseModel):
    id: str
    item_id: str
    channel_id: str
    channel_username: str
    status: str
    status_title: str
    scheduled_at: str = ""
    published_at: str = ""
    delete_at: str = ""
    telegram_message_ids: list[int] = Field(default_factory=list)
    error: str = ""
    attempts: int = 0
    mode: str = ""
    profile_key: str = ""
    comment_status: str = ""
    delete_status: str = ""


class PlanOut(BaseModel):
    publications: list[PublicationOut]


class ScheduleIn(BaseModel):
    scheduled_at: str | None = None


class PublishOut(BaseModel):
    publication_id: str
    ok: bool
    status: str
    message_ids: list[int] = Field(default_factory=list)
    message: str = ""
    how_to_fix: str = ""
    uncertain: bool = False


class CalendarEntryOut(BaseModel):
    publication_id: str
    item_id: str
    title: str
    channel_id: str
    channel_title: str
    status: str
    status_title: str
    scheduled_at: str = ""
    published_at: str = ""
    delete_at: str = ""


class CalendarChannelOut(BaseModel):
    channel_id: str
    title: str
    reference: str


class CalendarOut(BaseModel):
    start: str
    end: str
    channels: list[CalendarChannelOut]
    entries: list[CalendarEntryOut]


class ValidationIssueOut(BaseModel):
    kind: str
    message: str
    line: int = 0


class ValidationOut(BaseModel):
    ok: bool
    issues: list[ValidationIssueOut]
    button_problems: list[str]
    first_error: str = ""
    fixed_text: str = ""


class PreviewButtonOut(BaseModel):
    text: str
    action: str
    url: str = ""


class PreviewMediaOut(BaseModel):
    kind: str
    filename: str
    caption: str = ""


class PreviewOut(BaseModel):
    text: str
    entities: list[dict[str, object]]
    buttons: list[list[PreviewButtonOut]]
    media: list[PreviewMediaOut]
    is_album: bool
    caption_used: bool
    char_count: int
    notice: str


class ModerationIn(BaseModel):
    blocked_keywords: list[str] | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None
    quiet_hours_tz: str | None = None


class ModerationOut(BaseModel):
    source_id: str
    blocked_keywords: list[str]
    quiet_hours_enabled: bool
    quiet_hours_start: int
    quiet_hours_end: int
    quiet_hours_tz: str


class TickOut(BaseModel):
    published: int
    deleted: int
    comments: int
    due: int


# --- Content Operations 2.0 (v1.9) -----------------------------------------


class AiProfileOut(BaseModel):
    id: str
    key: str
    title: str
    language: str
    tone: str
    max_length: int
    system_instructions: str
    provider_policy: str
    actions: list[str]
    enabled: bool
    builtin: bool
    description: str


class AiProfileIn(BaseModel):
    key: str
    title: str = ""
    language: str = "ru"
    tone: str = "neutral"
    max_length: int = 0
    system_instructions: str = ""
    provider_policy: str = "auto"
    actions: list[str] = Field(default_factory=list)
    description: str = ""


class AiProfileUpdateIn(BaseModel):
    title: str | None = None
    language: str | None = None
    tone: str | None = None
    max_length: int | None = None
    system_instructions: str | None = None
    provider_policy: str | None = None
    actions: list[str] | None = None
    enabled: bool | None = None
    description: str | None = None


class AiProcessIn(BaseModel):
    """Apply an AI profile to an item (or classify only)."""

    profile_key: str = ""
    classify_only: bool = False


class ModerationDecisionIn(BaseModel):
    """A human moderation decision: approve | reject | review."""

    decision: str
    note: str = ""


class AutomationRuleOut(BaseModel):
    id: str
    name: str
    enabled: bool
    source_kind: str
    condition: dict[str, object]
    actions: list[str]
    action_titles: list[str]
    profile_key: str
    priority: int
    description: str


class AutomationRuleIn(BaseModel):
    name: str = ""
    source_kind: str = ""
    condition: dict[str, object] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)
    profile_key: str = ""
    priority: int = 0
    description: str = ""
    enabled: bool = True


class AutomationRuleUpdateIn(BaseModel):
    name: str | None = None
    source_kind: str | None = None
    condition: dict[str, object] | None = None
    actions: list[str] | None = None
    profile_key: str | None = None
    priority: int | None = None
    description: str | None = None
    enabled: bool | None = None


class PipelineRecordOut(BaseModel):
    id: str
    item_id: str
    publication_id: str
    stage: str
    status: str
    source_kind: str
    channel_id: str
    provider: str
    model: str
    fallback_used: bool
    latency_ms: int
    attempts: int
    detail: str
    occurred_at: str


class PipelineAnalyticsOut(BaseModel):
    stage_counts: dict[str, int]
    ai_provider_counts: dict[str, int]
    ai_fallback: int
    ai_failed: int
    comment_posted: int
    comment_failed: int
    delete_failed: int
    recent: list[PipelineRecordOut]


__all__ = [
    "AiProcessIn",
    "AiProfileIn",
    "AiProfileOut",
    "AiProfileUpdateIn",
    "ApplyCleanIn",
    "AutomationRuleIn",
    "AutomationRuleOut",
    "AutomationRuleUpdateIn",
    "ButtonIn",
    "ButtonSetIn",
    "ButtonSetOut",
    "CalendarChannelOut",
    "CalendarEntryOut",
    "CalendarOut",
    "CleanPreviewOut",
    "ContentDashboardOut",
    "ContentItemListOut",
    "ContentItemOut",
    "ContentItemUpdateIn",
    "ContentSourceIn",
    "ContentSourceListOut",
    "ContentSourceOut",
    "GrabOut",
    "ModerationDecisionIn",
    "ModerationIn",
    "ModerationOut",
    "PipelineAnalyticsOut",
    "PipelineRecordOut",
    "PlanIn",
    "PlanOut",
    "PreviewButtonOut",
    "PreviewMediaOut",
    "PreviewOut",
    "PublicationOut",
    "PublishOut",
    "RewriteIn",
    "RewriteOut",
    "RightsOut",
    "ScheduleIn",
    "TargetIn",
    "TickOut",
    "ValidationIssueOut",
    "ValidationOut",
]
