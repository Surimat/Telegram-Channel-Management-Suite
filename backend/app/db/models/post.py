"""Post model (PHASE 3).

The minimal channel-post entity needed by the Reaction Manager. A post can be
ingested from a Telegram update/adapter later or created through the service.
Full content analytics is a later phase; this only stores what reactions need.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PostStatus(enum.StrEnum):
    """Processing state of a post in the pipeline."""

    NEW = "new"                  # ingested, not classified
    CLASSIFIED = "classified"    # category known
    PLANNED = "planned"          # reaction jobs created
    PROCESSING = "processing"    # jobs still running
    DONE = "done"                # all jobs finished
    SKIPPED = "skipped"          # reactions disabled / no bots / profile off
    FAILED = "failed"            # planning or execution failed


class Post(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "posts"

    # Telegram identity (may be empty for a simulated/pasted post).
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    channel_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Classification result (filled by the Rules Engine / future AI).
    category: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    category_title: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    classification_source: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    matched_terms: Mapped[str] = mapped_column(Text, default="", nullable=False)

    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, name="post_status"), default=PostStatus.NEW, index=True, nullable=False
    )

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Post id={self.id} category={self.category!r} status={self.status}>"


__all__ = ["Post", "PostStatus"]
