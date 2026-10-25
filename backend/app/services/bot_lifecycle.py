"""Bot-lifecycle recovery and adoption (D-125).

One place that owns the bot lifecycle after a restart and when a bot appears.

Recovery. The Bot Factory creation queue and the Bot Onboarding queue are both
durable and one-operation-per-tick, but each tracks its in-flight row
separately: the factory uses ``QUEUED → RUNNING → SUCCESS|FAILED``
(``QueueState``) and onboarding uses ``QUEUED → VERIFYING → READY|FAILED``
(``OnboardingStatus``). ``run_queue_once`` only ever picks a ``QUEUED`` row, so a
row left mid-flight by a crash would hang the queue forever. This service calls
the recover method each queue already owns, so no lifecycle stage is left
unrecovered.

Adoption. A bot created through the official deep link (``t.me/newbot``) is
announced to the manager bot by a ``managed_bot`` update. This service routes
that creation into its Bot Factory batch (idempotently), so the batch completes
and is reported instead of silently staying "created by hand, never registered".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.bot_factory import BatchStatus, QueueState
from backend.app.manager.bus import (
    CATEGORY_TELEGRAM,
    PRIORITY_SUCCESS,
    Notification,
    get_notification_bus,
)
from backend.app.services.bot_factory import AdoptionResult, BotFactoryService
from backend.app.services.bot_onboarding import BotOnboardingService


@dataclass(slots=True)
class LifecycleRecoveryResult:
    """How many in-flight operations were re-queued per stage."""

    bot_factory: int = 0
    bot_onboarding: int = 0

    @property
    def total(self) -> int:
        return self.bot_factory + self.bot_onboarding


class BotLifecycleService:
    """Recovers every bot-lifecycle queue and adopts created bots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recover(self) -> LifecycleRecoveryResult:
        factory = await BotFactoryService(self.session).recover()
        onboarding = await BotOnboardingService(self.session).recover()
        return LifecycleRecoveryResult(
            bot_factory=factory, bot_onboarding=onboarding
        )

    async def adopt_managed_bot(
        self,
        *,
        username: str,
        telegram_id: int,
        title: str = "",
    ) -> AdoptionResult:
        """Register a deep-link-created bot into its batch (idempotent).

        Delegates to :meth:`BotFactoryService.adopt_managed_bot`. A bot with an
        unknown username is not ours — it is ignored, never searched for or
        imported (D-070). If the same ``managed_bot`` update is delivered twice,
        the second call is a no-op (the candidate already points at a bot), so no
        duplicate bot is created and no counter is inflated.
        """
        result = await BotFactoryService(self.session).adopt_managed_bot(
            telegram_id, username=username, title=title
        )
        if result.adopted:
            self._emit_adopted(username, result.candidate_id)
            await self._settle_if_complete(result.batch_ids[0])
        return result

    async def _settle_if_complete(self, batch_id: str) -> bool:
        """Mark a deep-link batch COMPLETED once no candidate is left waiting.

        The owner completes a deep-link batch by hand, one bot at a time. When the
        last waiting candidate is adopted nothing else would settle the batch, so
        it would report itself unfinished forever. Settling is idempotent: an
        already-completed batch is left untouched.
        """
        factory = BotFactoryService(self.session)
        batch = await factory.get_batch(batch_id)
        if batch.status is BatchStatus.COMPLETED:
            return True
        rows = await factory.candidates.list_for_batch(batch_id)
        active = {
            QueueState.QUEUED.value,
            QueueState.RUNNING.value,
            QueueState.PENDING.value,
        }
        pending = [r for r in rows if not r.bot_id and r.queue_state in active]
        if not rows or pending:
            return False
        batch.status = BatchStatus.COMPLETED
        if batch.completed_at is None:
            batch.completed_at = utcnow()
        await self.session.commit()
        return True

    def _emit_adopted(self, username: str, candidate_id: str) -> None:
        """Publish a secret-free "bot created" notification (best effort)."""
        clean = username.lstrip("@")
        try:
            get_notification_bus().publish(
                Notification(
                    category=CATEGORY_TELEGRAM,
                    event_key="bot_factory.bot_created",
                    message=(
                        f"Бот @{clean} создан и добавлен в пакет фабрики ботов."
                    ),
                    level="INFO",
                    priority=PRIORITY_SUCCESS,
                    dedup_key=f"bot_factory.bot_created:{candidate_id}",
                )
            )
        except Exception:  # pragma: no cover - notification is best effort
            return


__all__ = [
    "AdoptionResult",
    "BotLifecycleService",
    "LifecycleRecoveryResult",
]

