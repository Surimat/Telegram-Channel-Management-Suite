"""Reaction service tests: profiles, rules, ingestion, execution, recovery.

Everything runs against a temporary SQLite DB and the deterministic fake
provider — no Telegram credentials and no network (D-001).
"""

from __future__ import annotations

import random
from datetime import timedelta

import pytest

from backend.app.db.base import utcnow
from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.models.post import Post, PostStatus
from backend.app.db.models.reaction import ReactionJob, ReactionJobStatus
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import FloodWaitError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.services.queue_service import QueueService
from backend.app.services.reaction_service import (
    REACTION_JOB_KIND,
    ReactionService,
    ReactionServiceError,
)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def _factory(record: list[FakeTelegramBotProvider] | None = None, *, fail: Exception | None = None):
    def _make(token, *, provider_name="auto", settings=None):
        provider = FakeTelegramBotProvider(token, fail_with=fail)
        if record is not None:
            record.append(provider)
        return provider

    return _make


async def _add_bot(session, *, username: str, telegram_id: int, health=BotHealth.OK) -> Bot:
    repo = BotRepository(session)
    bot = Bot(
        kind=BotKind.ORDINARY,
        enabled=True,
        telegram_id=telegram_id,
        username=username,
        token_encrypted="enc:placeholder",  # opened via monkeypatched open_secret
        health=health,
    )
    await repo.add(bot)
    return bot


@pytest.fixture(autouse=True)
def _patch_open_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.reaction_service.open_secret",
        lambda value, settings: "123:FAKE",
    )


async def _service(session, record=None, *, fail=None, rng=None) -> ReactionService:
    return ReactionService(
        session, provider_factory=_factory(record, fail=fail), rng=rng or random.Random(1)
    )


async def test_ensure_default_rules_seeds_once() -> None:
    async with session_scope() as session:
        service = await _service(session)
        created = await service.ensure_default_rules()
        assert created > 0
        assert await service.ensure_default_rules() == 0
        rules = await service.list_rules()
        assert len(rules) == created


async def test_profile_crud_and_validation() -> None:
    async with session_scope() as session:
        service = await _service(session)
        profile = await service.save_profile(
            None,
            name="Основной",
            enabled=True,
            is_default=True,
            allowed_emoji=["👍", "❤️"],
            participation_probability=0.8,
        )
        assert profile.is_default
        updated = await service.save_profile(profile.id, name="Переименован")
        assert updated.name == "Переименован"
        with pytest.raises(ReactionServiceError):
            await service.save_profile(profile.id, participation_probability=2.0)
        with pytest.raises(ReactionServiceError):
            await service.save_profile(profile.id, delay_min=100, delay_max=10)
        await service.delete_profile(profile.id)
        assert await service.get_profile(profile.id) is None


async def test_only_one_default_profile() -> None:
    async with session_scope() as session:
        service = await _service(session)
        a = await service.save_profile(None, name="A", is_default=True, enabled=True)
        b = await service.save_profile(None, name="B", is_default=True, enabled=True)
        assert a.is_default is False or b.is_default is False
        defaults = [p for p in await service.list_profiles() if p.is_default]
        assert len(defaults) == 1


async def test_set_reactions_enabled_creates_default_profile() -> None:
    async with session_scope() as session:
        service = await _service(session)
        await service.set_reactions_enabled(True)
        assert await service.reactions_enabled() is True
        assert await service.get_active_profile() is not None


async def test_simulate_without_bots_uses_demo_bots() -> None:
    async with session_scope() as session:
        service = await _service(session)
        await service.ensure_default_rules()
        await service.save_profile(
            None,
            name="Sim",
            enabled=True,
            is_default=True,
            allowed_emoji=["❤️", "👍"],
            participation_probability=1.0,
            skip_probability=0.0,
            delay_min=5,
            delay_max=60,
        )
        result = await service.simulate(text="Спасибо за донат!", bot_count=4, seed=1)
        assert result.category == "donation"
        assert result.total_bots == 4
        assert result.participating >= 1
        assert all(s.delay_seconds >= 0 for s in result.steps)


async def test_ingest_post_plans_durable_jobs() -> None:
    record: list[FakeTelegramBotProvider] = []
    async with session_scope() as session:
        service = await _service(session, record)
        await _add_bot(session, username="r1", telegram_id=101)
        await _add_bot(session, username="r2", telegram_id=102)
        await service.save_profile(
            None,
            name="Plan",
            enabled=True,
            is_default=True,
            allowed_emoji=["❤️", "👍"],
            participation_probability=1.0,
            skip_probability=0.0,
            delay_min=1,
            delay_max=5,
        )
        post = await service.ingest_post(text="спасибо за донат", channel_id=-100123,
                                         telegram_message_id=55, seed=1)
        assert post.status == PostStatus.PLANNED
        jobs = await service.jobs.for_post(post.id)
        assert jobs  # at least one scheduled
        # Every scheduled job has a matching durable queue row.
        for job in jobs:
            if job.status == ReactionJobStatus.SCHEDULED:
                assert job.queue_job_id
                queue_job = await QueueService(session).get(job.queue_job_id)
                assert queue_job is not None
                assert queue_job.kind == REACTION_JOB_KIND


async def test_execute_reaction_job_records_on_fake_provider() -> None:
    record: list[FakeTelegramBotProvider] = []
    async with session_scope() as session:
        service = await _service(session, record)
        bot = await _add_bot(session, username="reactor", telegram_id=200)
        await service.save_profile(
            None, name="Exec", enabled=True, is_default=True,
            allowed_emoji=["❤️"], participation_probability=1.0, skip_probability=0.0,
            delay_min=0, delay_max=1,
        )
        post = await service.ingest_post(
            text="спасибо за донат", channel_id=-100999, telegram_message_id=77, seed=2
        )
        jobs = await service.jobs.for_post(post.id)
        scheduled = [j for j in jobs if j.status == ReactionJobStatus.SCHEDULED]
        assert scheduled
        job = scheduled[0]
        await service.execute_reaction_job(job.id)

        refreshed = await service.jobs.get(job.id)
        assert refreshed is not None
        assert refreshed.status == ReactionJobStatus.DONE
        assert refreshed.reaction == "❤️"

        # The fake provider recorded bot + emoji + message id.
        reactions = [r for p in record for r in p.reactions]
        assert reactions
        assert reactions[0].emoji == "❤️"
        assert reactions[0].message_id == 77
        assert reactions[0].chat_id == -100999
        _ = bot


async def test_execute_flood_wait_marks_failed_not_bypassed() -> None:
    async with session_scope() as session:
        service = await _service(
            session, fail=FloodWaitError(30, technical="FloodWait")
        )
        await _add_bot(session, username="slow", telegram_id=300)
        await service.save_profile(
            None, name="Flood", enabled=True, is_default=True,
            allowed_emoji=["👍"], participation_probability=1.0, skip_probability=0.0,
            delay_min=0, delay_max=1,
        )
        post = await service.ingest_post(
            text="новость", channel_id=-1001, telegram_message_id=88, seed=3
        )
        jobs = await service.jobs.for_post(post.id)
        job = next(j for j in jobs if j.status == ReactionJobStatus.SCHEDULED)
        with pytest.raises(FloodWaitError):
            await service.execute_reaction_job(job.id)
        refreshed = await service.jobs.get(job.id)
        assert refreshed is not None
        assert refreshed.status == ReactionJobStatus.FAILED
        assert "FloodWait" in refreshed.error


async def test_execute_without_telegram_ids_fails_clearly() -> None:
    record: list[FakeTelegramBotProvider] = []
    async with session_scope() as session:
        service = await _service(session, record)
        bot = await _add_bot(session, username="noid", telegram_id=400)

        post = Post(text="x", category="neutral", status=PostStatus.PLANNED)
        session.add(post)
        await session.flush()
        job = ReactionJob(post_id=post.id, bot_id=bot.id, reaction="👍",
                          status=ReactionJobStatus.SCHEDULED)
        session.add(job)
        await session.flush()
        with pytest.raises(ReactionServiceError):
            await service.execute_reaction_job(job.id)


async def test_recover_resets_running_reaction_jobs() -> None:
    async with session_scope() as session:
        bot = await _add_bot(session, username="r", telegram_id=500)

        post = Post(text="x", status=PostStatus.PLANNED)
        session.add(post)
        await session.flush()
        job = ReactionJob(post_id=post.id, bot_id=bot.id, reaction="👍",
                          status=ReactionJobStatus.RUNNING)
        session.add(job)
        await session.flush()
        job_id = job.id

    async with session_scope() as session:
        recovered = await ReactionService(session).recover()
        assert recovered == 1
        job = await session.get(ReactionJob, job_id)
        assert job is not None
        assert job.status == ReactionJobStatus.SCHEDULED


async def test_stats_reflect_activity() -> None:
    async with session_scope() as session:
        service = await _service(session)
        await _add_bot(session, username="s", telegram_id=600)
        await service.save_profile(
            None, name="Stats", enabled=True, is_default=True, allowed_emoji=["👍"],
        )
        await service.ingest_post(
            text="нейтрально", channel_id=-1, telegram_message_id=9, seed=1
        )
        stats = await service.stats()
        assert stats["enabled"] is True
        assert stats["active_bots"] == 1
        assert stats["last_post"] is not None


async def test_scheduler_executes_reaction_queue_job() -> None:
    """End-to-end: durable queue job → provider reaction through the scheduler."""
    from backend.app.scheduler.scheduler import Scheduler

    record: list[FakeTelegramBotProvider] = []
    async with session_scope() as session:
        bot = await _add_bot(session, username="sched", telegram_id=700)
        post = Post(text="x", category="neutral", status=PostStatus.PLANNED,
                    channel_id=-50, telegram_message_id=42)
        session.add(post)
        await session.flush()
        job = ReactionJob(post_id=post.id, bot_id=bot.id, reaction="🔥",
                          status=ReactionJobStatus.SCHEDULED,
                          scheduled_at=utcnow() - timedelta(seconds=1))
        session.add(job)
        await session.flush()
        queue_job = await QueueService(session).enqueue(
            kind=REACTION_JOB_KIND,
            payload={"reaction_job_id": job.id},
            scheduled_at=utcnow() - timedelta(seconds=1),
        )
        job.queue_job_id = queue_job.id
        reaction_job_id = job.id
        queue_job_id = queue_job.id

    async def handler(session, qjob: Job) -> None:
        import json

        payload = json.loads(qjob.payload)
        await ReactionService(
            session, provider_factory=_factory(record)
        ).execute_reaction_job(payload["reaction_job_id"])

    scheduler = Scheduler()
    scheduler.register(REACTION_JOB_KIND, handler)
    await scheduler._tick()

    async with session_scope() as session:
        qj = await QueueService(session).get(queue_job_id)
        assert qj is not None and qj.status == JobStatus.DONE
        rj = await session.get(ReactionJob, reaction_job_id)
        assert rj is not None and rj.status == ReactionJobStatus.DONE
    assert any(r.emoji == "🔥" for p in record for r in p.reactions)
