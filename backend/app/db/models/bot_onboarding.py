"""Mass bot-to-channel onboarding models (v2.0, D-120).

A :class:`BotOnboardingBatch` is one "connect these bots to this channel, with
this rights profile" request. Each :class:`BotOnboardingCandidate` is one bot in
that request and carries the durable queue state of its connection.

This is *composition*, not a parallel system: the actual connection and the real
rights verification reuse :class:`~backend.app.services.binding_service.BindingService`
(the same bot↔channel binding the rest of the suite uses). Nothing here adds a
bot to a channel on its own — the owner confirms each bot through Telegram's
official ``startchannel`` flow; the queue only prepares the link, waits, and then
verifies what Telegram actually granted.

Only non-secret, display-safe data is stored: bot/channel ids and usernames, the
rights profile key, the bot's own deep link and a human-readable error. Tokens are
never stored, returned or logged here (D-110).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Hard cap on bots in one onboarding queue (the UI offers 1–50).
MAX_ONBOARDING_BOTS = 50


class OnboardingStatus(enum.StrEnum):
    """Durable state of one bot's connection operation (shown verbatim in the UI).

    Stored as a plain string, not a DB enum: the state machine may grow and a
    SQLite CHECK constraint cannot be extended by an ALTER (same rule as the
    bot-creation queue, D-109).
    """

    QUEUED = "queued"                        # waiting its turn
    WAITING_CONFIRMATION = "waiting_confirmation"  # link prepared; owner must confirm in Telegram
    VERIFYING = "verifying"                  # the rights check is in flight
    READY = "ready"                          # Telegram confirmed the required right
    NEEDS_PERMISSION = "needs_permission"    # present but missing the required right
    FAILED = "failed"                        # connection could not be verified (retryable)
    SKIPPED = "skipped"                      # the owner skipped this bot


ONBOARDING_STATUS_TITLES = {
    OnboardingStatus.QUEUED: "В очереди",
    OnboardingStatus.WAITING_CONFIRMATION: "Ожидает подтверждения",
    OnboardingStatus.VERIFYING: "Проверка",
    OnboardingStatus.READY: "Готов",
    OnboardingStatus.NEEDS_PERMISSION: "Нужны права",
    OnboardingStatus.FAILED: "Ошибка",
    OnboardingStatus.SKIPPED: "Пропущен",
}

#: Statuses that still need the scheduler to advance the queue.
ACTIVE_ONBOARDING_STATUSES = {
    OnboardingStatus.QUEUED,
    OnboardingStatus.WAITING_CONFIRMATION,
    OnboardingStatus.VERIFYING,
}

#: Terminal statuses a retry must not silently revive.
TERMINAL_ONBOARDING_STATUSES = {
    OnboardingStatus.READY,
    OnboardingStatus.SKIPPED,
}


class OnboardingBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_onboarding_batches"

    channel_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    channel_label: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    rights_profile: Mapped[str] = mapped_column(
        String(32), default="reactions", nullable=False
    )
    #: The BindingService function this profile maps to (reactions/posting/…).
    function: Mapped[str] = mapped_column(String(32), default="reactions", nullable=False)

    requested_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    permission_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Paused queue: the durable handler no-ops until the owner resumes it.
    queue_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<OnboardingBatch channel={self.channel_id!r} "
            f"profile={self.rights_profile} ready={self.ready_count}>"
        )


class OnboardingCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_onboarding_candidates"

    batch_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    bot_id: Mapped[str] = mapped_column(String(32), default="", index=True, nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bot_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    bot_title: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    channel_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    rights_profile: Mapped[str] = mapped_column(String(32), default="reactions", nullable=False)
    function: Mapped[str] = mapped_column(String(32), default="reactions", nullable=False)

    #: The official ``t.me/<bot>?startchannel&admin=…`` link (display-safe).
    deep_link: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default=OnboardingStatus.QUEUED.value, index=True, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: The verified BindingService binding this candidate resolved to (empty until
    #: the connection step runs).
    binding_id: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def status_enum(self) -> OnboardingStatus:
        try:
            return OnboardingStatus(self.status)
        except ValueError:
            return OnboardingStatus.QUEUED

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OnboardingCandidate {self.bot_username!r} {self.status}>"


__all__ = [
    "ACTIVE_ONBOARDING_STATUSES",
    "MAX_ONBOARDING_BOTS",
    "ONBOARDING_STATUS_TITLES",
    "TERMINAL_ONBOARDING_STATUSES",
    "OnboardingBatch",
    "OnboardingCandidate",
    "OnboardingStatus",
]
