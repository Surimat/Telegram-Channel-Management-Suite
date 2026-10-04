"""Invite Manager service (PHASE 6).

Turns a filtered audience slice into a controlled, confirmed bulk-invite run.
The pipeline is deliberately conservative:

1. **Preview (dry-run)** — count who would be invited and show the operator the
   mandatory summary (source(s), target, users, accounts, filters, planned
   operations). Nothing runs yet.
2. **Create** — persist a ``DRAFT`` :class:`InviteJob` with a snapshot of the
   filters and one :class:`InviteTask` per target user.
3. **Confirm + start** — only after confirmation does the run begin, as a durable
   queue job the scheduler drives chunk by chunk.

Server limits are respected, never bypassed (D-006): FloodWait pauses the run and
records the wait time, privacy/admin restrictions become per-user statuses, and
``recover()`` pauses a run interrupted by a restart instead of silently
continuing a bulk operation.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.invite import (
    InviteJob,
    InviteJobStatus,
    InviteStatus,
    InviteTask,
)
from backend.app.db.repositories.audience import (
    AudienceSourceRepository,
    AudienceUserRepository,
)
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.invites import (
    InviteJobRepository,
    InviteTaskRepository,
)
from backend.app.providers.errors import (
    AlreadyParticipantError,
    ChatAdminRequiredError,
    FloodWaitError,
    NetworkError,
    PrivacyRestrictedError,
    SessionInvalidError,
    TelegramProviderError,
)
from backend.app.providers.session_base import SessionProvider
from backend.app.services.events_service import EventsService
from backend.app.services.queue_service import QueueService
from backend.app.services.session_service import SessionProviderFactory, SessionService

MODULE = "invites"
INVITE_JOB_KIND = "invite.batch"

# Filter keys accepted from the UI (a subset of the audience filters).
_FILTER_KEYS = (
    "search",
    "source_ids",
    "tag",
    "status",
    "is_bot",
    "is_deleted",
    "has_username",
    "is_premium",
    "telegram_user_id",
    "seen_after",
    "seen_before",
)


class InviteServiceError(Exception):
    """A friendly, user-facing invite error."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


class InviteService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        session_provider_factory: SessionProviderFactory | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.jobs = InviteJobRepository(session)
        self.tasks = InviteTaskRepository(session)
        self.users = AudienceUserRepository(session)
        self.sources = AudienceSourceRepository(session)
        self.queue = QueueService(session)
        self.events = EventsService(session)
        self._session_provider_factory = session_provider_factory

    # ------------------------------------------------------------------
    # Provider / account resolution (same path the Audience Scanner uses)
    # ------------------------------------------------------------------
    def _session_service(self) -> SessionService:
        kwargs: dict[str, Any] = {"settings": self.settings}
        if self._session_provider_factory is not None:
            kwargs["provider_factory"] = self._session_provider_factory
        return SessionService(self.session, **kwargs)

    async def _load_accounts(self, account_ids: list[str]) -> list[Any]:
        service = self._session_service()
        accounts = []
        for account_id in account_ids:
            account = await service.get(account_id)
            if account is None:
                raise InviteServiceError(
                    f"Аккаунт не найден: {account_id}.",
                    how_to_fix="Обновите список аккаунтов и выберите доступный.",
                    status_code=404,
                )
            accounts.append(account)
        if not accounts:
            for candidate in await service.list_accounts(enabled=True):
                if candidate.status.value == "online":
                    accounts.append(candidate)
        if not accounts:
            raise InviteServiceError(
                "Нет доступного Telegram-аккаунта для приглашений.",
                how_to_fix=(
                    "Добавьте аккаунт в разделе «Аккаунты» и проверьте, "
                    "что он в статусе «онлайн»."
                ),
            )
        return accounts

    def _provider_for(self, account: Any) -> SessionProvider:
        service = self._session_service()
        return service.provider_for(account)

    # ------------------------------------------------------------------
    # Filters / planning
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_filters(raw: dict[str, Any] | None) -> dict[str, Any]:
        raw = raw or {}
        filters: dict[str, Any] = {}
        for key in _FILTER_KEYS:
            if key in raw and raw[key] not in (None, "", []):
                filters[key] = raw[key]
        return filters

    async def _filtered_users(
        self, filters: dict[str, Any], *, limit: int, offset: int = 0
    ) -> tuple[list[Any], int]:
        return await self.users.list(
            search=str(filters.get("search", "")),
            source_ids=list(filters.get("source_ids") or []) or None,
            tag=filters.get("tag"),
            status=filters.get("status"),
            is_bot=filters.get("is_bot"),
            is_deleted=filters.get("is_deleted"),
            has_username=filters.get("has_username"),
            is_premium=filters.get("is_premium"),
            telegram_user_id=filters.get("telegram_user_id"),
            sort="last_seen",
            order="desc",
            limit=limit,
            offset=offset,
        )

    async def preview(
        self,
        *,
        target: str = "",
        channel_id: str = "",
        account_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        max_total: int = 0,
        sample_limit: int = 10,
    ) -> dict[str, Any]:
        """Dry-run: count the audience slice and describe the planned run."""
        if channel_id:
            channel = await ChannelRepository(self.session).get(channel_id)
            if channel is None:
                raise InviteServiceError(
                    "Выбранный канал не найден.",
                    how_to_fix="Обновите список каналов на странице «Каналы».",
                    status_code=404,
                )
            target = channel.reference
        if not (target or "").strip():
            raise InviteServiceError(
                "Не указан целевой канал.",
                how_to_fix="Выберите канал из списка или укажите его вручную.",
            )
        merged = self._coerce_filters(filters)
        if source_ids:
            merged["source_ids"] = list(source_ids)
        users, total = await self._filtered_users(merged, limit=sample_limit)
        planned = total if max_total <= 0 else min(total, max_total)
        accounts = await self._load_accounts(list(account_ids or []))

        source_labels = []
        for sid in merged.get("source_ids") or []:
            source = await self.sources.get(sid)
            if source is not None:
                source_labels.append(source.title or source.username or source.reference)

        return {
            "target": target,
            "source_ids": list(merged.get("source_ids") or []),
            "source_labels": source_labels,
            "account_ids": [a.id for a in accounts],
            "account_labels": [a.username or a.display_name or a.id for a in accounts],
            "filters": {k: v for k, v in merged.items() if k != "source_ids"},
            "total_candidates": total,
            "planned_operations": planned,
            "accounts_count": len(accounts),
            "max_total": max_total,
            "sample": [
                {
                    "id": u.id,
                    "telegram_user_id": u.telegram_user_id,
                    "username": u.username,
                    "display_name": u.display_name,
                }
                for u in users
            ],
            "explanation": self._preview_explanation(total, planned, len(accounts)),
            "requires_confirmation": True,
        }

    @staticmethod
    def _preview_explanation(total: int, planned: int, accounts: int) -> str:
        if total == 0:
            return (
                "По выбранным фильтрам не найдено ни одного пользователя. "
                "Измените фильтры или сначала просканируйте источники."
            )
        return (
            f"Будет приглашено до {planned} пользователей с {accounts} аккаунт(ов). "
            "Telegram может ограничить частоту — система остановит очередь и покажет "
            "время ожидания, обходить ограничения нельзя."
        )

    # ------------------------------------------------------------------
    # Create (draft) + confirm + start
    # ------------------------------------------------------------------
    async def create_job(
        self,
        *,
        name: str = "",
        target: str = "",
        channel_id: str = "",
        account_ids: list[str] | None = None,
        source_ids: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        dry_run: bool = False,
        per_account_delay_min: float | None = None,
        per_account_delay_max: float | None = None,
        max_per_account: int | None = None,
        max_total: int | None = None,
    ) -> InviteJob:
        # A channel chosen from the shared registry supplies the target and its
        # display title, so the owner does not retype it (decision D-051).
        channel_ref = ""
        channel_title = ""
        if channel_id:
            channel = await ChannelRepository(self.session).get(channel_id)
            if channel is None:
                raise InviteServiceError(
                    "Выбранный канал не найден.",
                    how_to_fix="Обновите список каналов на странице «Каналы».",
                    status_code=404,
                )
            channel_ref = channel.reference
            channel_title = channel.title or channel.reference
            target = channel_ref

        if not (target or "").strip():
            raise InviteServiceError(
                "Не указан целевой канал.",
                how_to_fix="Выберите канал из списка или укажите его вручную.",
            )
        merged = self._coerce_filters(filters)
        if source_ids:
            merged["source_ids"] = list(source_ids)
        accounts = await self._load_accounts(list(account_ids or []))

        delay_min = (
            per_account_delay_min
            if per_account_delay_min is not None
            else self.settings.invite_delay_min
        )
        delay_max = (
            per_account_delay_max
            if per_account_delay_max is not None
            else self.settings.invite_delay_max
        )
        if delay_max < delay_min:
            delay_min, delay_max = delay_max, delay_min

        cap = max_total if max_total is not None else self.settings.invite_max_total
        per_acct = (
            max_per_account
            if max_per_account is not None
            else self.settings.invite_max_per_account
        )

        users, _total = await self._filtered_users(
            merged, limit=(cap if cap > 0 else 100000)
        )

        job = InviteJob(
            name=name or f"Приглашение в {target}",
            target=target,
            target_title=channel_title or target,
            channel_id=channel_id or "",
            account_ids=json.dumps([a.id for a in accounts]),
            source_ids=json.dumps(list(merged.get("source_ids") or [])),
            filters=json.dumps({k: v for k, v in merged.items() if k != "source_ids"}),
            status=InviteJobStatus.DRAFT,
            dry_run=dry_run,
            per_account_delay_min=float(delay_min),
            per_account_delay_max=float(delay_max),
            max_per_account=int(per_acct),
            max_total=int(cap),
            total_tasks=len(users),
        )
        await self.jobs.add(job)

        await self._plan_tasks(job, users, accounts, start_at=utcnow())
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Создано задание приглашения «{job.name}» на {len(users)} пользователей.",
            operation="create_job",
            status="ok",
        )
        return job

    async def _plan_tasks(
        self,
        job: InviteJob,
        users: list[Any],
        accounts: list[Any],
        *,
        start_at: datetime,
    ) -> None:
        """Assign each user an account (round-robin) and a spaced-out time."""
        existing, _ = await self.tasks.list_for_job(job.id, limit=1)
        if existing:
            return
        account_cycle: list[Any] = []
        if job.max_per_account and job.max_per_account > 0:
            for account in accounts:
                account_cycle.extend([account] * job.max_per_account)
        if not account_cycle:
            account_cycle = list(accounts)

        # Next due time per account so several accounts work in parallel while a
        # single account still waits between invites (configurable, randomized).
        next_due: dict[str, datetime] = {a.id: start_at for a in accounts}
        tasks: list[InviteTask] = []
        for index, user in enumerate(users):
            account = account_cycle[index % len(account_cycle)]
            due = next_due.get(account.id, start_at)
            tasks.append(
                InviteTask(
                    job_id=job.id,
                    user_id=user.id,
                    telegram_user_id=user.telegram_user_id,
                    account_id=account.id,
                    status=InviteStatus.PENDING,
                    scheduled_at=due,
                )
            )
            gap = random.uniform(job.per_account_delay_min, job.per_account_delay_max)
            next_due[account.id] = due + timedelta(seconds=gap)
        await self.tasks.add_many(tasks)
        job.total_tasks = len(tasks)
        await self.session.flush()

    async def confirm_and_start(self, job_id: str) -> InviteJob:
        """Record the operator's confirmation and enqueue the run."""
        job = await self._require_job(job_id)
        if job.status not in {InviteJobStatus.DRAFT, InviteJobStatus.READY}:
            raise InviteServiceError(
                "Это задание нельзя запустить в текущем состоянии.",
                how_to_fix="Создайте новое задание или продолжите существующее.",
            )
        job.confirmed_at = utcnow()
        job.confirmed_summary = json.dumps(
            {"total_tasks": job.total_tasks, "target": job.target}
        )
        job.status = InviteJobStatus.READY
        await self.session.flush()
        return await self.start_job(job_id)

    async def start_job(self, job_id: str) -> InviteJob:
        job = await self._require_job(job_id)
        if job.confirmed_at is None:
            raise InviteServiceError(
                "Задание не подтверждено.",
                how_to_fix="Сначала подтвердите суммарную сводку перед запуском.",
            )
        job.status = InviteJobStatus.RUNNING
        job.started_at = job.started_at or utcnow()
        job.finished_at = None
        queue_job = await self.queue.enqueue(
            kind=INVITE_JOB_KIND,
            payload={"invite_job_id": job.id},
            group_key=job.id,
            max_attempts=1,
        )
        job.queue_job_id = queue_job.id
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Запущено приглашение «{job.name}».",
            operation="start",
            status="ok",
        )
        return job

    async def pause_job(self, job_id: str) -> InviteJob:
        job = await self._require_job(job_id)
        job.status = InviteJobStatus.PAUSED
        await self.session.flush()
        return job

    async def resume_job(self, job_id: str) -> InviteJob:
        job = await self._require_job(job_id)
        if job.status != InviteJobStatus.PAUSED:
            raise InviteServiceError(
                "Задание не на паузе.",
                how_to_fix="Поставьте задание на паузу, чтобы затем продолжить.",
            )
        return await self.start_job(job_id)

    async def stop_job(self, job_id: str) -> InviteJob:
        job = await self._require_job(job_id)
        job.status = InviteJobStatus.STOPPED
        job.finished_at = utcnow()
        await self.session.flush()
        return job

    async def retry_failed(self, job_id: str) -> InviteJob:
        """Re-queue failed / flood-wait tasks (technically safe to retry)."""
        job = await self._require_job(job_id)
        reset = await self.tasks.retry_failed(job_id)
        await self.session.flush()
        if reset and job.status in {InviteJobStatus.COMPLETED, InviteJobStatus.STOPPED}:
            await self.start_job(job_id)
        await self.events.info(
            MODULE,
            f"Повтор приглашений: сброшено {reset} заданий.",
            operation="retry",
            status="ok",
        )
        return job

    async def _require_job(self, job_id: str) -> InviteJob:
        job = await self.jobs.get(job_id)
        if job is None:
            raise InviteServiceError("Задание приглашения не найдено.", status_code=404)
        return job

    # ------------------------------------------------------------------
    # Execution (durable; one bounded batch per scheduler tick)
    # ------------------------------------------------------------------
    async def run_tick(self, job_id: str) -> tuple[str, float]:
        """Execute one bounded batch for ``job_id``.

        Returns ``(action, next_delay_seconds)`` where action is one of:

        * ``"done"``   — the run finished (or is no longer runnable);
        * ``"paused"`` — a FloodWait paused it (do not re-schedule);
        * ``"more"``   — work remains; re-schedule after ``next_delay_seconds``.

        Committing after every batch keeps progress restart-safe (D-008).
        """
        job = await self.jobs.get(job_id)
        if job is None or job.status != InviteJobStatus.RUNNING:
            return "done", 0.0

        size = self.settings.invite_batch_size
        now = utcnow()
        claimed = await self.tasks.claim_batch(job.id, limit=size, now=now)
        if not claimed:
            pending = await self.tasks.pending_count(job.id)
            if pending == 0:
                await self._finish_job(job)
                await self.session.commit()
                return "done", 0.0
            # Nothing is due yet: wait until the next scheduled task.
            delay = await self._seconds_until_next_due(job.id, now)
            await self.session.commit()
            return "more", delay

        accounts = await self._load_accounts(json.loads(job.account_ids or "[]"))
        providers: dict[str, SessionProvider] = {}
        paused_for_flood = False

        for task in claimed:
            if paused_for_flood:
                # Unrun claims go back to pending; they retry after the wait.
                task.status = InviteStatus.PENDING
                continue
            account = next((a for a in accounts if a.id == task.account_id), None)
            if account is None:
                task.status = InviteStatus.FAILED
                task.error = "Аккаунт недоступен."
                task.completed_at = utcnow()
                continue
            provider = providers.get(account.id)
            if provider is None:
                provider = self._provider_for(account)
                providers[account.id] = provider
            outcome = await self._execute_task(job, task, provider)
            if outcome == "flood":
                paused_for_flood = True

        await self._refresh_counters(job)
        pending = await self.tasks.pending_count(job.id)
        if paused_for_flood:
            await self.session.commit()
            return "paused", 0.0
        if pending == 0:
            await self._finish_job(job)
            await self.session.commit()
            return "done", 0.0
        delay = await self._seconds_until_next_due(job.id, utcnow())
        await self.session.commit()
        return "more", delay

    async def _seconds_until_next_due(self, job_id: str, now: datetime) -> float:
        nxt = await self.tasks.next_due(job_id, now=now)
        if nxt is None or nxt.scheduled_at is None:
            return 1.0
        delta = (nxt.scheduled_at - now).total_seconds()
        return max(1.0, min(delta, 3600.0))

    async def run_batch(self, *, batch_size: int | None = None) -> None:
        """Execute one batch for the first due running job (manual/test helper)."""
        rows, _ = await self.jobs.list(status=InviteJobStatus.RUNNING, limit=1)
        if not rows:
            return
        await self.run_tick(rows[0].id)

    async def _execute_task(
        self, job: InviteJob, task: InviteTask, provider: SessionProvider
    ) -> str:
        task.attempts += 1
        try:
            if job.dry_run:
                task.status = InviteStatus.INVITED
                task.completed_at = utcnow()
                return "invited"
            await provider.invite_to_channel(job.target, task.telegram_user_id)
            task.status = InviteStatus.INVITED
            task.completed_at = utcnow()
            task.error = ""
            return "invited"
        except AlreadyParticipantError:
            task.status = InviteStatus.ALREADY_MEMBER
            task.completed_at = utcnow()
            return "already"
        except PrivacyRestrictedError as exc:
            task.status = InviteStatus.PRIVACY
            task.error = exc.message
            task.completed_at = utcnow()
            return "privacy"
        except ChatAdminRequiredError as exc:
            task.status = InviteStatus.ADMIN_REQUIRED
            task.error = exc.message
            task.completed_at = utcnow()
            return "admin"
        except FloodWaitError as exc:
            wait = exc.retry_after or 0
            task.status = InviteStatus.FLOOD_WAIT
            task.error = exc.message
            task.wait_until = utcnow() + timedelta(seconds=wait)
            # Pause the whole run and surface the wait time (D-006).
            job.status = InviteJobStatus.PAUSED
            job.waiting_account_id = task.account_id
            job.wait_until = task.wait_until
            job.last_error = exc.message
            await self.events.error(
                MODULE,
                f"Приглашения приостановлены: {exc.message}",
                how_to_fix=exc.how_to_fix,
                operation="invite",
                status="flood_wait",
            )
            await self.session.flush()
            return "flood"
        except SessionInvalidError as exc:
            task.status = InviteStatus.FAILED
            task.error = exc.message
            task.completed_at = utcnow()
            return "session_invalid"
        except NetworkError as exc:
            # Transient: keep pending so it is retried on the next tick.
            task.status = InviteStatus.PENDING
            task.error = exc.message
            return "network"
        except TelegramProviderError as exc:
            task.status = InviteStatus.FAILED
            task.error = exc.message
            task.completed_at = utcnow()
            return "failed"

    async def _refresh_counters(self, job: InviteJob) -> None:
        counts = await self.tasks.status_counts(job.id)
        job.invited_count = counts.get(InviteStatus.INVITED.value, 0)
        job.already_count = counts.get(InviteStatus.ALREADY_MEMBER.value, 0)
        job.privacy_count = counts.get(InviteStatus.PRIVACY.value, 0)
        job.flood_count = counts.get(InviteStatus.FLOOD_WAIT.value, 0)
        job.error_count = counts.get(InviteStatus.FAILED.value, 0) + counts.get(
            InviteStatus.ADMIN_REQUIRED.value, 0
        )
        job.processed_count = (
            job.invited_count + job.already_count + job.privacy_count
        )
        await self.session.flush()

    async def _finish_job(self, job: InviteJob) -> None:
        job.status = InviteJobStatus.COMPLETED
        job.finished_at = utcnow()
        await self.session.flush()
        await self.events.info(
            MODULE,
            (
                f"Приглашение «{job.name}» завершено: приглашено {job.invited_count}, "
                f"уже были {job.already_count}, ограничения {job.privacy_count}, "
                f"ошибок {job.error_count}."
            ),
            operation="finish",
            status="ok",
        )

    # ------------------------------------------------------------------
    # Recovery after restart
    # ------------------------------------------------------------------
    async def recover(self) -> int:
        """Pause runs interrupted by a restart so a bulk action never resumes
        silently. The operator resumes explicitly, or retries failed tasks."""
        # Tasks claimed mid-batch by the crashed process must return to the
        # pending pool, or an explicit resume would leave them stuck forever.
        await self.tasks.recover_stuck_running()
        active = await self.jobs.active()
        for job in active:
            job.status = InviteJobStatus.PAUSED
        if active:
            await self.session.flush()
        return len(active)

    async def summary(self) -> dict[str, Any]:
        counts = await self.jobs.count_by_status()
        return {"by_status": counts}

    def explain_job(self, job: InviteJob) -> str:
        """Plain-language "what happened" for the UI."""
        if job.status == InviteJobStatus.PAUSED and job.wait_until is not None:
            return (
                "Приглашения приостановлены: Telegram попросил подождать. "
                f"Возобновить можно после {_iso(job.wait_until)}."
            )
        if job.status == InviteJobStatus.RUNNING:
            return (
                f"Идёт приглашение: обработано {job.processed_count} из "
                f"{job.total_tasks}."
            )
        if job.status == InviteJobStatus.COMPLETED:
            return (
                f"Завершено: приглашено {job.invited_count}, уже состояли "
                f"{job.already_count}, недоступны по приватности {job.privacy_count}."
            )
        if job.status == InviteJobStatus.STOPPED:
            return "Задание остановлено пользователем."
        if job.status == InviteJobStatus.FAILED:
            return "Задание завершилось с ошибкой."
        return "Задание создано и ожидает подтверждения."


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


__all__ = ["INVITE_JOB_KIND", "MODULE", "InviteService", "InviteServiceError"]
