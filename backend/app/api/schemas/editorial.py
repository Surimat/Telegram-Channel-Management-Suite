"""Editorial Workspace API schemas (v1.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EditorialRoomOut(BaseModel):
    id: str
    channel_id: str
    channel_label: str
    bot_id: str
    group_chat_id: int | None
    group_title: str
    status: str
    status_label: str
    topics: dict[str, int] = Field(default_factory=dict)
    bot_is_member: bool = False
    bot_is_admin: bool = False
    can_send_messages: bool = False
    can_manage_topics: bool = False
    last_checked: str = ""
    last_error: str = ""


class EditorialRoomListOut(BaseModel):
    items: list[EditorialRoomOut]
    status_titles: dict[str, str] = Field(default_factory=dict)


class EditorialRoomIn(BaseModel):
    channel_id: str
    group_chat_id: int
    bot_id: str = ""
    group_title: str = ""


class EditorialRoomCheckOut(BaseModel):
    room_id: str
    status: str
    status_label: str
    message: str
    how_to_fix: str = ""
    topics: dict[str, int] = Field(default_factory=dict)


class EditorialMemberOut(BaseModel):
    id: str
    telegram_user_id: int
    display_name: str
    username: str
    role: str
    role_title: str
    enabled: bool


class EditorialMemberIn(BaseModel):
    telegram_user_id: int
    role: str
    display_name: str = ""
    username: str = ""
    enabled: bool = True


class EditorialItemOut(BaseModel):
    id: str
    content_item_id: str
    channel_id: str
    channel_label: str
    title: str
    status: str
    status_title: str
    order_index: int
    assigned_user_id: int
    version: int
    error: str
    scheduled_at: str = ""
    card_message_id: int | None = None
    topic_id: int | None = None
    available_actions: list[str] = Field(default_factory=list)


class EditorialBoardOut(BaseModel):
    room_id: str
    channel_id: str
    channel_label: str
    group_title: str
    status: str
    status_label: str
    topics: dict[str, int] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    columns: dict[str, list[EditorialItemOut]] = Field(default_factory=dict)
    status_titles: dict[str, str] = Field(default_factory=dict)


class EditorialEnqueueIn(BaseModel):
    content_item_id: str
    channel_id: str = ""
    title: str = ""


class EditorialMoveIn(BaseModel):
    status: str
    actor_telegram_id: int = 0
    actor_name: str = ""
    expected_version: int | None = None


class EditorialReorderIn(BaseModel):
    status: str
    ordered_ids: list[str] = Field(default_factory=list)
    actor_telegram_id: int = 0
    actor_name: str = ""


class EditorialActionResultOut(BaseModel):
    ok: bool
    action: str
    message: str
    item_id: str = ""
    status: str = ""


class EditorialAuditOut(BaseModel):
    id: str
    item_id: str
    actor_telegram_id: int
    actor_name: str
    action: str
    old_status: str
    new_status: str
    detail: str
    created_at: str = ""
