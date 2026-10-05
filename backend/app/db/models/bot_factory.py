"""Bot Factory models (v1.3: bulk managed-bot preparation).

A :class:`BotBatch` is one "I need N managed bots" request. It records the
generator inputs, progress counters and status. A :class:`BotCandidate` is one
prepared bot inside the batch: its suggested display name, suggested username,
the *real* availability status Telegram reported, and the creation/token state.

Nothing here is a bypass of Telegram's limits. The batch only *prepares*
candidates; a candidate becomes a real bot only through the official managed-bot
flow (``bots.checkUsername`` / ``bots.createBot`` / the manager bot's token
export). ``BOT_CREATE_LIMIT_NOTE`` is shown verbatim in the UI so the owner is
never promised unlimited bots.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Shown verbatim in the UI (never promise unlimited bots).
BOT_CREATE_LIMIT_NOTE = (
    "Telegram ограничивает количество принадлежащих вам ботов. "
    "Создать больше доступного лимита невозможно."
)


class BatchStatus(enum.StrEnum):
    """Lifecycle of a bot batch."""

    DRAFT = "draft"          # candidates generated, nothing checked
    CHECKING = "checking"    # availability check in progress
    READY = "ready"          # at least one candidate is available
    CREATING = "creating"    # creation in progress
    COMPLETED = "completed"  # all available candidates created
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"


BATCH_STATUS_TITLES = {
    BatchStatus.DRAFT: "Черновик",
    BatchStatus.CHECKING: "Проверка",
    BatchStatus.READY: "Готов к созданию",
    BatchStatus.CREATING: "Создание",
    BatchStatus.COMPLETED: "Завершён",
    BatchStatus.PAUSED: "Пауза",
    BatchStatus.CANCELLED: "Отменён",
    BatchStatus.FAILED: "Ошибка",
}


class CandidateStatus(enum.StrEnum):
    """Lifecycle of one prepared bot candidate."""

    GENERATED = "generated"          # name/username suggested, not checked
    CHECKING = "checking"            # check in progress
    AVAILABLE = "available"          # Telegram confirmed the username is free
    OCCUPIED = "occupied"            # username already taken
    INVALID = "invalid"              # username violates Telegram rules
    READY = "ready"                  # available + selected for creation
    CREATING = "creating"
    CREATED = "created"              # bot exists, token not imported yet
    TOKEN_IMPORTED = "token_imported"  # bot exists and its token is registered
    FAILED = "failed"
    CANCELLED = "cancelled"


CANDIDATE_STATUS_TITLES = {
    CandidateStatus.GENERATED: "Сгенерирован",
    CandidateStatus.CHECKING: "Проверка",
    CandidateStatus.AVAILABLE: "Свободен",
    CandidateStatus.OCCUPIED: "Занят",
    CandidateStatus.INVALID: "Недопустим",
    CandidateStatus.READY: "Готов",
    CandidateStatus.CREATING: "Создаётся",
    CandidateStatus.CREATED: "Создан",
    CandidateStatus.TOKEN_IMPORTED: "Токен получен",
    CandidateStatus.FAILED: "Ошибка",
    CandidateStatus.CANCELLED: "Отменён",
}

#: Terminal candidate states (never re-created implicitly).
TERMINAL_CANDIDATE_STATUSES = {
    CandidateStatus.TOKEN_IMPORTED,
    CandidateStatus.CANCELLED,
}


class BotBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_batches"

    title: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    # Generator inputs (kept so a batch can be reviewed and re-run).
    prefix: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    topic: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    style: Mapped[str] = mapped_column(String(32), default="neutral", nullable=False)
    name_template: Mapped[str] = mapped_column(
        String(120), default="{prefix} {index}", nullable=False
    )
    username_template: Mapped[str] = mapped_column(
        String(120), default="{prefix}_{index}_bot", nullable=False
    )

    # The manager bot that will control the created bots (our Bot row id) and its
    # Telegram @username (needed for the official creation call and deep links).
    manager_bot_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    manager_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # The owner's user account used for native creation (empty = deep-link only).
    account_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    # Optional channel to bind created bots to afterwards.
    channel_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    requested_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus, name="bot_batch_status"),
        default=BatchStatus.DRAFT,
        index=True,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BotBatch {self.title!r} status={self.status} created={self.created_count}>"


class BotCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_candidates"

    batch_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    suggested_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    suggested_username: Mapped[str] = mapped_column(
        String(64), default="", index=True, nullable=False
    )

    # What Telegram (or the local validator) reported for the username.
    username_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    username_message: Mapped[str] = mapped_column(Text, default="", nullable=False)

    creation_status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="bot_candidate_status"),
        default=CandidateStatus.GENERATED,
        index=True,
        nullable=False,
    )

    # Filled once the bot exists: our Bot row id and Telegram identity.
    bot_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deep_link: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BotCandidate {self.suggested_username!r} {self.creation_status}>"


__all__ = [
    "BATCH_STATUS_TITLES",
    "BOT_CREATE_LIMIT_NOTE",
    "CANDIDATE_STATUS_TITLES",
    "TERMINAL_CANDIDATE_STATUSES",
    "BatchStatus",
    "BotBatch",
    "BotCandidate",
    "CandidateStatus",
]
