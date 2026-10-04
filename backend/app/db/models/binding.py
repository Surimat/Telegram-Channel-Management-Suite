"""Bot ↔ channel binding model (product slice: bot-only mode).

A :class:`BotChannelBinding` records that a specific bot was connected to a
specific registry channel, and — importantly — the *verified* state of that
connection: whether Telegram confirmed the bot is present, its role, and which
administrator rights it actually has. Nothing is assumed: a binding only becomes
``ready`` after the provider confirmed the required permission.

This is what lets the Reaction Manager work **without any user session**: a bot
reacts to channel posts through the official Bot API, and the binding is the
source of truth for "can this bot do the job here?".

Only non-secret, display-safe data is stored (bot/channel ids, role, booleans,
a human-readable error). No tokens, session contents or API hashes.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BindingStatus(enum.StrEnum):
    """Lifecycle of a bot↔channel connection (shown in the UI verbatim)."""

    NOT_CONNECTED = "not_connected"    # added in the app, not verified with Telegram
    CONNECTED = "connected"            # Telegram confirms the bot is a member
    NEEDS_PERMISSION = "needs_permission"  # present but missing a required right
    READY = "ready"                    # present *and* able to perform the function
    ERROR = "error"                    # last check failed (network/limits/etc.)


class BindingRole(enum.StrEnum):
    """The bot's role in the channel, as reported by Telegram."""

    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    LEFT = "left"
    UNKNOWN = "unknown"


#: The channel function a binding is being checked for. The Reaction Manager
#: needs ``reactions``; other modules may need posting or editing.
FUNCTION_REACTIONS = "reactions"
FUNCTION_POSTING = "posting"
FUNCTION_EDITING = "editing"

FUNCTION_TITLES = {
    FUNCTION_REACTIONS: "Реакции",
    FUNCTION_POSTING: "Публикация",
    FUNCTION_EDITING: "Редактирование",
}


class BotChannelBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One verified bot↔channel connection."""

    __tablename__ = "bot_channel_bindings"

    bot_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # Registry channel id (Channel.id). The display reference/title is copied
    # here so a binding stays readable even if the channel row is later edited.
    channel_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    channel_label: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Which function this binding is meant to serve (see FUNCTION_*).
    function: Mapped[str] = mapped_column(String(32), default=FUNCTION_REACTIONS, nullable=False)

    status: Mapped[BindingStatus] = mapped_column(
        Enum(BindingStatus, name="binding_status"),
        default=BindingStatus.NOT_CONNECTED,
        index=True,
        nullable=False,
    )
    role: Mapped[BindingRole] = mapped_column(
        Enum(BindingRole, name="binding_role"),
        default=BindingRole.UNKNOWN,
        nullable=False,
    )

    # Verified rights (all default False — never assume a permission).
    can_post_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_edit_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_delete_messages: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_chat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_invite_users: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_set_reactions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # The official Telegram deep link used to add the bot to the channel.
    invite_link: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Free-form JSON of the raw permission map (for diagnostics, no secrets).
    permissions: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("bot_id", "channel_id", "function", name="uq_binding_bot_channel_fn"),
        Index("ix_bindings_channel_status", "channel_id", "status"),
    )

    @property
    def is_ready(self) -> bool:
        return self.status is BindingStatus.READY

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<BotChannelBinding bot={self.bot_id} channel={self.channel_id} "
            f"status={self.status}>"
        )


__all__ = [
    "FUNCTION_EDITING",
    "FUNCTION_POSTING",
    "FUNCTION_REACTIONS",
    "FUNCTION_TITLES",
    "BindingRole",
    "BindingStatus",
    "BotChannelBinding",
]
