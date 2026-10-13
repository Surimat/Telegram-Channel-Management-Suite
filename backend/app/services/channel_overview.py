"""Unified channel state overview (D-127).

Answers one question for the owner: *what is the real state of this channel
right now?* — per channel, in one place, in plain language.

It is **read-only aggregation** over data that already exists: the Channel
Registry, bot↔channel bindings, audience sources, invite jobs, the Bot Factory
and onboarding queues, the content pipeline, the durable job queue and the
channel event log. It stores nothing and changes nothing, so it can never drift
from the modules it summarises.

The per-channel *attention* level is derived deterministically (``ok < info <
warning < error``): each section contributes its own level, the channel takes the
worst one, and the reason lists the sections at that level. Nothing is guessed —
an empty install reports ``info`` ("nothing configured yet"), never ``error``.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.audience import AudienceSource, ScanStatus
from backend.app.db.models.binding import BotChannelBinding
from backend.app.db.models.bot import Bot
from backend.app.db.models.bot_factory import BotBatch, BotCandidate, QueueState
from backend.app.db.models.bot_onboarding import OnboardingBatch
from backend.app.db.models.channel import Channel, ChannelStatus
from backend.app.db.models.content import ContentItem, ContentSource, Publication
from backend.app.db.models.content_ops import (
    AI_STATUS_ERROR,
    AI_STATUS_UNAVAILABLE,
    ContentOperation,
)
from backend.app.db.models.event import Event, EventLevel
from backend.app.db.models.invite import InviteJob, InviteJobStatus
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.models.post import Post
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.services.channel_modules import (
    MODULE_TITLES,
    effective_modules,
    parse_modules,
)

# Attention levels, worst-last.
ATTENTION_OK = "ok"
ATTENTION_INFO = "info"
ATTENTION_WARNING = "warning"
ATTENTION_ERROR = "error"

_ATTENTION_ORDER = {
    ATTENTION_OK: 0,
    ATTENTION_INFO: 1,
    ATTENTION_WARNING: 2,
    ATTENTION_ERROR: 3,
}

ATTENTION_LABELS = {
    ATTENTION_OK: "Всё в порядке",
    ATTENTION_INFO: "Есть что посмотреть",
    ATTENTION_WARNING: "Требуется внимание",
    ATTENTION_ERROR: "Есть проблемы",
}

#: Invite states that mean "a run is still in progress".
_ACTIVE_INVITE_STATUSES = {
    InviteJobStatus.READY,
    InviteJobStatus.RUNNING,
    InviteJobStatus.PAUSED,
}

#: Durable-queue states that mean "work is still waiting or running".
_ACTIVE_JOB_STATUSES = {
    JobStatus.PENDING,
    JobStatus.SCHEDULED,
    JobStatus.RUNNING,
}

#: Bot-Factory candidate queue states that still need processing.
_PENDING_FACTORY_STATES = {
    QueueState.PENDING,
    QueueState.QUEUED,
    QueueState.RUNNING,
}

_MODULE_ORDER = ("reactions", "audience", "invites", "analytics")


def _label(channel: Channel) -> str:
    """A non-secret, display-safe channel label."""
    return channel.title or channel.username or channel.reference or channel.id


def _attention(level: str, reason: str = "") -> dict[str, str]:
    return {"level": level, "label": ATTENTION_LABELS[level], "reason": reason}


def _worst(levels: list[str]) -> str:
    if not levels:
        return ATTENTION_OK
    return max(levels, key=lambda level: _ATTENTION_ORDER.get(level, 0))


def _section(
    status: str,
    label: str,
    counts: dict[str, int] | None = None,
    items: list[str] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "label": label,
        "counts": {k: int(v) for k, v in (counts or {}).items()},
        "items": list(items or []),
    }


def _new_channel_bucket() -> dict[str, object]:
    # A module with no data is not a reason to flag a channel: only real signals
    # (a failed publication, a permission gap, …) raise the attention level.
    return {
        "bindings": _section(ATTENTION_OK, "Нет данных."),
        "audience": _section(ATTENTION_OK, "Нет данных."),
        "invites": _section(ATTENTION_OK, "Нет данных."),
        "bots": _section(ATTENTION_OK, "Нет данных."),
        "content": _section(ATTENTION_OK, "Нет данных."),
        "pipeline": _section(ATTENTION_OK, "Нет данных."),
        "queue": _section(ATTENTION_OK, "Очередь пуста."),
    }


class ChannelOverviewService:
    """Read-only aggregation of one channel's state across every module."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.channels = ChannelRepository(session)

    async def build(self) -> dict[str, object]:
        channels, _total = await self.channels.list(limit=500)
        generated_at = utcnow()
        events = await self._events_section()

        if not channels:
            return {
                "generated_at": generated_at,
                "totals": {
                    "channels": 0,
                    "ok": 0,
                    "info": 0,
                    "warning": 0,
                    "error": 0,
                    "needs_attention": 0,
                },
                "attention": _attention(
                    ATTENTION_OK, "Каналы ещё не добавлены — добавьте первый в разделе «Каналы»."
                ),
                "events": events,
                "channels": [],
            }

        ids = [c.id for c in channels]
        buckets, job_keys = await self._aggregate(ids)
        queue_sections = await self._queue_sections(ids, job_keys)

        items: list[dict[str, object]] = []
        for channel in channels:
            bucket = buckets.get(channel.id) or _new_channel_bucket()
            bucket["queue"] = queue_sections.get(
                channel.id, _section(ATTENTION_OK, "Очередь пуста.")
            )
            items.append(self._channel_item(channel, bucket))

        levels = [str(item["attention"]["level"]) for item in items]  # type: ignore[index]
        # The events journal is part of the overall picture but not a channel.
        overall_levels = list(levels)
        if events["status"] == ATTENTION_ERROR:
            overall_levels.append(ATTENTION_ERROR)
        overall = _worst(overall_levels)
        totals = {
            "channels": len(items),
            "ok": sum(1 for level in levels if level == ATTENTION_OK),
            "info": sum(1 for level in levels if level == ATTENTION_INFO),
            "warning": sum(1 for level in levels if level == ATTENTION_WARNING),
            "error": sum(1 for level in levels if level == ATTENTION_ERROR),
            "needs_attention": sum(
                1 for level in levels if level in {ATTENTION_WARNING, ATTENTION_ERROR}
            ),
        }
        return {
            "generated_at": generated_at,
            "totals": totals,
            "attention": _attention(overall, self._overall_reason(items, events, overall)),
            "events": events,
            "channels": items,
        }

    # --- per-channel assembly -------------------------------------------------
    def _channel_item(self, channel: Channel, bucket: dict[str, object]) -> dict[str, object]:
        modules = [
            {
                "id": module_id,
                "title": MODULE_TITLES.get(module_id, module_id),
                "enabled": enabled,
            }
            for module_id, enabled in self._modules(channel).items()
        ]
        attention = self._channel_attention(channel, modules, bucket)
        return {
            "id": channel.id,
            "title": channel.title,
            "username": channel.username,
            "reference": channel.reference,
            "kind": str(channel.kind),
            "status": str(channel.status),
            "is_default": channel.is_default,
            "attention": attention,
            "modules": modules,
            "bindings": bucket["bindings"],
            "audience": bucket["audience"],
            "invites": bucket["invites"],
            "bots": bucket["bots"],
            "content": bucket["content"],
            "pipeline": bucket["pipeline"],
            "queue": bucket["queue"],
        }

    def _modules(self, channel: Channel) -> dict[str, bool]:
        parsed = effective_modules(_parse_modules(channel.modules))
        return {module_id: bool(parsed.get(module_id, True)) for module_id in _MODULE_ORDER}

    def _channel_attention(
        self,
        channel: Channel,
        modules: list[dict[str, object]],
        bucket: dict[str, object],
    ) -> dict[str, str]:
        reasons: list[tuple[str, str]] = []
        if channel.status == ChannelStatus.ERROR:
            reasons.append((ATTENTION_ERROR, "Проверка канала завершилась ошибкой."))
        elif channel.status == ChannelStatus.WARNING:
            reasons.append((ATTENTION_WARNING, "Канал доступен с ограничениями."))
        elif channel.status == ChannelStatus.NEW:
            reasons.append((ATTENTION_INFO, "Канал ещё не проверен."))

        for name in ("bindings", "audience", "invites", "bots", "content", "pipeline", "queue"):
            section = bucket.get(name)
            if not isinstance(section, dict):
                continue
            level = str(section.get("status", ATTENTION_INFO))
            if level in {ATTENTION_ERROR, ATTENTION_WARNING, ATTENTION_INFO}:
                reasons.append((level, str(section.get("label", ""))))

        disabled = [str(m["title"]) for m in modules if not m["enabled"]]
        if disabled:
            reasons.append((ATTENTION_INFO, "Отключены модули: " + ", ".join(disabled) + "."))

        if not reasons:
            return _attention(ATTENTION_OK, "Все проверенные разделы в порядке.")
        level = _worst([r[0] for r in reasons])
        at_level = [reason for reason_level, reason in reasons if reason_level == level and reason]
        return _attention(level, " ".join(at_level[:3]))

    def _overall_reason(
        self, items: list[dict[str, object]], events: dict[str, object], level: str
    ) -> str:
        if level == ATTENTION_OK:
            return "Все каналы в порядке."
        labels = [
            _channel_label(item)
            for item in items
            if str(item["attention"]["level"]) == level  # type: ignore[index]
        ]
        if events["status"] == ATTENTION_ERROR and level == ATTENTION_ERROR:
            labels.append("журнал каналов")
        return "Обратите внимание: " + ", ".join(labels[:5]) + "."

    # --- aggregation ----------------------------------------------------------
    async def _aggregate(
        self, ids: list[str]
    ) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
        buckets: dict[str, dict[str, object]] = {
            channel_id: _new_channel_bucket() for channel_id in ids
        }
        job_keys: dict[str, str] = {}

        for channel_id, section in (await self._bindings(ids)).items():
            buckets.setdefault(channel_id, _new_channel_bucket())["bindings"] = section
        audience_buckets, audience_keys = await self._audience(ids)
        for channel_id, section in audience_buckets.items():
            buckets[channel_id]["audience"] = section
        job_keys.update(audience_keys)

        invite_buckets, invite_keys = await self._invites(ids)
        for channel_id, section in invite_buckets.items():
            buckets[channel_id]["invites"] = section
        job_keys.update(invite_keys)

        bot_buckets, factory_keys = await self._bots(ids)
        for channel_id, section in bot_buckets.items():
            buckets[channel_id]["bots"] = section
        job_keys.update(factory_keys)

        content_buckets = await self._content(ids)
        for channel_id, section in content_buckets.items():
            buckets[channel_id]["content"] = section

        pipeline_buckets = await self._pipeline(ids)
        for channel_id, section in pipeline_buckets.items():
            buckets[channel_id]["pipeline"] = section

        post_keys = await self._post_keys(ids)
        job_keys.update(post_keys)
        return buckets, job_keys

    async def _bindings(self, ids: list[str]) -> dict[str, dict[str, object]]:
        rows = (
            await self.session.execute(
                select(
                    BotChannelBinding.channel_id,
                    BotChannelBinding.bot_id,
                    BotChannelBinding.status,
                ).where(BotChannelBinding.channel_id.in_(ids))
            )
        ).all()
        bot_labels = await self._bot_labels({bot_id for _, bot_id, _ in rows})
        per_channel: dict[str, dict[str, int]] = {}
        bots: dict[str, list[str]] = {}
        for channel_id, bot_id, status in rows:
            counts = per_channel.setdefault(
                channel_id,
                {"total": 0, "ready": 0, "needs_permission": 0, "not_connected": 0, "error": 0},
            )
            counts["total"] += 1
            key = str(status)
            if key in counts:
                counts[key] += 1
            label = bot_labels.get(bot_id)
            if label:
                bots.setdefault(channel_id, []).append(label)

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in per_channel.items():
            if counts["error"]:
                status = ATTENTION_ERROR
                label = f"Боты с ошибкой подключения: {counts['error']}."
            elif counts["needs_permission"]:
                status = ATTENTION_WARNING
                label = f"Ботам не хватает прав: {counts['needs_permission']}."
            elif counts["ready"]:
                status = ATTENTION_OK
                label = f"Готовые боты: {counts['ready']}."
            else:
                status = ATTENTION_INFO
                label = "Бот подключён, права ещё не проверены."
            sections[channel_id] = _section(
                status, label, counts, sorted(bots.get(channel_id, []))
            )
        return sections

    async def _bot_labels(self, bot_ids: set[str]) -> dict[str, str]:
        if not bot_ids:
            return {}
        rows = (
            await self.session.execute(
                select(Bot.id, Bot.username, Bot.title).where(Bot.id.in_(list(bot_ids)))
            )
        ).all()
        labels: dict[str, str] = {}
        for bot_id, username, title in rows:
            labels[bot_id] = f"@{username}" if username else (title or bot_id)
        return labels

    async def _audience(
        self, ids: list[str]
    ) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
        rows = (
            await self.session.execute(
                select(
                    AudienceSource.id,
                    AudienceSource.channel_id,
                    AudienceSource.scan_status,
                ).where(AudienceSource.channel_id.in_(ids))
            )
        ).all()
        per_channel: dict[str, dict[str, int]] = {}
        job_keys: dict[str, str] = {}
        for source_id, channel_id, scan_status in rows:
            job_keys[source_id] = channel_id
            counts = per_channel.setdefault(channel_id, {"sources": 0, "scanning": 0, "failed": 0})
            counts["sources"] += 1
            if scan_status == ScanStatus.SCANNING:
                counts["scanning"] += 1
            elif scan_status == ScanStatus.FAILED:
                counts["failed"] += 1

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in per_channel.items():
            if counts["failed"]:
                status = ATTENTION_WARNING
                label = f"Сканирование аудитории с ошибкой: {counts['failed']}."
            elif counts["scanning"]:
                status = ATTENTION_INFO
                label = "Идёт сканирование аудитории."
            else:
                status = ATTENTION_OK
                label = f"Источники аудитории в порядке: {counts['sources']}."
            sections[channel_id] = _section(status, label, counts)
        return sections, job_keys

    async def _invites(
        self, ids: list[str]
    ) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
        rows = (
            await self.session.execute(
                select(InviteJob.id, InviteJob.channel_id, InviteJob.status).where(
                    InviteJob.channel_id.in_(ids)
                )
            )
        ).all()
        per_channel: dict[str, dict[str, int]] = {}
        job_keys: dict[str, str] = {}
        for job_id, channel_id, status in rows:
            job_keys[job_id] = channel_id
            counts = per_channel.setdefault(channel_id, {"total": 0, "active": 0, "failed": 0})
            counts["total"] += 1
            if status in _ACTIVE_INVITE_STATUSES:
                counts["active"] += 1
            elif status == InviteJobStatus.FAILED:
                counts["failed"] += 1

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in per_channel.items():
            if counts["failed"]:
                status = ATTENTION_WARNING
                label = f"Приглашения с ошибкой: {counts['failed']}."
            elif counts["active"]:
                status = ATTENTION_INFO
                label = f"Активные приглашения: {counts['active']}."
            else:
                status = ATTENTION_OK
                label = f"Приглашения: {counts['total']} запусков."
            sections[channel_id] = _section(status, label, counts)
        return sections, job_keys

    async def _bots(
        self, ids: list[str]
    ) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
        counts_by_channel: dict[str, dict[str, int]] = {}
        job_keys: dict[str, str] = {}

        factory_rows = (
            await self.session.execute(
                select(
                    BotBatch.id,
                    BotBatch.channel_id,
                    BotBatch.created_count,
                    BotBatch.failed_count,
                ).where(BotBatch.channel_id.in_(ids))
            )
        ).all()
        for batch_id, channel_id, created, failed in factory_rows:
            job_keys[batch_id] = channel_id
            counts = counts_by_channel.setdefault(channel_id, self._empty_bot_counts())
            counts["factory_batches"] += 1
            counts["factory_created"] += int(created or 0)
            counts["factory_failed"] += int(failed or 0)

        pending_states = [state.value for state in _PENDING_FACTORY_STATES]
        pending_rows = (
            await self.session.execute(
                select(BotBatch.channel_id, func.count())
                .join(BotCandidate, BotCandidate.batch_id == BotBatch.id)
                .where(
                    BotBatch.channel_id.in_(ids),
                    BotCandidate.queue_state.in_(pending_states),
                )
                .group_by(BotBatch.channel_id)
            )
        ).all()
        for channel_id, pending in pending_rows:
            counts_by_channel.setdefault(channel_id, self._empty_bot_counts())[
                "factory_pending"
            ] += int(pending)

        onboarding_rows = (
            await self.session.execute(
                select(OnboardingBatch).where(OnboardingBatch.channel_id.in_(ids))
            )
        ).scalars().all()
        for batch in onboarding_rows:
            counts = counts_by_channel.setdefault(batch.channel_id, self._empty_bot_counts())
            counts["onboarding_batches"] += 1
            counts["onboarding_ready"] += int(batch.ready_count or 0)
            counts["onboarding_permission"] += int(batch.permission_count or 0)
            counts["onboarding_pending"] += max(
                int(batch.requested_count or 0)
                - int(batch.ready_count or 0)
                - int(batch.permission_count or 0)
                - int(batch.failed_count or 0)
                - int(batch.skipped_count or 0),
                0,
            )

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in counts_by_channel.items():
            if counts["factory_failed"]:
                status = ATTENTION_ERROR
                label = f"Не удалось создать ботов: {counts['factory_failed']}."
            elif counts["onboarding_permission"]:
                status = ATTENTION_WARNING
                label = f"Ботам не хватает прав при подключении: {counts['onboarding_permission']}."
            elif counts["factory_pending"] or counts["onboarding_pending"]:
                status = ATTENTION_INFO
                label = (
                    "Подготовка ботов идёт: "
                    f"{counts['factory_pending'] + counts['onboarding_pending']} в очереди."
                )
            else:
                status = ATTENTION_OK
                label = "Подготовка ботов не требуется."
            sections[channel_id] = _section(status, label, counts)
        return sections, job_keys

    @staticmethod
    def _empty_bot_counts() -> dict[str, int]:
        return {
            "factory_batches": 0,
            "factory_created": 0,
            "factory_failed": 0,
            "factory_pending": 0,
            "onboarding_batches": 0,
            "onboarding_ready": 0,
            "onboarding_permission": 0,
            "onboarding_pending": 0,
        }

    async def _content(self, ids: list[str]) -> dict[str, dict[str, object]]:
        source_rows = (
            await self.session.execute(
                select(ContentSource.id, ContentSource.channel_id).where(
                    ContentSource.channel_id.in_(ids)
                )
            )
        ).all()
        source_to_channel = dict(source_rows)

        counts_by_channel: dict[str, dict[str, int]] = {
            channel_id: self._empty_content_counts() for channel_id in ids
        }

        if source_to_channel:
            item_rows = (
                await self.session.execute(
                    select(ContentItem.source_id, ContentItem.status, func.count())
                    .where(ContentItem.source_id.in_(list(source_to_channel)))
                    .group_by(ContentItem.source_id, ContentItem.status)
                )
            ).all()
            for source_id, status, count in item_rows:
                channel_id = source_to_channel.get(source_id)
                if channel_id is None:
                    continue
                counts = counts_by_channel.setdefault(channel_id, self._empty_content_counts())
                counts["items"] += int(count)
                key = str(status)
                if key in counts:
                    counts[key] += int(count)

        pub_rows = (
            await self.session.execute(
                select(Publication.channel_id, Publication.status, func.count())
                .where(Publication.channel_id.in_(ids))
                .group_by(Publication.channel_id, Publication.status)
            )
        ).all()
        for channel_id, status, count in pub_rows:
            counts = counts_by_channel.setdefault(channel_id, self._empty_content_counts())
            counts["publications"] += int(count)
            key = str(status)
            if key in counts:
                counts[key] += int(count)

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in counts_by_channel.items():
            if counts["failed"]:
                status = ATTENTION_ERROR
                label = f"Публикации с ошибкой: {counts['failed']}."
            elif counts["needs_review"]:
                status = ATTENTION_WARNING
                label = f"Ждут проверки: {counts['needs_review']}."
            elif counts["scheduled"]:
                status = ATTENTION_INFO
                label = f"Запланировано публикаций: {counts['scheduled']}."
            elif counts["published"]:
                status = ATTENTION_OK
                label = f"Опубликовано: {counts['published']}."
            else:
                status = ATTENTION_OK
                label = "Контент по этому каналу ещё не публиковался."
            sections[channel_id] = _section(status, label, counts)
        return sections

    @staticmethod
    def _empty_content_counts() -> dict[str, int]:
        return {
            "items": 0,
            "needs_review": 0,
            "approved": 0,
            "scheduled": 0,
            "published": 0,
            "failed": 0,
            "publications": 0,
        }

    async def _pipeline(self, ids: list[str]) -> dict[str, dict[str, object]]:
        rows = (
            await self.session.execute(
                select(
                    ContentOperation.channel_id,
                    ContentOperation.stage,
                    ContentOperation.status,
                    func.count(),
                )
                .where(ContentOperation.channel_id.in_(ids))
                .group_by(
                    ContentOperation.channel_id,
                    ContentOperation.stage,
                    ContentOperation.status,
                )
            )
        ).all()
        counts_by_channel: dict[str, dict[str, int]] = {}
        for channel_id, stage, status, count in rows:
            counts = counts_by_channel.setdefault(
                channel_id, {"operations": 0, "ai_unavailable": 0}
            )
            counts["operations"] += int(count)
            stage_key = str(stage)
            counts[stage_key] = counts.get(stage_key, 0) + int(count)
            if stage_key == "ai" and str(status) in {AI_STATUS_UNAVAILABLE, AI_STATUS_ERROR}:
                counts["ai_unavailable"] += int(count)

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in counts_by_channel.items():
            if counts["ai_unavailable"]:
                status = ATTENTION_WARNING
                label = f"ИИ недоступен для записей: {counts['ai_unavailable']}."
            else:
                status = ATTENTION_OK
                label = f"Операций конвейера: {counts['operations']}."
            sections[channel_id] = _section(status, label, counts)
        return sections

    async def _post_keys(self, ids: list[str]) -> dict[str, str]:
        rows = (
            await self.session.execute(
                select(Post.id, Post.registry_channel_id).where(Post.registry_channel_id.in_(ids))
            )
        ).all()
        return dict(rows)

    async def _queue_sections(
        self, ids: list[str], job_keys: dict[str, str]
    ) -> dict[str, dict[str, object]]:
        if not job_keys:
            return {}
        rows = (
            await self.session.execute(
                select(Job.group_key, Job.kind, Job.status, func.count())
                .where(Job.group_key.in_(list(job_keys)))
                .group_by(Job.group_key, Job.kind, Job.status)
            )
        ).all()
        counts_by_channel: dict[str, dict[str, int]] = {}
        kinds_by_channel: dict[str, set[str]] = {}
        for group_key, kind, status, count in rows:
            channel_id = job_keys.get(group_key)
            if channel_id is None:
                continue
            counts = counts_by_channel.setdefault(
                channel_id, {"total": 0, "active": 0, "failed": 0}
            )
            counts["total"] += int(count)
            if status in _ACTIVE_JOB_STATUSES:
                counts["active"] += int(count)
            elif status == JobStatus.FAILED:
                counts["failed"] += int(count)
            kinds_by_channel.setdefault(channel_id, set()).add(str(kind))

        sections: dict[str, dict[str, object]] = {}
        for channel_id, counts in counts_by_channel.items():
            if counts["failed"]:
                status = ATTENTION_WARNING
                label = f"Задания с ошибкой: {counts['failed']}."
            elif counts["active"]:
                status = ATTENTION_INFO
                label = f"Активные задания: {counts['active']}."
            else:
                status = ATTENTION_OK
                label = f"Заданий всего: {counts['total']}."
            sections[channel_id] = _section(
                status, label, counts, sorted(kinds_by_channel.get(channel_id, set()))
            )
        return sections

    async def _events_section(self) -> dict[str, object]:
        rows = (
            await self.session.execute(
                select(Event.level, func.count())
                .where(Event.module == "channels", Event.resolved.is_(False))
                .group_by(Event.level)
            )
        ).all()
        counts = {"unresolved_total": 0, "unresolved_errors": 0}
        for level, count in rows:
            counts["unresolved_total"] += int(count)
            if level in {EventLevel.ERROR, EventLevel.CRITICAL}:
                counts["unresolved_errors"] += int(count)

        last = (
            await self.session.execute(
                select(Event.message)
                .where(
                    Event.module == "channels",
                    Event.resolved.is_(False),
                    Event.level.in_([EventLevel.ERROR, EventLevel.CRITICAL]),
                )
                .order_by(Event.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

        if counts["unresolved_errors"]:
            status = ATTENTION_ERROR
            label = f"Необработанные ошибки журнала: {counts['unresolved_errors']}."
        else:
            status = ATTENTION_OK
            label = "Журнал каналов без необработанных ошибок."
        items = [str(last)] if last else []
        return _section(status, label, counts, items)


def _channel_label(item: dict[str, object]) -> str:
    title = str(item.get("title") or "")
    username = str(item.get("username") or "")
    reference = str(item.get("reference") or "")
    return title or username or reference or str(item.get("id", ""))


def _parse_modules(raw: object) -> dict[str, bool]:
    return parse_modules(raw)


__all__ = [
    "ATTENTION_ERROR",
    "ATTENTION_INFO",
    "ATTENTION_LABELS",
    "ATTENTION_OK",
    "ATTENTION_WARNING",
    "ChannelOverviewService",
]
