"""Invite-link campaign models (product slice: no-session promotion).

Directly inviting users requires a user (MTProto) account. Without one, the
Invite Manager still has a genuinely useful mode: **promotion via invite
links**. A campaign groups named invite links for a target channel, tracks join
requests, and reports conversion — all through the official Bot API, so it works
in bot-only mode.

Honesty rules baked into the model:

* A campaign never claims to know *who clicked* a link; Telegram only reports
  joins/join-requests. Counters are therefore joins/requests, not clicks.
* The risk mode is a *pacing preference*, never a limit-bypass. Telegram's own
  FloodWait/privacy rules always win.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CampaignStatus(enum.StrEnum):
    DRAFT = "draft"          # created, no links yet
    ACTIVE = "active"        # links are live
    PAUSED = "paused"        # temporarily stopped (links may be revoked)
    COMPLETED = "completed"  # operator finished it
    DISABLED = "disabled"    # turned off


class LinkStatus(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"
    EXPIRED = "expired"
    ERROR = "error"


class JoinRequestStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    UNKNOWN = "unknown"


class InviteCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named promotion campaign: a set of invite links for one target."""

    __tablename__ = "invite_campaigns"

    name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    # Target channel/group people are invited to.
    channel_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    target: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    target_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"),
        default=CampaignStatus.DRAFT,
        index=True,
        nullable=False,
    )

    # Pacing preference: conservative | standard | manual. Never a limit bypass.
    risk_mode: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)

    # Whether new members must be approved by an admin (join requests on).
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Denormalised counters for cheap UI polling.
    links_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joins_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<InviteCampaign name={self.name!r} status={self.status}>"


class InviteLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One named invite link (optionally a join-request link)."""

    __tablename__ = "invite_links"

    campaign_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    # The t.me link Telegram returned (safe to display; not a secret).
    link: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    status: Mapped[LinkStatus] = mapped_column(
        Enum(LinkStatus, name="link_status"),
        default=LinkStatus.ACTIVE,
        index=True,
        nullable=False,
    )

    join_request: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    member_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expire_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    joins_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<InviteLink label={self.label!r} status={self.status}>"


class JoinRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pending/resolved join request observed via the Bot API."""

    __tablename__ = "join_requests"

    campaign_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    link_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    status: Mapped[JoinRequestStatus] = mapped_column(
        Enum(JoinRequestStatus, name="join_request_status"),
        default=JoinRequestStatus.PENDING,
        index=True,
        nullable=False,
    )
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<JoinRequest user={self.telegram_user_id} status={self.status}>"


__all__ = [
    "CampaignStatus",
    "InviteCampaign",
    "InviteLink",
    "JoinRequest",
    "JoinRequestStatus",
    "LinkStatus",
]
