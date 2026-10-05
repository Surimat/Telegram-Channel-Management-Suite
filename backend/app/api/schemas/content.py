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


__all__ = [
    "ApplyCleanIn",
    "CleanPreviewOut",
    "ContentDashboardOut",
    "ContentItemListOut",
    "ContentItemOut",
    "ContentItemUpdateIn",
    "ContentSourceIn",
    "ContentSourceListOut",
    "ContentSourceOut",
    "GrabOut",
    "RewriteIn",
    "RewriteOut",
    "RightsOut",
]
