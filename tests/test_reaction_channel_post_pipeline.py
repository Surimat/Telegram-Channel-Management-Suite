"""End-to-end pipeline tests for the Reaction Manager channel-post source (D-130).

These tests prove the *whole* path, not just the pieces:

    real Telegram ``Update`` (channel_post)
      -> ``AiogramBotProvider.get_updates`` (real parser)
      -> ``ManagerBotRuntime`` poll loop (asks Telegram for channel posts)
      -> ``ReactionService.ingest_channel_post`` (real ``chat_id`` + ``message_id``)
      -> ``plan_post`` (durable reaction job + queue job for the right post)
      -> ``Scheduler`` claims the queue job and runs the registered handler
      -> ``execute_reaction_job`` calls the provider's ``set_reaction``
      -> the provider records the reaction on the *real* chat/message id.

They also lock the honest edge cases: a redelivered update is a no-op, a channel
whose ``reactions`` module is off stores/queues nothing, and a Telegram refusal
fails the job with the real message instead of pretending success.

No network, no real credentials: the Telegram update is a genuine
``aiogram.types.Update`` object fed to the real parser, and the reaction is
applied through the deterministic fake provider (decision D-001).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aiogram.types import Chat, Message, Update

from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.models.channel import Channel, ChannelKind
from backend.app.db.models.job import JobStatus
from backend.app.db.models.post import PostStatus
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.posts import PostRepository
from backend.app.db.repositories.reactions import ReactionJobRepository
from backend.app.db.session import init_models, session_scope
from backend.app.manager.runtime import ManagerBotRuntime
from backend.app.providers.aiogram_bot import AiogramBotProvider
from backend.app.providers.errors import UnauthorizedError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.types import MANAGER_ALLOWED_UPDATES, BotUpdate
from backend.app.scheduler import handlers as scheduler_handlers
from backend.app.scheduler.scheduler import Scheduler
from backend.app.services.queue_service import QueueService
from backend.app.services.reaction_service import ReactionService

CHAT_ID = -1001234567890
MSG_ID = 4321
USERNAME = "mychannel"


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


@pytest.fixture(autouse=True)
def _fake_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Decrypt stored bot tokens to a valid-looking fake token (no crypto key)."""
    monkeypatch.setattr(
        "backend.app.services.reaction_service.open_secret",
        lambda value, settings: "123456:FAKE-TOKEN",
    )
    monkeypatch.setattr(
        "backend.app.core.security.open_secret",
        lambda value, settings: "123456:FAKE-TOKEN",
    )


def _real_update(*, message_id: int = MSG_ID, text: str = "Спасибо за донат!") -> Update:
    """A genuine ``channel_post`` update, as Telegram would deliver it."""
    chat = Chat(id=CHAT_ID, type="channel", username=USERNAME, title="My Channel")
    message = Message(message_id=message_id, date=0, chat=chat, text=text)
    return Update(update_id=100, channel_post=message)


def _fake_aiogram_provider(update: Update, captured: dict) -> AiogramBotProvider:
    """An ``AiogramBotProvider`` whose network call returns ``update`` once."""
    provider = AiogramBotProvider("123456:TEST-TOKEN")

    async def fake_get_updates(**kwargs):  # type: ignore[no-untyped-def]
        captured["allowed_updates"] = kwargs.get("allowed_updates")
        captured["offset"] = kwargs.get("offset")
        return [update]

    async def _noop_close() -> None:
        return None

    provider._bot.get_updates = fake_get_updates  # type: ignore[method-assign]
    provider.close = _noop_close  # type: ignore[method-assign]
    return provider


class _RuntimeServiceStub:
    """Stands in for ``ManagerBotService`` so the poll loop needs no network.

    It returns the provider under test from ``manager_provider`` and treats
    ``register_commands`` as a best-effort no-op (the command menu is unrelated
    to the channel-post path). ``handle_update`` is never reached for a
    ``channel_post``.
    """

    def __init__(self, session, provider) -> None:  # type: ignore[no-untyped-def]
        self._provider = provider

    async def manager_provider(self):  # type: ignore[no-untyped-def]
        return self._provider

    async def register_commands(self, provider) -> bool:  # type: ignore[no-untyped-def]
        return True

    async def handle_update(self, update):  # type: ignore[no-untyped-def]
        class _Result:
            handled = False
            reply = ""

        return _Result()


async def _seed(
    session,
    *,
    modules: dict | None = None,
) -> tuple[ReactionService, FakeTelegramBotProvider]:
    """Seed a channel wired to the reactions module, a slave bot and a profile."""
    await ChannelRepository(session).add(
        Channel(
            id="ch1",
            reference="@mychannel",
            username=USERNAME,
            telegram_id=CHAT_ID,
            kind=ChannelKind.CHANNEL,
            modules=json.dumps(modules if modules is not None else {"reactions": True}),
        )
    )
    await BotRepository(session).add(
        Bot(
            kind=BotKind.ORDINARY,
            enabled=True,
            telegram_id=555,
            username="slave1",
            token_encrypted="enc:slave",
            health=BotHealth.OK,
        )
    )
    # Manager bot: needed so ``manager_provider`` can build the poll provider.
    await BotRepository(session).add(
        Bot(
            kind=BotKind.MANAGER,
            enabled=True,
            telegram_id=999,
            username="manager",
            token_encrypted="enc:manager",
            health=BotHealth.OK,
        )
    )
    service = ReactionService(session)
    await service.save_profile(
        None,
        name="P",
        enabled=True,
        is_default=True,
        allowed_emoji=["❤️", "👍"],
        participation_probability=1.0,
        skip_probability=0.0,
        delay_min=0,
        delay_max=0,
    )
    provider = FakeTelegramBotProvider("123456:FAKE-TOKEN")
    return service, provider


def _fake_factory(provider: FakeTelegramBotProvider):  # type: ignore[no-untyped-def]
    def _make(token, *, provider_name="auto", settings=None):
        return provider

    return _make


async def _run_poll(monkeypatch: pytest.MonkeyPatch, update: Update, captured: dict) -> None:
    """Drive one real poll tick through the runtime with a real Update."""
    poll_provider = _fake_aiogram_provider(update, captured)

    def _stub_factory(session):  # type: ignore[no-untyped-def]
        return _RuntimeServiceStub(session, poll_provider)

    async def _no_flush(self, session, provider):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("backend.app.manager.runtime.ManagerBotService", _stub_factory)
    monkeypatch.setattr(ManagerBotRuntime, "_flush_notifications", _no_flush)
    await ManagerBotRuntime()._tick()


# --- the whole path: real update -> provider.set_reaction -------------------
async def test_full_pipeline_real_channel_post_reaches_telegram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuine ``channel_post`` update must reach ``set_reaction`` end to end."""
    captured: dict = {}
    reaction_provider = FakeTelegramBotProvider("123456:FAKE-TOKEN")

    async with session_scope() as session:
        _service, reaction_provider = await _seed(session)
        # 1) Real Telegram Update -> real parser -> runtime poll -> ingest/plan.
        await _run_poll(monkeypatch, _real_update(), captured)

    # The poller must ask Telegram for channel posts, otherwise they never arrive.
    assert captured["allowed_updates"] is not None
    assert "channel_post" in captured["allowed_updates"]

    async with session_scope() as session:
        post = await PostRepository(session).get_by_telegram(CHAT_ID, MSG_ID)
        assert post is not None, "a real channel post must be stored"
        assert post.telegram_message_id == MSG_ID
        assert post.channel_id == CHAT_ID
        assert post.registry_channel_id == "ch1"
        assert post.status == PostStatus.PLANNED

        jobs = await ReactionJobRepository(session).for_post(post.id)
        assert jobs, "a real channel post must plan at least one reaction"
        scheduled = [j for j in jobs if j.status.value == "scheduled"]
        assert scheduled, "at least one reaction job must be scheduled"

        # The durable queue must carry the *right* post for the reaction job.
        queue_jobs, _total = await QueueService(session).list(limit=100)
        reaction_queue = [j for j in queue_jobs if j.kind == "reaction.job"]
        assert reaction_queue, "a queue job must be enqueued for the reaction"
        payload = json.loads(reaction_queue[0].payload)
        assert payload["post_id"] == post.id
        assert payload["reaction_job_id"] == scheduled[0].id

        # 2) Apply the reaction through the provider (fake) and record the result.
        service = ReactionService(session, provider_factory=_fake_factory(reaction_provider))
        for job in scheduled:
            await service.execute_reaction_job(job.id)
        await session.commit()

    # 3) The provider must have actually applied a reaction on the real ids.
    assert reaction_provider.reactions, "set_reaction must be called"
    applied = reaction_provider.reactions[0]
    assert applied.chat_id == CHAT_ID
    assert applied.message_id == MSG_ID
    assert applied.emoji

    async with session_scope() as session:
        done_jobs = await ReactionJobRepository(session).for_post(
            (await PostRepository(session).get_by_telegram(CHAT_ID, MSG_ID)).id
        )
        assert all(j.status.value == "done" for j in done_jobs)


async def test_scheduler_claims_queue_job_and_applies_reaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The registered scheduler handler must run the queued reaction job."""
    reaction_provider = FakeTelegramBotProvider("123456:FAKE-TOKEN")

    async with session_scope() as session:
        service, reaction_provider = await _seed(session)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=MSG_ID, text="Спасибо за донат!", chat_username=USERNAME
        )
        assert post is not None

    real_service = ReactionService

    def _service_factory(session):  # type: ignore[no-untyped-def]
        return real_service(session, provider_factory=_fake_factory(reaction_provider))

    monkeypatch.setattr(scheduler_handlers, "ReactionService", _service_factory)

    scheduler = Scheduler()
    scheduler_handlers.register_handlers(scheduler)
    await scheduler._tick()

    assert reaction_provider.reactions, "the scheduler must apply the reaction"
    assert reaction_provider.reactions[0].chat_id == CHAT_ID
    assert reaction_provider.reactions[0].message_id == MSG_ID

    async with session_scope() as session:
        queue_jobs, _total = await QueueService(session).list(limit=100)
        reaction_queue = [j for j in queue_jobs if j.kind == "reaction.job"]
        assert reaction_queue and reaction_queue[0].status == JobStatus.DONE


# --- Telegram delivery is actually requested --------------------------------
def test_allowed_updates_request_channel_posts() -> None:
    """Telegram only sends channel posts when they are explicitly requested."""
    assert "channel_post" in MANAGER_ALLOWED_UPDATES
    assert "edited_channel_post" in MANAGER_ALLOWED_UPDATES


async def test_fake_provider_records_requested_allowed_updates() -> None:
    provider = FakeTelegramBotProvider("123456:ABC")
    await provider.get_updates(allowed_updates=list(MANAGER_ALLOWED_UPDATES))
    assert provider.last_allowed_updates is not None
    assert "channel_post" in provider.last_allowed_updates


# --- duplicates -------------------------------------------------------------
async def test_redelivered_update_does_not_duplicate_post_or_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telegram may redeliver an update; it must not double-store or double-queue."""
    captured: dict = {}
    update = _real_update()

    async with session_scope() as session:
        await _seed(session)

    await _run_poll(monkeypatch, update, captured)
    await _run_poll(monkeypatch, update, captured)

    async with session_scope() as session:
        _posts, total = await PostRepository(session).list()
        assert total == 1, "a redelivered update must not create a second post"
        post = await PostRepository(session).get_by_telegram(CHAT_ID, MSG_ID)
        assert post is not None
        jobs = await ReactionJobRepository(session).for_post(post.id)
        assert len(jobs) == 1, "a redelivered update must not double-plan"
        queue_jobs, _t = await QueueService(session).list(limit=100)
        assert len([j for j in queue_jobs if j.kind == "reaction.job"]) == 1


# --- module off -------------------------------------------------------------
async def test_module_off_stores_nothing_and_queues_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A channel with the reactions module off must be ignored entirely."""
    captured: dict = {}
    async with session_scope() as session:
        await _seed(session, modules={"reactions": False})

    await _run_poll(monkeypatch, _real_update(), captured)

    async with session_scope() as session:
        assert await PostRepository(session).latest() is None
        queue_jobs, _t = await QueueService(session).list(limit=100)
        assert not [j for j in queue_jobs if j.kind == "reaction.job"]


# --- Telegram error ---------------------------------------------------------
async def test_telegram_error_is_recorded_on_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Telegram refusal must fail the job with the real message, not silently."""
    failing = FakeTelegramBotProvider(
        "123456:FAKE-TOKEN",
        fail_with=UnauthorizedError(
            "Бот не имеет права ставить реакции в этом канале.",
            how_to_fix="Выдайте боту право «Реакции» в настройках канала.",
        ),
    )

    async with session_scope() as session:
        service, _provider = await _seed(session)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=MSG_ID, text="Спасибо за донат!", chat_username=USERNAME
        )
        assert post is not None
        jobs = await ReactionJobRepository(session).for_post(post.id)
        scheduled = [j for j in jobs if j.status.value == "scheduled"]
        assert scheduled

        failing_service = ReactionService(session, provider_factory=_fake_factory(failing))
        with pytest.raises(UnauthorizedError):
            await failing_service.execute_reaction_job(scheduled[0].id)
        await session.commit()

    async with session_scope() as session:
        post = await PostRepository(session).get_by_telegram(CHAT_ID, MSG_ID)
        job = (await ReactionJobRepository(session).for_post(post.id))[0]
        assert job.status.value == "failed"
        assert "реакции" in job.error.lower()


async def test_scheduler_marks_queue_job_failed_on_telegram_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing handler must mark the durable queue job FAILED, not DONE."""
    failing = FakeTelegramBotProvider(
        "123456:FAKE-TOKEN",
        fail_with=UnauthorizedError("Нет права ставить реакции."),
    )

    async with session_scope() as session:
        service, _p = await _seed(session)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=MSG_ID, text="Спасибо!", chat_username=USERNAME
        )
        assert post is not None

    real_service = ReactionService

    def _service_factory(session):  # type: ignore[no-untyped-def]
        return real_service(session, provider_factory=_fake_factory(failing))

    monkeypatch.setattr(scheduler_handlers, "ReactionService", _service_factory)
    scheduler = Scheduler()
    scheduler_handlers.register_handlers(scheduler)
    await scheduler._tick()

    async with session_scope() as session:
        queue_jobs, _t = await QueueService(session).list(limit=100)
        reaction_queue = [j for j in queue_jobs if j.kind == "reaction.job"]
        assert reaction_queue and reaction_queue[0].status == JobStatus.FAILED


# --- manual path with a known real message id -------------------------------
async def test_manual_post_with_known_message_id_reaches_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the real Telegram id is known, a manual post must still react."""
    reaction_provider = FakeTelegramBotProvider("123456:FAKE-TOKEN")

    async with session_scope() as session:
        service, reaction_provider = await _seed(session)
        post = await service.ingest_post(
            text="Спасибо за донат!",
            telegram_message_id=MSG_ID,
            channel_id=CHAT_ID,
            registry_channel_id="ch1",
        )
        assert post.telegram_message_id == MSG_ID
        assert post.channel_id == CHAT_ID
        assert post.status == PostStatus.PLANNED

        jobs = await ReactionJobRepository(session).for_post(post.id)
        scheduled = [j for j in jobs if j.status.value == "scheduled"]
        assert scheduled, "a manual post with a real id must enqueue a reaction"

        exec_service = ReactionService(session, provider_factory=_fake_factory(reaction_provider))
        for job in scheduled:
            await exec_service.execute_reaction_job(job.id)
        await session.commit()

    assert reaction_provider.reactions
    assert reaction_provider.reactions[0].chat_id == CHAT_ID
    assert reaction_provider.reactions[0].message_id == MSG_ID


async def test_runtime_handler_ingests_real_update() -> None:
    """``_handle_channel_post`` must store the post with its real ids."""
    async with session_scope() as session:
        await _seed(session)
        await ManagerBotRuntime()._handle_channel_post(
            session,
            BotUpdate(
                update_id=7,
                kind="channel_post",
                channel_post_chat_id=CHAT_ID,
                channel_post_message_id=MSG_ID,
                channel_post_text="Спасибо за донат!",
                channel_post_chat_username=USERNAME,
            ),
        )
        post = await PostRepository(session).get_by_telegram(CHAT_ID, MSG_ID)
        assert post is not None
        assert post.telegram_message_id == MSG_ID
        assert post.channel_id == CHAT_ID
        assert await ReactionJobRepository(session).for_post(post.id)


# --- negative controls: the pre-fix behaviour must NOT be sufficient --------
def test_parser_without_channel_post_branch_drops_the_post() -> None:
    """Prove the ``channel_post`` branch is what makes ingestion possible.

    Emulates the pre-D-130 parser (no ``channel_post``/``edited_channel_post``
    branch): the same real ``Update`` is then classified ``kind="other"`` and the
    runtime never ingests it. This is the negative control for the fix.
    """
    real = _real_update()

    class _OldUpdate:
        def __init__(self, update: Update) -> None:
            self.update_id = update.update_id

        def __getattr__(self, name: str):  # no channel_post branch existed
            return None

    provider = AiogramBotProvider("123456:TEST-TOKEN")

    async def fake_get_updates(**kwargs):  # type: ignore[no-untyped-def]
        return [_OldUpdate(real)]

    provider._bot.get_updates = fake_get_updates  # type: ignore[method-assign]
    parsed = asyncio.run(provider.get_updates(timeout=0))
    assert [u.kind for u in parsed] == ["other"]

    # And the *fixed* parser on the same update yields channel_post.
    fixed = _fake_aiogram_provider(real, {})
    fixed_parsed = asyncio.run(fixed.get_updates(timeout=0))
    assert fixed_parsed[0].kind == "channel_post"
    assert fixed_parsed[0].channel_post_message_id == MSG_ID


async def test_other_kind_update_is_never_ingested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-``channel_post`` update must not create a post or a job."""
    async with session_scope() as session:
        await _seed(session)
        await ManagerBotRuntime()._handle_channel_post(
            session,
            BotUpdate(update_id=7, kind="other"),
        )
        assert await PostRepository(session).latest() is None

