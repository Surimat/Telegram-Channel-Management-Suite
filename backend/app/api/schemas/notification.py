"""Notification Center API schemas (v1.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NotificationCategoryOut(BaseModel):
    key: str
    label: str
    enabled: bool
    destinations: list[str] = Field(default_factory=list)


class NotificationSettingsOut(BaseModel):
    enabled: bool
    categories: list[NotificationCategoryOut]
    quiet_hours_enabled: bool
    quiet_hours_start: int
    quiet_hours_end: int
    quiet_hours_tz: str
    aggregation_enabled: bool
    destinations: list[dict[str, str]] = Field(default_factory=list)


class NotificationSettingsIn(BaseModel):
    enabled: bool | None = None
    categories: dict[str, bool] | None = None
    routing: dict[str, list[str]] | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None
    quiet_hours_tz: str | None = None
    aggregation_enabled: bool | None = None


class NotificationOut(BaseModel):
    id: str
    category: str
    category_label: str
    priority: str
    priority_label: str
    destination: str
    destination_label: str
    event_key: str
    message: str
    how_to_fix: str
    status: str
    status_label: str
    error: str
    aggregate_count: int
    read: bool
    postponed_until: str = ""
    delivered_at: str = ""
    created_at: str = ""


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int


class NotificationDashboardOut(BaseModel):
    enabled: bool
    pending: int
    failed: int
    quiet_hours_enabled: bool
    in_quiet_hours: bool
    status_counts: dict[str, int] = Field(default_factory=dict)
    category_counts: dict[str, int] = Field(default_factory=dict)


class NotificationTestIn(BaseModel):
    category: str = "system"
    priority: str = "info"
