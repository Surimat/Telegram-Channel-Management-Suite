"""Editorial Workspace models (v1.4: редакционная комната).

A linked Telegram forum supergroup where the owner, editors and moderators work
on the same publication queue the Web UI shows. The Telegram group is a *real*
group (visible on staff phones); the suite keeps the queue itself and mirrors it
into forum topics as one card per content item.

* :class:`EditorialRoom` — one channel's editorial room (the linked forum group,
  the manager/editorial bot, the topic map and the verified bot rights).
* :class:`EditorialMember` — a Telegram user granted a role (owner/editor/
  moderator/viewer), always identified by the numeric Telegram user id.
* :class:`EditorialItem` — one queued content item: its queue status, target
  channel, the Telegram card message, an ``order_index`` (the suite, not
  Telegram, owns the order) and a ``version`` for conflict detection.
* :class:`EditorialAuditEntry` — who did what, when, and the status change.

Only non-secret, display-safe data is stored. Telegram user ids are the
authorization identifier; usernames are never trusted as identity.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EditorialStatus(enum.StrEnum):
    """Queue lifecycle of an editorial item (one card = one content item)."""

    INBOX = "inbox"          # 📥 Входящие
    EDITING = "editing"      # ✍️ На редактировании
    REVIEW = "review"        # ✅ На согласовании
    APPROVED = "approved"    # approved (moving toward scheduling)
    SCHEDULED = "scheduled"  # 📅 Очередь публикации
    PUBLISHED = "published"  # 🚀 Опубликовано
    REJECTED = "rejected"    # ❌ Отклонено
    PAUSED = "paused"        # ⏸ Пауза
    FAILED = "failed"        # ⚠ Ошибки


STATUS_TITLES = {
    EditorialStatus.INBOX: "Входящие",
    EditorialStatus.EDITING: "На редактировании",
    EditorialStatus.REVIEW: "На согласовании",
    EditorialStatus.APPROVED: "Одобрено",
    EditorialStatus.SCHEDULED: "Очередь публикации",
    EditorialStatus.PUBLISHED: "Опубликовано",
    EditorialStatus.REJECTED: "Отклонено",
    EditorialStatus.PAUSED: "Пауза",
    EditorialStatus.FAILED: "Ошибки",
}

#: The default forum topics created in an editorial room, in order. ``key`` is the
#: editorial status the topic mirrors; ``emoji``/``title`` are shown to editors.
DEFAULT_TOPICS: tuple[tuple[str, str, str], ...] = (
    ("inbox", "📥", "Входящие"),
    ("editing", "✍️", "На редактировании"),
    ("review", "✅", "На согласовании"),
    ("scheduled", "📅", "Очередь публикации"),
    ("published", "🚀", "Опубликовано"),
    ("failed", "⚠", "Ошибки"),
)

#: Optional extra topic (not created by default).
OPTIONAL_TOPICS: tuple[tuple[str, str, str], ...] = (
    ("ideas", "💡", "Идеи"),
)


class EditorialRole(enum.StrEnum):
    """Access level of a Telegram user in the editorial room."""

    OWNER = "owner"          # everything
    EDITOR = "editor"        # edit / approve / move
    MODERATOR = "moderator"  # moderate and reject
    VIEWER = "viewer"        # read only


ROLE_TITLES = {
    EditorialRole.OWNER: "Владелец",
    EditorialRole.EDITOR: "Редактор",
    EditorialRole.MODERATOR: "Модератор",
    EditorialRole.VIEWER: "Наблюдатель",
}

#: Actions a role is allowed to perform. ``approve`` implies moving forward;
#: publishing is restricted to owner/editor (a moderator must not publish).
ROLE_ACTIONS = {
    EditorialRole.OWNER: {
        "view", "edit", "approve", "reject", "reorder", "schedule",
        "publish", "moderate", "delete_queued", "delete_published", "manage_roles",
    },
    EditorialRole.EDITOR: {
        "view", "edit", "approve", "reject", "reorder", "schedule", "publish",
    },
    EditorialRole.MODERATOR: {"view", "reject", "moderate", "reorder"},
    EditorialRole.VIEWER: {"view"},
}


class RoomStatus(enum.StrEnum):
    """Setup state of an editorial room (never claims rights before checking)."""

    NOT_CONNECTED = "not_connected"    # group not chosen yet
    NEEDS_RIGHTS = "needs_rights"      # bot present but missing a right
    READY = "ready"                    # bot verified + topics created
    ERROR = "error"                    # last check failed


ROOM_STATUS_TITLES = {
    RoomStatus.NOT_CONNECTED: "Не подключена",
    RoomStatus.NEEDS_RIGHTS: "Нужны права",
    RoomStatus.READY: "Готова",
    RoomStatus.ERROR: "Ошибка",
}


class EditorialRoom(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One channel's editorial room (its linked forum supergroup)."""

    __tablename__ = "editorial_rooms"

    channel_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    channel_label: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # The editorial bot (manager or a dedicated bot) used to post cards.
    bot_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # The Telegram forum supergroup id (negative for supergroups).
    group_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    group_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, name="editorial_room_status"),
        default=RoomStatus.NOT_CONNECTED,
        index=True,
        nullable=False,
    )
    # JSON map {status_key: topic_id}; the suite mirrors cards into these topics.
    topics: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Verified bot rights (never assumed; a missing flag stays False).
    bot_is_member: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_send_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_edit_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_delete_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_topics: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("channel_id", name="uq_editorial_room_channel"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EditorialRoom channel={self.channel_id} status={self.status}>"


class EditorialMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Telegram user with a role in an editorial room."""

    __tablename__ = "editorial_members"

    room_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # The authorization identifier: a numeric Telegram user id. Never a username.
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    role: Mapped[EditorialRole] = mapped_column(
        Enum(EditorialRole, name="editorial_role"),
        default=EditorialRole.VIEWER,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("room_id", "telegram_user_id", name="uq_editorial_member"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EditorialMember user={self.telegram_user_id} role={self.role}>"


class EditorialItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One queued content item in an editorial room."""

    __tablename__ = "editorial_items"

    room_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    content_item_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    # Target channel (a content item may target several; one card per target).
    channel_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    channel_label: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    status: Mapped[EditorialStatus] = mapped_column(
        Enum(EditorialStatus, name="editorial_status"),
        default=EditorialStatus.INBOX,
        index=True,
        nullable=False,
    )
    # The suite owns the order; Telegram cards only reflect it (no message moves).
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # The forum topic + Telegram card message this item is mirrored into.
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    card_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Assigned editor (numeric Telegram id), 0 = unassigned.
    assigned_user_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optimistic concurrency: an editor who saved a stale version is warned.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        Index("ix_editorial_items_room_status", "room_id", "status"),
        UniqueConstraint(
            "room_id", "content_item_id", "channel_id", name="uq_editorial_item_target"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EditorialItem id={self.id} status={self.status} order={self.order_index}>"


class EditorialAuditEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Who did what, when, on which item, and the status change (audit log)."""

    __tablename__ = "editorial_audit"

    room_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    item_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    old_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EditorialAuditEntry {self.action} by={self.actor_telegram_id}>"


__all__ = [
    "DEFAULT_TOPICS",
    "OPTIONAL_TOPICS",
    "ROLE_ACTIONS",
    "ROLE_TITLES",
    "ROOM_STATUS_TITLES",
    "STATUS_TITLES",
    "EditorialAuditEntry",
    "EditorialItem",
    "EditorialMember",
    "EditorialRole",
    "EditorialRoom",
    "EditorialStatus",
    "RoomStatus",
]
