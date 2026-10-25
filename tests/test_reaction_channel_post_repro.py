"""Regression tests for Reaction Manager channel-post ingestion (D-130).

Real-world defect: the Reaction Manager never reacted to a real channel post.
Nothing fed the pipeline. The manager-bot runtime parsed only
``message``/``callback``/``managed_bot`` updates, the aiogram provider had no
``channel_post`` branch (a real post was returned as ``kind="other"`` and
dropped), ``get_updates`` never asked Telegram for ``channel_post``, and the
manual API path stored a post with no Telegram ``message_id`` so its job could
never execute.

These tests lock the fix: a manager bot that is a channel administrator receives
each new post as a ``channel_post`` update, the post is stored with its real
numeric ``chat_id``/``message_id``, reactions are planned, redelivery is a no-op,
and the manual path refuses a post it cannot react to instead of enqueuing a job
that always fails.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aiogram.types import Chat, Message, Update

from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.models.channel import Channel, ChannelKind
from backend.app.db.models.post import PostStatus
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.posts import PostRepository
from backend.app.db.repositories.reactions import ReactionJobRepository
from backend.app.db.session import init_models, session_scope
from backend.app.manager.runtime import ManagerBotRuntime
from backend.app.providers.errors import UnauthorizedError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.types import MANAGER_ALLOWED_UPDATES, BotUpdate
from backend.app.services.reaction_service import ReactionService, ReactionServiceError

CHAT_ID = -1001234567890


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


@pytest.fixture(autouse=True)
def _patch_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.services.reaction_service.open_secret",
        lambda value, settings: "123:FAKE",
    )


async def _seed(session, *, modules=None, enabled: bool = True) -> ReactionService:
    await ChannelRepository(session).add(
        Channel(
            id="ch1",
            reference="@mychannel",
            username="mychannel",
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
            token_encrypted="enc:x",
            health=BotHealth.OK,
        )
    )
    service = ReactionService(session)
    await service.save_profile(
        None,
        name="P",
        enabled=enabled,
        is_default=True,
        allowed_emoji=["❤️", "👍"],
        participation_probability=1.0,
        skip_probability=0.0,
        delay_min=1,
        delay_max=2,
    )
    return service


# --- provider: real channel_post updates are parsed -------------------------
def _parse(update: Update) -> list[BotUpdate]:
    from backend.app.providers.aiogram_bot import AiogramBotProvider

    provider = AiogramBotProvider("123456:TEST-TOKEN")

    async def fake_get_updates(**kwargs):  # type: ignore[no-untyped-def]
        return [update]

    provider._bot.get_updates = fake_get_updates  # type: ignore[method-assign]
    return asyncio.run(provider.get_updates(timeout=0))


def test_aiogram_parses_channel_post() -> None:
    chat = Chat(id=CHAT_ID, type="channel", username="mychannel", title="My")
    message = Message(message_id=42, date=0, chat=chat, text="Спасибо за донат!")
    parsed = _parse(Update(update_id=7, channel_post=message))
    assert parsed
    assert parsed[0].kind == "channel_post"
    assert parsed[0].channel_post_chat_id == CHAT_ID
    assert parsed[0].channel_post_message_id == 42
    assert parsed[0].channel_post_text == "Спасибо за донат!"
    assert parsed[0].channel_post_chat_username == "mychannel"
    assert parsed[0].channel_post_edited is False


def test_aiogram_parses_edited_channel_post() -> None:
    chat = Chat(id=CHAT_ID, type="channel", username="mychannel", title="My")
    message = Message(message_id=42, date=0, chat=chat, text="Обновлено")
    parsed = _parse(Update(update_id=8, edited_channel_post=message))
    assert parsed[0].kind == "channel_post"
    assert parsed[0].channel_post_edited is True
    assert parsed[0].channel_post_message_id == 42


def test_poller_asks_telegram_for_channel_posts() -> None:
    """Without ``channel_post`` in allowed_updates Telegram never sends posts."""
    assert "channel_post" in MANAGER_ALLOWED_UPDATES
    assert "edited_channel_post" in MANAGER_ALLOWED_UPDATES
    provider = FakeTelegramBotProvider("123456:ABC")
    asyncio.run(provider.get_updates(allowed_updates=list(MANAGER_ALLOWED_UPDATES)))
    assert provider.last_allowed_updates is not None
    assert "channel_post" in provider.last_allowed_updates


async def test_runtime_poll_requests_channel_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real runtime loop must pass ``allowed_updates`` to ``get_updates``."""
    provider = FakeTelegramBotProvider("123456:ABC")
    provider.queue_updates([BotUpdate(update_id=1, kind="other")])

    class _Svc:
        def __init__(self, session) -> None:
            pass

        async def manager_provider(self):
            return provider

        async def register_commands(self, prov) -> bool:
            return True

        async def handle_update(self, update):
            class _Result:
                handled = False
                reply = ""

            return _Result()

    async def _no_flush(self, session, prov):
        return None

    monkeypatch.setattr("backend.app.manager.runtime.ManagerBotService", _Svc)
    monkeypatch.setattr(ManagerBotRuntime, "_flush_notifications", _no_flush)
    await ManagerBotRuntime()._tick()
    assert provider.last_allowed_updates is not None
    assert "channel_post" in provider.last_allowed_updates


# --- service: ingest stores real ids and plans reactions --------------------
async def test_ingest_channel_post_stores_real_ids_and_plans() -> None:
    async with session_scope() as session:
        service = await _seed(session)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID,
            message_id=42,
            text="Спасибо за донат!",
            chat_username="mychannel",
        )
        assert post is not None
        assert post.telegram_message_id == 42
        assert post.channel_id == CHAT_ID
        assert post.registry_channel_id == "ch1"
        assert post.status == PostStatus.PLANNED
        jobs = await ReactionJobRepository(session).for_post(post.id)
        assert jobs, "a real channel post must plan at least one reaction job"
        assert all(j.status.value == "scheduled" for j in jobs)


async def test_redelivered_update_is_a_noop() -> None:
    async with session_scope() as session:
        service = await _seed(session)
        first = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=42, text="x", chat_username="mychannel"
        )
        assert first is not None
        again = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=42, text="x", chat_username="mychannel"
        )
        assert again is None
        _posts, total = await service.posts.list()
        assert total == 1


async def test_edited_post_refreshes_text_without_replanning() -> None:
    async with session_scope() as session:
        service = await _seed(session)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=42, text="старый", chat_username="mychannel"
        )
        assert post is not None
        before = len(await ReactionJobRepository(session).for_post(post.id))
        result = await service.ingest_channel_post(
            chat_id=CHAT_ID,
            message_id=42,
            text="новый",
            chat_username="mychannel",
            edited=True,
        )
        assert result is None
        refreshed = await service.posts.get(post.id)
        assert refreshed is not None and refreshed.text == "новый"
        after = len(await ReactionJobRepository(session).for_post(post.id))
        assert after == before, "an edit must not re-plan reactions"


async def test_unknown_channel_is_ignored() -> None:
    async with session_scope() as session:
        await _seed(session)
        service = ReactionService(session)
        assert (
            await service.ingest_channel_post(
                chat_id=-999, message_id=1, text="x", chat_username="not_mine"
            )
            is None
        )
        assert await service.posts.latest() is None


async def test_module_disabled_channel_is_ignored() -> None:
    async with session_scope() as session:
        service = await _seed(session, modules={"reactions": False})
        assert (
            await service.ingest_channel_post(
                chat_id=CHAT_ID, message_id=42, text="x", chat_username="mychannel"
            )
            is None
        )
        assert await service.posts.latest() is None


async def test_reactions_disabled_is_ignored() -> None:
    async with session_scope() as session:
        service = await _seed(session, enabled=False)
        assert (
            await service.ingest_channel_post(
                chat_id=CHAT_ID, message_id=42, text="x", chat_username="mychannel"
            )
            is None
        )
        assert await service.posts.latest() is None


# --- runtime handler --------------------------------------------------------
async def test_runtime_handler_ingests_channel_post() -> None:
    async with session_scope() as session:
        await _seed(session)
        await ManagerBotRuntime()._handle_channel_post(
            session,
            BotUpdate(
                update_id=7,
                kind="channel_post",
                channel_post_chat_id=CHAT_ID,
                channel_post_message_id=42,
                channel_post_text="Спасибо за донат!",
                channel_post_chat_username="mychannel",
            ),
        )
        post = await PostRepository(session).get_by_telegram(CHAT_ID, 42)
        assert post is not None
        assert post.telegram_message_id == 42
        assert post.channel_id == CHAT_ID
        assert await ReactionJobRepository(session).for_post(post.id)


# --- execution --------------------------------------------------------------
def _factory(record, *, fail=None):
    def _make(token, *, provider_name="auto", settings=None):
        provider = FakeTelegramBotProvider(token, fail_with=fail)
        record.append(provider)
        return provider

    return _make


async def test_channel_post_reaction_reaches_provider() -> None:
    record: list[FakeTelegramBotProvider] = []
    async with session_scope() as session:
        service = await _seed(session)
        service._provider_factory = _factory(record)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID,
            message_id=42,
            text="Спасибо за донат!",
            chat_username="mychannel",
        )
        assert post is not None
        jobs = await ReactionJobRepository(session).for_post(post.id)
        for job in jobs:
            await service.execute_reaction_job(job.id)
        assert record and record[0].reactions, "a reaction must actually be applied"
        applied = record[0].reactions[0]
        assert applied.chat_id == CHAT_ID
        assert applied.message_id == 42


async def test_telegram_error_is_reported_honestly() -> None:
    """A Telegram refusal must fail the job with the real message, not silently."""
    record: list[FakeTelegramBotProvider] = []
    async with session_scope() as session:
        service = await _seed(session)
        error = UnauthorizedError(
            "Бот не имеет права ставить реакции в этом канале.",
            how_to_fix="Выдайте боту право «Реакции» в настройках канала.",
        )
        service._provider_factory = _factory(record, fail=error)
        post = await service.ingest_channel_post(
            chat_id=CHAT_ID,
            message_id=42,
            text="Спасибо за донат!",
            chat_username="mychannel",
        )
        assert post is not None
        jobs = await ReactionJobRepository(session).for_post(post.id)
        with pytest.raises(UnauthorizedError):
            await service.execute_reaction_job(jobs[0].id)
        failed = await service.jobs.get(jobs[0].id)
        assert failed is not None
        assert failed.status.value == "failed"
        assert "реакции" in failed.error.lower()


# --- manual scenario --------------------------------------------------------
async def test_manual_post_without_message_id_is_skipped() -> None:
    """A typed post with no Telegram id must not enqueue an unrunnable job."""
    async with session_scope() as session:
        service = await _seed(session)
        post = await service.ingest_post(
            text="Спасибо за донат!", registry_channel_id="ch1", seed=1
        )
        assert post.status == PostStatus.SKIPPED
        assert await service.jobs.for_post(post.id) == []


async def test_manual_plan_without_message_id_is_refused() -> None:
    from backend.app.db.models.post import Post

    async with session_scope() as session:
        service = await _seed(session)
        post = Post(
            text="x",
            category="neutral",
            status=PostStatus.CLASSIFIED,
            registry_channel_id="ch1",
        )
        session.add(post)
        await session.flush()
        with pytest.raises(ReactionServiceError):
            await service.plan_post(post)
        assert await service.jobs.for_post(post.id) == []
