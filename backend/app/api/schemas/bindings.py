"""Schemas for bot↔channel bindings and channel reaction capabilities."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BindingCreate(BaseModel):
    bot_id: str
    channel_id: str
    function: str = "reactions"


class BindingOut(BaseModel):
    id: str
    bot_id: str
    bot_username: str = ""
    channel_id: str
    channel_label: str = ""
    function: str
    status: str
    status_label: str = ""
    role: str
    can_post_messages: bool = False
    can_edit_messages: bool = False
    can_delete_messages: bool = False
    can_manage_chat: bool = False
    can_invite_users: bool = False
    can_set_reactions: bool = False
    invite_link: str = ""
    note: str = ""
    last_checked: datetime | None = None
    last_error: str = ""
    created_at: datetime


class BindingListOut(BaseModel):
    items: list[BindingOut]
    total: int


class BindingCheckOut(BaseModel):
    binding_id: str
    status: str
    status_label: str
    role: str
    present: bool
    can_set_reactions: bool
    message: str
    how_to_fix: str = ""


class CapabilityOut(BaseModel):
    channel_id: str
    status: str
    available: list[str] = Field(default_factory=list)
    bot_reactions: list[str] = Field(default_factory=list)
    reactions_limit: int = 0
    paid_available: bool = False
    message: str = ""
    last_checked: str = ""
