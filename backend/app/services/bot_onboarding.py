"""Mass bot-to-channel onboarding service (v2.0, D-120).

Connects bots created by the Bot Factory to a channel in bulk, honestly and
durably — using only Telegram's **official** flows:

* every link is the official channel deep link
  ``https://t.me/<bot>?startchannel&admin=<rights>`` (the owner confirms each bot
  by hand inside Telegram; nothing is added silently and no confirmation is
  faked);
* the actual result is verified by the existing
  :class:`~backend.app.services.binding_service.BindingService` — the *real*
  ``getChatMember`` rights probe, never a guess;
* a durable, restart-safe queue paces the flow one bot per scheduler tick, so one
  failed bot never stops the rest and a restart resumes where it left off.

This is composition, not a parallel system: Bot Factory provides the bots, the
Binding Service owns the bot↔channel relationship, the scheduler owns durability,
and the Notification Center announces completion. Tokens are never read, shown or
logged here.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.base import utcnow
from backend.app.db.models.binding import (
    FUNCTION_EDITING,
    FUNCTION_POSTING,
    FUNCTION_REACTIONS,
)
from backend.app.db.models.bot import Bot
from backend.app.db.models.bot_onboarding import (
    MAX_ONBOARDING_BOTS,
    ONBOARDING_STATUS_TITLES,
    OnboardingBatch,
    OnboardingCandidate,
    OnboardingStatus,
)
from backend.app.db.repositories.bot_onboarding import (
    OnboardingBatchRepository,
    OnboardingCandidateRepository,
)
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.binding_service import BindingService, BindingServiceError
from backend.app.services.events_service import EventsService
from backend.app.services.notification_service import NotificationCenterService

ProviderFactory = Callable[..., TelegramBotProvider]

MODULE = "bot_onboarding"

#: Durable-queue kind for the onboarding tick. The handler advances exactly one
#: bot per tick and re-schedules itself while work remains (restart-safe).
BOT_ONBOARDING_JOB_KIND = "bot_onboarding.tick"

#: The right a binding must have verified before the bot is "ready" for a
#: function. Mirrors ``BindingService`` (which owns the actual probe).
FUNCTION_PERMISSION = {
    FUNCTION_REACTIONS: "can_set_reactions",
    FUNCTION_POSTING: "can_post_messages",
    FUNCTION_EDITING: "can_edit_messages",
}


@dataclass(frozen=True, slots=True)
class RightsProfile:
    """A minimal, purpose-named rights profile mapped to a BindingService function.

    The Suite asks Telegram only for what the chosen function needs — never a
    blanket "all rights". The ``admin_rights`` list uses Telegram's official
    ``admin=`` vocabulary (space-separated in the link); the ``function`` selects
    which *verified* right the Binding Service requires on the later check.
    """

    key: str
    title_ru: str
    title_en: str
    function: str
    admin_rights: tuple[str, ...]
    description_ru: str
    description_en: str


RIGHTS_PROFILES: tuple[RightsProfile, ...] = (
    RightsProfile(
        key="reactions",
        title_ru="Только реакции",
        title_en="Reactions only",
        function=FUNCTION_REACTIONS,
        admin_rights=("delete_messages",),
        description_ru=(
            "Минимум для автоматических реакций: право удалять сообщения "
            "(Telegram требует его для управления реакциями). Публикация не даётся."
        ),
        description_en=(
            "Minimum for automatic reactions: the right to delete messages "
            "(Telegram requires it to manage reactions). No posting is granted."
        ),
    ),
    RightsProfile(
        key="posting",
        title_ru="Публикация",
        title_en="Publishing",
        function=FUNCTION_POSTING,
        admin_rights=("post_messages", "delete_messages"),
        description_ru=(
            "Публикация контента и управление реакциями: право публиковать и "
            "удалять сообщения."
        ),
        description_en=(
            "Content publishing plus reaction management: the right to post and "
            "delete messages."
        ),
    ),
    RightsProfile(
        key="editing",
        title_ru="Публикация и редактирование",
        title_en="Publishing and editing",
        function=FUNCTION_EDITING,
        admin_rights=("post_messages", "edit_messages", "delete_messages"),
        description_ru=(
            "Публикация, редактирование и удаление сообщений — для сценариев, где "
            "Suite исправляет уже опубликованные посты."
        ),
        description_en=(
            "Posting, editing and deleting messages — for scenarios where the "
            "Suite corrects already-published posts."
        ),
    ),
)

RIGHTS_PROFILES_BY_KEY = {p.key: p for p in RIGHTS_PROFILES}

#: Default profile when none is chosen (least privilege for the common case).
DEFAULT_RIGHTS_PROFILE = "reactions"


def rights_profile(key: str) -> RightsProfile:
    """Return the rights profile for ``key`` (falls back to the default)."""
    return RIGHTS_PROFILES_BY_KEY.get(key or "", RIGHTS_PROFILES_BY_KEY[DEFAULT_RIGHTS_PROFILE])


def channel_start_link(bot_username: str, admin_rights: tuple[str, ...] | list[str]) -> str:
    """Build the official Telegram channel deep link that adds a bot as admin.

    Format (Telegram's own, Bot API 6.0+): ``t.me/<bot>?startchannel&admin=...``
    where ``admin`` is a ``+``-separated list of official admin-right tokens
    (``post_messages``, ``delete_messages``, …). The link only *opens* Telegram's
    confirmation dialog — it can never add the bot silently and never grants a
    right the owner does not confirm.
    """
    username = (bot_username or "").strip().lstrip("@")
    if not username:
        return ""
    rights = "+".join(r for r in admin_rights if r)
    if not rights:
        return f"https://t.me/{username}?startchannel"
    return f"https://t.me/{username}?startchannel&admin={rights}"


class BotOnboardingError(Exception):
    """An onboarding operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class CandidateResult:
    candidate_id: str
    bot_id: str
    bot_username: str
    status: str
    status_label: str
    binding_id: str = ""
    deep_link: str = ""
    error: str = ""


@dataclass(slots=True)
class ProgressResult:
    total: int = 0
    queued: int = 0
    waiting: int = 0
    verifying: int = 0
    ready: int = 0
    needs_permission: int = 0
    failed: int = 0
    skipped: int = 0
    paused: bool = False
    active: int = 0
    done: int = 0

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "total": self.total,
            "queued": self.queued,
            "waiting": self.waiting,
            "verifying": self.verifying,
            "ready": self.ready,
            "needs_permission": self.needs_permission,
            "failed": self.failed,
            "skipped": self.skipped,
            "paused": self.paused,
            "active": self.active,
            "done": self.done,
        }


class BotOnboardingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        binding_service: BindingService | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.batches = OnboardingBatchRepository(session)
        self.candidates = OnboardingCandidateRepository(session)
        self.bots = BotRepository(session)
        self.channels = ChannelRepository(session)
        self.events = EventsService(session)
        self._binding_service = binding_service
        self._provider_factory = provider_factory

    # --- collaborators -------------------------------------------------------
    def _binding(self) -> BindingService:
        if self._binding_service is not None:
            return self._binding_service
        return BindingService(self.session, provider_factory=self._provider_factory)

    def _provider_for(self, bot: Bot) -> TelegramBotProvider:
        if not bot.token_encrypted:
            raise BotOnboardingError(
                "У бота нет сохранённого токена.",
                how_to_fix="Получите токен бота в «Фабрике ботов» или добавьте бота заново.",
            )
        try:
            token = open_secret(bot.token_encrypted, self.settings)
        except ValueError as exc:  # pragma: no cover - defensive
            raise BotOnboardingError(
                "Не удалось прочитать токен бота.",
                how_to_fix="Проверьте, что APP_SECRET_KEY не менялся.",
            ) from exc
        return self._provider_factory(
            token, provider_name=bot.provider_name, settings=self.settings
        )

    # --- creation ------------------------------------------------------------
    async def create_batch(
        self,
        *,
        bot_ids: list[str],
        channel_id: str,
        rights_profile: str = DEFAULT_RIGHTS_PROFILE,
    ) -> OnboardingBatch:
        """Create a queue connecting ``bot_ids`` to ``channel_id``.

        Only ready-to-open bots (username + token) are accepted; the rest are
        reported in ``last_error`` so the owner knows why a bot was skipped. Queue
        creation never contacts Telegram.
        """
        profile = rights_profile_checked(rights_profile)
        channel = await self.channels.get(channel_id)
        if channel is None:
            raise BotOnboardingError("Канал не найден.", status_code=404)

        unique_ids = list(dict.fromkeys(bid for bid in bot_ids if bid))
        if not unique_ids:
            raise BotOnboardingError(
                "Не выбран ни один бот.",
                how_to_fix="Отметьте от 1 до 50 ботов созданных в «Фабрике ботов».",
            )
        if len(unique_ids) > MAX_ONBOARDING_BOTS:
            raise BotOnboardingError(
                f"За один раз можно подключить не более {MAX_ONBOARDING_BOTS} ботов.",
                how_to_fix="Разделите ботов на несколько очередей.",
            )

        batch = OnboardingBatch(
            channel_id=channel_id,
            channel_label=channel.title or channel.reference,
            rights_profile=profile.key,
            function=profile.function,
            requested_count=len(unique_ids),
        )
        await self.batches.add(batch)

        skipped: list[str] = []
        index = 0
        for bot_id in unique_ids:
            bot = await self.bots.get(bot_id)
            if bot is None or not bot.username:
                skipped.append(bot_id)
                continue
            if not bot.token_encrypted:
                skipped.append(bot_id)
                continue
            index += 1
            candidate = OnboardingCandidate(
                batch_id=batch.id,
                index=index,
                bot_id=bot.id,
                telegram_id=bot.telegram_id,
                bot_username=bot.username.lstrip("@"),
                bot_title=bot.title,
                channel_id=channel_id,
                rights_profile=profile.key,
                function=profile.function,
                deep_link=channel_start_link(bot.username, profile.admin_rights),
                status=OnboardingStatus.QUEUED.value,
            )
            await self.candidates.add(candidate)

        batch.requested_count = index
        if skipped:
            batch.last_error = (
                f"Пропущено ботов без имени или токена: {len(skipped)}."
            )
            await self.events.warning(
                MODULE,
                f"Часть ботов не поставлена в очередь подключения: {len(skipped)}.",
                explanation="У этих ботов нет имени пользователя или сохранённого токена.",
                operation="create_batch",
                status="warning",
            )
        if index == 0:
            raise BotOnboardingError(
                "Ни один из выбранных ботов не готов к подключению.",
                how_to_fix="Получите токены ботов в «Фабрике ботов» и попробуйте снова.",
            )
        await self.session.commit()
        return batch

    # --- inventory -----------------------------------------------------------
    async def list_batches(
        self, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[OnboardingBatch], int]:
        return await self.batches.list_all(limit=limit, offset=offset)

    async def get_batch(self, batch_id: str) -> OnboardingBatch:
        batch = await self.batches.get(batch_id)
        if batch is None:
            raise BotOnboardingError("Очередь подключения не найдена.", status_code=404)
        return batch

    async def list_candidates(self, batch_id: str) -> list[OnboardingCandidate]:
        return await self.candidates.list_for_batch(batch_id)

    async def delete_batch(self, batch_id: str) -> None:
        batch = await self.get_batch(batch_id)
        await self.candidates.delete_for_batch(batch_id)
        await self.batches.delete(batch)
        await self.session.commit()

    # --- queue lifecycle -----------------------------------------------------
    async def enqueue(self, batch_id: str) -> OnboardingBatch:
        """(Re)start the queue: revive failed/paused items and unpause."""
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        for row in rows:
            if row.status == OnboardingStatus.FAILED.value:
                row.status = OnboardingStatus.QUEUED.value
                row.last_error = ""
        batch.queue_paused = False
        await self.session.commit()
        return batch

    async def pause(self, batch_id: str) -> OnboardingBatch:
        batch = await self.get_batch(batch_id)
        batch.queue_paused = True
        await self.events.info(
            MODULE,
            "Очередь подключения приостановлена.",
            explanation="Уже подключённые боты сохранены. Очередь можно продолжить.",
            operation="pause",
            status="ok",
        )
        await self.session.commit()
        return batch

    async def resume(self, batch_id: str) -> OnboardingBatch:
        batch = await self.get_batch(batch_id)
        batch.queue_paused = False
        await self.session.commit()
        return batch

    async def skip_candidate(self, candidate_id: str) -> OnboardingCandidate:
        row = await self._get_candidate(candidate_id)
        if row.status == OnboardingStatus.READY.value:
            raise BotOnboardingError(
                "Этот бот уже подключён — пропускать нечего.",
                status_code=409,
            )
        row.status = OnboardingStatus.SKIPPED.value
        row.last_error = ""
        await self._recount(row.batch_id)
        await self.session.commit()
        return row

    async def retry_candidate(self, candidate_id: str) -> OnboardingCandidate:
        row = await self._get_candidate(candidate_id)
        if row.status == OnboardingStatus.READY.value:
            raise BotOnboardingError(
                "Этот бот уже подключён — повтор не нужен.",
                status_code=409,
            )
        row.status = OnboardingStatus.QUEUED.value
        row.last_error = ""
        await self.session.commit()
        return row

    async def verify_candidate(self, candidate_id: str) -> CandidateResult:
        """Re-check one bot's real rights against Telegram and persist the state."""
        row = await self._get_candidate(candidate_id)
        try:
            bot = await self.bots.get(row.bot_id) if row.bot_id else None
            if bot is None or not bot.username:
                raise BotOnboardingError(
                    "Бот для этой очереди не найден.",
                    how_to_fix="Проверьте, что бот ещё есть в разделе «Боты».",
                    status_code=409,
                )
            binding = await self._binding().connect(
                row.bot_id, row.channel_id, function=row.function
            )
            row.binding_id = binding.id
            row.status = OnboardingStatus.VERIFYING.value
            await self.session.commit()
            check = await self._binding().check(binding.id)
        except (BotOnboardingError, BindingServiceError) as exc:
            return await self._mark_failed(row, exc.message, how_to_fix=exc.how_to_fix)
        except TelegramProviderError as exc:  # pragma: no cover - defensive
            return await self._mark_failed(row, exc.message, how_to_fix=exc.how_to_fix)

        await self._apply_check(row, check)
        await self._recount(row.batch_id)
        batch = await self.get_batch(row.batch_id)
        rows = await self.candidates.list_for_batch(row.batch_id)
        await self._settle(batch, rows)
        await self.session.commit()
        return self._result(row)

    # --- durable queue (one op per tick) ------------------------------------
    async def queue_progress(self, batch_id: str) -> ProgressResult:
        counts = await self.candidates.count_by_status(batch_id)
        batch = await self.batches.get(batch_id)
        paused = bool(batch and batch.queue_paused)
        queued = counts.get(OnboardingStatus.QUEUED.value, 0)
        waiting = counts.get(OnboardingStatus.WAITING_CONFIRMATION.value, 0)
        verifying = counts.get(OnboardingStatus.VERIFYING.value, 0)
        ready = counts.get(OnboardingStatus.READY.value, 0)
        needs_permission = counts.get(OnboardingStatus.NEEDS_PERMISSION.value, 0)
        failed = counts.get(OnboardingStatus.FAILED.value, 0)
        skipped = counts.get(OnboardingStatus.SKIPPED.value, 0)
        active = queued + waiting + verifying
        return ProgressResult(
            total=sum(counts.values()),
            queued=queued,
            waiting=waiting,
            verifying=verifying,
            ready=ready,
            needs_permission=needs_permission,
            failed=failed,
            skipped=skipped,
            paused=paused,
            active=active,
            done=ready + skipped,
        )

    async def run_queue_once(self, batch_id: str) -> OnboardingBatch:
        """One bounded pass — the durable job handler body.

        Picks the single oldest active candidate, refreshes its deep link, verifies
        it against Telegram and stops. Exactly one bot per tick keeps a large
        queue from blocking the scheduler and makes a restart resume the queue
        (D-008 style). A paused or drained queue is a no-op. One failure never
        aborts the others: the candidate is marked ``failed`` and the queue moves on.
        """
        batch = await self.get_batch(batch_id)
        if batch.queue_paused:
            return batch
        rows = await self.candidates.list_for_batch(batch_id)
        row = next(
            (r for r in rows if r.status in (
                OnboardingStatus.QUEUED.value,
                OnboardingStatus.WAITING_CONFIRMATION.value,
                OnboardingStatus.VERIFYING.value,
            )),
            None,
        )
        if row is None:
            await self._settle(batch, rows)
            await self.session.commit()
            return batch

        # Refresh the link from the current profile (the bot may have been renamed).
        profile = rights_profile(row.rights_profile)
        if row.bot_username:
            row.deep_link = channel_start_link(row.bot_username, profile.admin_rights)
        row.status = OnboardingStatus.VERIFYING.value
        row.attempts += 1
        await self.session.flush()

        binding = self._binding()
        try:
            bot = await self.bots.get(row.bot_id) if row.bot_id else None
            if bot is None or not bot.username:
                raise BotOnboardingError(
                    "Бот для этой очереди не найден.",
                    how_to_fix="Проверьте, что бот ещё есть в разделе «Боты».",
                    status_code=409,
                )
            link = await binding.connect(row.bot_id, row.channel_id, function=row.function)
            row.binding_id = link.id
            await self.session.flush()
            check = await binding.check(link.id)
            await self._apply_check(row, check)
        except (BotOnboardingError, BindingServiceError) as exc:
            await self._mark_failed(row, exc.message, how_to_fix=exc.how_to_fix)
        except TelegramProviderError as exc:
            await self._mark_failed(row, exc.message, how_to_fix=exc.how_to_fix)
        except Exception as exc:  # pragma: no cover - defensive
            await self._mark_failed(row, str(exc))

        await self._recount(batch_id)
        # Re-read the rows so a queue that drained on this pass is settled and
        # notified immediately, instead of one tick later.
        rows = await self.candidates.list_for_batch(batch_id)
        await self._settle(batch, rows)
        await self.session.commit()
        return batch

    async def recover(self) -> int:
        """Re-hydrate candidates stuck mid-verification after a crash.

        A ``VERIFYING`` row whose process died is put back to ``QUEUED`` so the
        queue resumes instead of hanging (mirrors the bot-creation queue).
        """
        rows = []
        for batch in (await self.batches.list_all(limit=500))[0]:
            rows.extend(await self.candidates.list_for_batch(batch.id))
        revived = 0
        for row in rows:
            if row.status == OnboardingStatus.VERIFYING.value:
                row.status = OnboardingStatus.QUEUED.value
                revived += 1
        if revived:
            await self.session.commit()
        return revived

    # --- completion notification --------------------------------------------
    async def _settle(self, batch: OnboardingBatch, rows: list[OnboardingCandidate]) -> None:
        """Mark a drained queue completed and (once) notify the owner."""
        if not rows or any(r.status in (
            OnboardingStatus.QUEUED.value,
            OnboardingStatus.WAITING_CONFIRMATION.value,
            OnboardingStatus.VERIFYING.value,
        ) for r in rows):
            return
        if batch.completed_at is not None:
            return
        batch.completed_at = utcnow()
        await self.session.flush()
        with contextlib.suppress(Exception):
            await self._notify_complete(batch, rows)

    async def _notify_complete(
        self, batch: OnboardingBatch, rows: list[OnboardingCandidate]
    ) -> None:
        from backend.app.manager.bus import CATEGORY_CHANNELS, Notification

        ready = sum(1 for r in rows if r.status == OnboardingStatus.READY.value)
        failed = sum(1 for r in rows if r.status == OnboardingStatus.FAILED.value)
        await NotificationCenterService(self.session).submit(
            Notification(
                category=CATEGORY_CHANNELS,
                event_key="bot_onboarding.completed",
                message=(
                    f"Очередь подключения ботов к каналу "
                    f"«{batch.channel_label or batch.channel_id}» завершена: "
                    f"готово {ready} из {len(rows)}, с ошибкой {failed}."
                ),
                level="SUCCESS" if not failed else "WARNING",
                how_to_fix=(
                    "" if not failed
                    else "Откройте «Фабрика ботов» → «Подключить к каналу» и повторите неудачные."
                ),
                dedup_key=f"bot_onboarding.completed:{batch.id}",
            )
        )

    # --- helpers -------------------------------------------------------------
    async def _get_candidate(self, candidate_id: str) -> OnboardingCandidate:
        row = await self.candidates.get(candidate_id)
        if row is None:
            raise BotOnboardingError("Бот в очереди не найден.", status_code=404)
        return row

    async def _apply_check(self, row: OnboardingCandidate, check: object) -> None:
        """Map the BindingService result onto the onboarding status.

        The Binding Service already decided, from Telegram's real answer, whether
        the bot is present and whether it holds the required right. We translate
        that one-to-one — no second, parallel interpretation of rights.
        """
        binding = await self._binding().get(row.binding_id)
        if binding is None:
            await self._mark_failed(row, "Подключение не найдено после проверки.")
            return
        status = str(getattr(binding.status, "value", binding.status))
        if status == "ready":
            row.status = OnboardingStatus.READY.value
            row.last_error = ""
        elif status == "needs_permission":
            row.status = OnboardingStatus.NEEDS_PERMISSION.value
            row.last_error = (
                getattr(check, "message", "")
                or "Боту не хватает прав для этой функции."
            )
        elif status == "error":
            row.status = OnboardingStatus.FAILED.value
            row.last_error = getattr(check, "message", "") or "Не удалось проверить подключение."
        else:
            # not_connected / connected: Telegram has not confirmed the bot yet.
            row.status = OnboardingStatus.WAITING_CONFIRMATION.value
            row.last_error = (
                getattr(check, "message", "") or "Бот ещё не добавлен в канал."
            )

    async def _mark_failed(
        self, row: OnboardingCandidate, message: str, *, how_to_fix: str = ""
    ) -> CandidateResult:
        row.status = OnboardingStatus.FAILED.value
        row.last_error = message
        await self._recount(row.batch_id)
        await self.session.commit()
        return self._result(row)

    async def _recount(self, batch_id: str) -> None:
        batch = await self.batches.get(batch_id)
        if batch is None:
            return
        counts = await self.candidates.count_by_status(batch_id)
        batch.ready_count = counts.get(OnboardingStatus.READY.value, 0)
        batch.permission_count = counts.get(OnboardingStatus.NEEDS_PERMISSION.value, 0)
        batch.failed_count = counts.get(OnboardingStatus.FAILED.value, 0)
        batch.skipped_count = counts.get(OnboardingStatus.SKIPPED.value, 0)
        await self.session.flush()

    def _result(self, row: OnboardingCandidate) -> CandidateResult:
        status = row.status_enum()
        return CandidateResult(
            candidate_id=row.id,
            bot_id=row.bot_id,
            bot_username=row.bot_username,
            status=status.value,
            status_label=ONBOARDING_STATUS_TITLES.get(status, status.value),
            binding_id=row.binding_id,
            deep_link=row.deep_link,
            error=row.last_error,
        )

    def result_dict(self, row: OnboardingCandidate) -> dict[str, object]:
        """Public, secret-free view of one candidate's action result."""
        result = self._result(row)
        return {
            "candidate_id": result.candidate_id,
            "bot_id": result.bot_id,
            "bot_username": result.bot_username,
            "status": result.status,
            "status_label": result.status_label,
            "binding_id": result.binding_id,
            "deep_link": result.deep_link,
            "error": result.error,
        }

    # --- serialization -------------------------------------------------------
    def batch_to_dict(self, batch: OnboardingBatch) -> dict[str, object]:
        return {
            "id": batch.id,
            "channel_id": batch.channel_id,
            "channel_label": batch.channel_label,
            "rights_profile": batch.rights_profile,
            "rights_profile_title": rights_profile(batch.rights_profile).title_ru,
            "function": batch.function,
            "requested_count": batch.requested_count,
            "ready_count": batch.ready_count,
            "permission_count": batch.permission_count,
            "failed_count": batch.failed_count,
            "skipped_count": batch.skipped_count,
            "queue_paused": batch.queue_paused,
            "completed": batch.completed_at is not None,
            "last_error": batch.last_error,
        }

    def candidate_to_dict(self, row: OnboardingCandidate) -> dict[str, object]:
        status = row.status_enum()
        return {
            "id": row.id,
            "batch_id": row.batch_id,
            "index": row.index,
            "bot_id": row.bot_id,
            "bot_username": row.bot_username,
            "bot_title": row.bot_title,
            "channel_id": row.channel_id,
            "rights_profile": row.rights_profile,
            "function": row.function,
            "deep_link": row.deep_link,
            "status": status.value,
            "status_label": ONBOARDING_STATUS_TITLES.get(status, status.value),
            "attempts": row.attempts,
            "binding_id": row.binding_id,
            "last_error": row.last_error,
        }

    def dashboard(self, batch: OnboardingBatch, progress: ProgressResult) -> dict[str, object]:
        return {
            "batch_id": batch.id,
            "channel_id": batch.channel_id,
            "channel_label": batch.channel_label,
            "rights_profile": batch.rights_profile,
            "rights_profile_title": rights_profile(batch.rights_profile).title_ru,
            "function": batch.function,
            "queue_paused": batch.queue_paused,
            "completed": batch.completed_at is not None,
            "progress": progress.as_dict(),
        }


def rights_profile_checked(key: str) -> RightsProfile:
    """Validate a profile key (raise a friendly error on an unknown one)."""
    if not key:
        return rights_profile(DEFAULT_RIGHTS_PROFILE)
    if key not in RIGHTS_PROFILES_BY_KEY:
        allowed = ", ".join(p.key for p in RIGHTS_PROFILES)
        raise BotOnboardingError(
            "Неизвестный профиль прав.",
            how_to_fix=f"Доступные профили: {allowed}.",
        )
    return RIGHTS_PROFILES_BY_KEY[key]


__all__ = [
    "BOT_ONBOARDING_JOB_KIND",
    "DEFAULT_RIGHTS_PROFILE",
    "FUNCTION_PERMISSION",
    "RIGHTS_PROFILES",
    "RIGHTS_PROFILES_BY_KEY",
    "BotOnboardingError",
    "BotOnboardingService",
    "CandidateResult",
    "ProgressResult",
    "RightsProfile",
    "channel_start_link",
    "rights_profile",
    "rights_profile_checked",
]
