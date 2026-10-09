"""Channel Registry API schemas.

Responses expose only display-safe fields and never secrets.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChannelCreate(BaseModel):
    reference: str
    title: str = ""
    kind: str = "unknown"
    make_default: bool = False
    note: str = ""


class ChannelUpdate(BaseModel):
    reference: str | None = None
    title: str | None = None
    note: str | None = None
    status: str | None = None
    target_language: str | None = None


class ChannelModulesIn(BaseModel):
    modules: dict[str, bool] = Field(default_factory=dict)


class ChannelVerifyIn(BaseModel):
    account_id: str


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    telegram_id: int | None = None
    username: str = ""
    title: str = ""
    kind: str
    status: str
    is_default: bool = False
    modules: dict[str, bool] = Field(default_factory=dict)
    verification_status: str = ""
    verification_message: str = ""
    verification_hint: str = ""
    participants_count: int | None = None
    last_verified_at: datetime | None = None
    note: str = ""
    target_language: str = "auto"
    created_at: datetime
    updated_at: datetime


class ChannelListOut(BaseModel):
    items: list[ChannelOut]
    total: int
    limit: int
    offset: int


class ChannelSummaryOut(BaseModel):
    total: int = 0
    verified: int = 0
    with_warning: int = 0
    with_error: int = 0
    default_channel_id: str | None = None
    default_channel_label: str = ""


class ChannelVerificationOut(BaseModel):
    channel_id: str
    status: str
    status_label: str = ""
    found: bool = False
    title: str = ""
    username: str = ""
    kind: str = ""
    participants_count: int | None = None
    message: str = ""
    how_to_fix: str = ""
    retry_after: int | None = None
