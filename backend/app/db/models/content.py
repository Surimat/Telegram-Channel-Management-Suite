"""Content Studio models (v1.2: content management vertical slice).

A small, explicit content model so the suite can grab, clean, schedule and
publish channel posts without turning into a monolith:

* :class:`ContentSource` — where material comes from (Telegram channel, RSS,
  Atom, a manual/public URL). Fetch state (etag/last-modified/last seen) lives
  here so a feed is never downloaded in full on every run.
* :class:`ContentItem` — one grabbed/drafted piece of content. Carries the
  original text, the cleaned text, Telegram entities, provenance and a
  ``rights_status``.
* :class:`MediaAsset` — a media file attached to an item (image/video/audio/
  document), with a content hash so identical media is never stored twice.
* :class:`Publication` — the intent to publish one item to one channel, with a
  per-target text/media override, its own schedule, status, resulting Telegram
  message ids and an optional auto-delete time.
* :class:`ButtonSet` — inline buttons for a publication (URL/callback/WebApp/
  copy). Only types the current Bot API supports are accepted.
* :class:`CommentPlan` — the "first comment" plan for a publication (posted into
  the channel's linked discussion group, never as a channel post).

Nothing here stores credentials or session data. ``rights_status`` is advisory
metadata for the owner, not a licence check performed on their behalf.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContentSourceKind(enum.StrEnum):
    """Where a content source lives."""

    TELEGRAM = "telegram"  # a Telegram channel/group (via SessionProvider)
    RSS = "rss"
    ATOM = "atom"
    MANUAL = "manual"      # a public URL or hand-entered material


class ContentSourceStatus(enum.StrEnum):
    """Fetch health of a source (honest, never a guess)."""

    IDLE = "idle"            # never fetched
    OK = "ok"                # last fetch succeeded
    ERROR = "error"          # last fetch failed
    PROTECTED = "protected"  # source forbids forwarding/downloading


class RightsStatus(enum.StrEnum):
    """Owner-declared usage rights for a piece of content.

    The suite never performs a legal check; this records what the owner states
    so publishing with unknown rights can warn instead of silently proceeding.
    """

    OWN = "own"                  # the owner's own content
    ALLOWED = "allowed"          # explicitly permitted by the author
    LICENSED = "licensed"        # a licence exists
    PUBLIC = "public"            # publicly available source
    UNKNOWN = "unknown"          # not stated


RIGHTS_TITLES = {
    RightsStatus.OWN: "Свой контент",
    RightsStatus.ALLOWED: "Разрешён к использованию",
    RightsStatus.LICENSED: "Есть лицензия",
    RightsStatus.PUBLIC: "Источник публичный",
    RightsStatus.UNKNOWN: "Не указано",
}


class ContentItemStatus(enum.StrEnum):
    """Lifecycle of a content item (docs/UI.md)."""

    IMPORTED = "imported"    # grabbed, not touched yet
    DRAFT = "draft"          # being edited
    READY = "ready"          # approved for scheduling
    SCHEDULED = "scheduled"  # has at least one scheduled publication
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


STATUS_TITLES = {
    ContentItemStatus.IMPORTED: "Импортировано",
    ContentItemStatus.DRAFT: "Черновик",
    ContentItemStatus.READY: "Готово",
    ContentItemStatus.SCHEDULED: "Запланировано",
    ContentItemStatus.PUBLISHING: "Публикуется",
    ContentItemStatus.PUBLISHED: "Опубликовано",
    ContentItemStatus.FAILED: "Ошибка",
    ContentItemStatus.ARCHIVED: "В архиве",
}

#: Workflow modes (docs: Manual / Semi-auto / Auto). Manual is the default.
MODE_MANUAL = "manual"
MODE_SEMI_AUTO = "semi_auto"
MODE_AUTO = "auto"
VALID_MODES = frozenset({MODE_MANUAL, MODE_SEMI_AUTO, MODE_AUTO})


class PublicationStatus(enum.StrEnum):
    """Lifecycle of one item→channel publication."""

    PLANNED = "planned"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContentSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_sources"

    kind: Mapped[ContentSourceKind] = mapped_column(
        Enum(ContentSourceKind, name="content_source_kind"),
        default=ContentSourceKind.MANUAL,
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    reference: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Registry channel link when this source is a Telegram channel (D-051).
    channel_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    status: Mapped[ContentSourceStatus] = mapped_column(
        Enum(ContentSourceStatus, name="content_source_status"),
        default=ContentSourceStatus.IDLE,
        nullable=False,
    )
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Conditional-GET / incremental state so a feed is not re-downloaded fully.
    etag: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    last_modified: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    last_seen_item: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    last_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]
    last_fetch_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Auto-moderation (v1.2): drop a fetched item before it reaches the drafts.
    #: A JSON list of lowercase keywords; an empty list disables the filter.
    blocked_keywords: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    #: Night moderation: while local time is inside quiet hours a new item is
    #: still grabbed but held (status ``held``) instead of becoming a draft.
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[int] = mapped_column(Integer, default=23, nullable=False)  # hour 0-23
    quiet_hours_end: Mapped[int] = mapped_column(Integer, default=8, nullable=False)  # hour 0-23
    quiet_hours_tz: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ContentSource {self.kind} ref={self.reference!r}>"


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_items"

    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: JSON list of Telegram entities (type/offset/length/url/...).
    entities: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    #: JSON list of inline-button dicts (rendered/validated before publish).
    buttons: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[ContentItemStatus] = mapped_column(
        Enum(ContentItemStatus, name="content_item_status"),
        default=ContentItemStatus.IMPORTED,
        index=True,
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(16), default=MODE_MANUAL, nullable=False)

    source_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    source_channel: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source_author: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]

    rights_status: Mapped[RightsStatus] = mapped_column(
        Enum(RightsStatus, name="content_rights_status"),
        default=RightsStatus.UNKNOWN,
        nullable=False,
    )
    #: Keep an attribution block appended at publish time (default on).
    attribution_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Deterministic dedup keys (never used as a security boundary).
    source_hash: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)

    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]

    #: Night moderation (v1.2): grabbed during quiet hours but held back from
    #: the active draft queue until the owner releases it.
    held: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Reason a fetched item was auto-moderated (kept for transparency).
    moderation_note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ContentItem id={self.id} status={self.status}>"


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"

    item_id: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )
    #: image | video | audio | document
    kind: Mapped[str] = mapped_column(String(16), default="image", nullable=False)
    filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    mime: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration: Mapped[float] = mapped_column(default=0.0, nullable=False)
    #: SHA-256 of the stored file so identical media is reused, never re-stored.
    media_hash: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    #: Hash of the source media before any conversion (media cache key).
    source_hash: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    #: JSON description of the conversion applied (preset/watermark), if any.
    conversion: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MediaAsset {self.kind} {self.filename!r}>"


class Publication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "publications"

    item_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    telegram_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    channel_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status"),
        default=PublicationStatus.PLANNED,
        index=True,
        nullable=False,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]

    #: Per-target overrides (empty = use the item's text/media/buttons).
    text_override: Mapped[str] = mapped_column(Text, default="", nullable=False)
    media_override: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    buttons_override: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: JSON list of the resulting Telegram message ids (an album has several).
    telegram_message_ids: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Idempotency key: a retry after a lost connection must not double-post.
    idempotency_key: Mapped[str] = mapped_column(
        String(128), default="", index=True, nullable=False
    )
    #: When set, the posted message(s) are deleted at this time (durable job).
    delete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # type: ignore[valid-type]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Publication item={self.item_id} channel={self.channel_id} status={self.status}>"


class ButtonSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "button_sets"

    item_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    publication_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    #: JSON list of rows, each a list of button dicts ({text, action, value}).
    rows: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ButtonSet item={self.item_id} pub={self.publication_id}>"


class CommentPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comment_plans"

    publication_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    buttons: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    discussion_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CommentPlan pub={self.publication_id} status={self.status}>"


__all__ = [
    "MODE_AUTO",
    "MODE_MANUAL",
    "MODE_SEMI_AUTO",
    "RIGHTS_TITLES",
    "STATUS_TITLES",
    "VALID_MODES",
    "ButtonSet",
    "CommentPlan",
    "ContentItem",
    "ContentItemStatus",
    "ContentSource",
    "ContentSourceKind",
    "ContentSourceStatus",
    "MediaAsset",
    "Publication",
    "PublicationStatus",
    "RightsStatus",
]
