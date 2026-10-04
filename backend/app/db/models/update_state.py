"""Auto-update state model (product slice: update service).

Auto-update is **off by default** and never blocks startup. This row stores the
owner's preference plus the last check/apply result so the UI can show what
happened without re-querying GitHub on every page load.

No secrets are stored. The update flow (check → confirm → download → checksum →
backup → apply on shutdown → health check → rollback) keeps all of its state in
plain files under the runtime directory; this table only mirrors the essentials.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Update states (shown in the UI verbatim).
UPDATE_IDLE = "idle"
UPDATE_CHECKING = "checking"
UPDATE_AVAILABLE = "available"
UPDATE_UP_TO_DATE = "up_to_date"
UPDATE_DOWNLOADED = "downloaded"
UPDATE_APPLYING = "applying"
UPDATE_FAILED = "failed"
UPDATE_ERROR = "error"

UPDATE_MESSAGES = {
    UPDATE_IDLE: "Обновления не проверялись.",
    UPDATE_CHECKING: "Проверяем обновления…",
    UPDATE_AVAILABLE: "Доступно обновление.",
    UPDATE_UP_TO_DATE: "У вас последняя версия.",
    UPDATE_DOWNLOADED: "Обновление скачано и проверено. Установится при завершении работы.",
    UPDATE_APPLYING: "Устанавливаем обновление…",
    UPDATE_FAILED: "Обновление не установилось — выполнена безопасная отмена.",
    UPDATE_ERROR: "Не удалось проверить обновления.",
}


class UpdateState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Auto-update preference and last-result snapshot (single active row)."""

    __tablename__ = "update_state"

    auto_update_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    state: Mapped[str] = mapped_column(String(24), default=UPDATE_IDLE, nullable=False)
    current_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    latest_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    release_url: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    release_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Staged artifact metadata (path under the runtime dir; never committed).
    staged_file: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    staged_sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UpdateState enabled={self.auto_update_enabled} state={self.state}>"


__all__ = [
    "UPDATE_APPLYING",
    "UPDATE_AVAILABLE",
    "UPDATE_CHECKING",
    "UPDATE_DOWNLOADED",
    "UPDATE_ERROR",
    "UPDATE_FAILED",
    "UPDATE_IDLE",
    "UPDATE_MESSAGES",
    "UPDATE_UP_TO_DATE",
    "UpdateState",
]
