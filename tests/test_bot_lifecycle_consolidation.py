"""Bot lifecycle consolidation tests (D-125).

Proves the four consolidated lifecycle behaviours end to end against the real
services (no mocks): duplicate-queue prevention, idempotent adoption, crash
recovery, and adoption of a bot created through the official managed-bot flow.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.app.db.models.bot import BotKind
from backend.app.db.models.bot_factory import BatchStatus, QueueState
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.jobs import JobRepository
from backend.app.db.session import init_models, session_scope
from backend.app.providers.aiogram_bot import AiogramBotProvider
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.fake_session import (
    FakeBotFactoryScenario,
    FakeSessionProvider,
)
from backend.app.providers.types import BotUpdate
from backend.app.services.bot_factory import (
    BOT_FACTORY_JOB_KIND,
    BotFactoryService,
)
from backend.app.services.bot_lifecycle import BotLifecycleService
from backend.app.services.bot_service import BotService
from backend.app.services.queue_service import QueueService


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def _bot_factory(token, *, provider_name="auto", settings=None):
    return FakeTelegramBotProvider(token)


def _manager(session):
    return BotService(session, provider_factory=_bot_factory)


def _service(session, provider: FakeSessionProvider | None = None) -> BotFactoryService:
    return BotFactoryService(session, bot_service=_manager(session))


async def _seed_account() -> None:
    from backend.app.db.models.session import SessionStatus, UserSession

    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )


async def _seed_manager(session, token: str = "555555:MANAGERTOKEN"):
    return await _manager(session).add_bot(
        token, kind=BotKind.MANAGER, title="Manager"
    )


async def _deep_link_batch(session) -> str:
    """A batch in deep-link mode with its candidates queued (D-109)."""
    manager = await _seed_manager(session)
    service = _service(session)
    batch = await service.create_batch(
        prefix="Mix", count=2, manager_bot_id=manager.id
    )
    batch = await service.create_batch_bots(batch.id, via_deeplink=True)
    return batch.id


# --- DEFECT 1: duplicate durable jobs ---------------------------------------
async def test_enqueue_unique_prevents_duplicate_factory_jobs() -> None:
    async with session_scope() as session:
        queue = QueueService(session)
        first = await queue.enqueue_unique(
            kind=BOT_FACTORY_JOB_KIND, payload={"batch_id": "b1"}, group_key="b1"
        )
        second = await queue.enqueue_unique(
            kind=BOT_FACTORY_JOB_KIND, payload={"batch_id": "b1"}, group_key="b1"
        )
        assert first is not None and first.id == second.id
        _, total = await JobRepository(session).list(kind=BOT_FACTORY_JOB_KIND)
        assert total == 1


async def test_enqueue_unique_allows_followup_when_excluding_self() -> None:
    async with session_scope() as session:
        queue = QueueService(session)
        running = await queue.enqueue(
            kind=BOT_FACTORY_JOB_KIND, payload={"batch_id": "b2"}, group_key="b2"
        )
        # The handler that owns ``running`` may schedule its own follow-up tick.
        followup = await queue.enqueue_unique(
            kind=BOT_FACTORY_JOB_KIND, payload={"batch_id": "b2"}, group_key="b2",
            exclude_id=running.id,
        )
        assert followup is not None and followup.id != running.id
        _, total = await JobRepository(session).list(kind=BOT_FACTORY_JOB_KIND)
        assert total == 2


async def test_start_queue_twice_creates_one_job() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        queue = QueueService(session)
        await queue.enqueue_unique(
            kind=BOT_FACTORY_JOB_KIND, payload={"batch_id": batch_id}, group_key=batch_id
        )
        await queue.enqueue_unique(
            kind=BOT_FACTORY_JOB_KIND, payload={"batch_id": batch_id}, group_key=batch_id
        )
        _, total = await JobRepository(session).list(kind=BOT_FACTORY_JOB_KIND)
        assert total == 1


# --- DEFECT 2: idempotent adoption / counter correctness --------------------
async def test_adopt_created_is_idempotent() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        service = _service(session)
        first = await service.adopt_created(batch_id, "mix_1_bot", 9001)
        assert first.bot_id
        batch = await service.get_batch(batch_id)
        assert batch.created_count == 1

        # A second delivery of the same managed-bot update must be a no-op.
        second = await service.adopt_created(batch_id, "mix_1_bot", 9001)
        assert second.id == first.id
        assert second.bot_id == first.bot_id
        batch = await service.get_batch(batch_id)
        assert batch.created_count == 1

        # No duplicate Bot row was registered for the same Telegram id.
        bots, _ = await BotRepository(session).list()
        matches = [b for b in bots if b.telegram_id == 9001]
        assert len(matches) == 1


async def test_created_count_reconciles_after_two_adoptions() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        service = _service(session)
        await service.adopt_created(batch_id, "mix_1_bot", 9101)
        await service.adopt_created(batch_id, "mix_2_bot", 9102)
        batch = await service.get_batch(batch_id)
        assert batch.created_count == 2
        # Re-adopting either must not drift the reconciled count.
        await service.adopt_created(batch_id, "mix_2_bot", 9102)
        batch = await service.get_batch(batch_id)
        assert batch.created_count == 2


# --- DEFECT 3: factory crash recovery ---------------------------------------
async def test_factory_recover_requeues_running_candidates() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        service = _service(session)
        rows = await service.list_candidates(batch_id)
        rows[0].queue_state = QueueState.RUNNING.value
        await session.flush()
        await session.commit()

    async with session_scope() as session:
        revived = await BotFactoryService(session).recover()
        assert revived == 1
        rows = await BotFactoryService(session).list_candidates(batch_id)
        assert rows[0].queue_state == QueueState.QUEUED.value


async def test_lifecycle_recover_covers_factory_and_onboarding() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        rows = await BotFactoryService(session).list_candidates(batch_id)
        rows[0].queue_state = QueueState.RUNNING.value
        await session.flush()
        await session.commit()

    async with session_scope() as session:
        result = await BotLifecycleService(session).recover()
        assert result.bot_factory == 1
        assert result.total >= 1


# --- DEFECT 3b: managed-bot adoption wired into the lifecycle ---------------
async def test_adopt_managed_bot_registers_into_batch() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        result = await BotLifecycleService(session).adopt_managed_bot(
            username="mix_1_bot", telegram_id=9201, title="Mix One"
        )
        assert result.adopted is True
        assert result.batch_ids == [batch_id]
        service = _service(session)
        batch = await service.get_batch(batch_id)
        assert batch.created_count == 1
        # The second delivery is a duplicate, not a second adoption.
        again = await BotLifecycleService(session).adopt_managed_bot(
            username="mix_1_bot", telegram_id=9201
        )
        assert again.adopted is False and again.duplicate is True


async def test_adopt_managed_bot_ignores_unknown_username() -> None:
    async with session_scope() as session:
        await _deep_link_batch(session)
        result = await BotLifecycleService(session).adopt_managed_bot(
            username="someone_else_bot", telegram_id=9999
        )
        assert result.adopted is False
        assert result.duplicate is False


async def test_deep_link_batch_completes_only_when_all_adopted() -> None:
    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        service = _service(session)
        await BotLifecycleService(session).adopt_managed_bot(
            username="mix_1_bot", telegram_id=9301
        )
        batch = await service.get_batch(batch_id)
        assert batch.status is not BatchStatus.COMPLETED  # one candidate remains

    async with session_scope() as session:
        await BotLifecycleService(session).adopt_managed_bot(
            username="mix_2_bot", telegram_id=9302
        )
        batch = await _service(session).get_batch(batch_id)
        assert batch.status is BatchStatus.COMPLETED
        assert batch.completed_at is not None
        assert batch.created_count == 2


async def test_runtime_routes_managed_bot_update_to_adoption() -> None:
    """The manager-bot runtime adopts a bot announced by a ``managed_bot`` update."""
    from backend.app.manager.runtime import ManagerBotRuntime

    async with session_scope() as session:
        batch_id = await _deep_link_batch(session)
        update = BotUpdate(
            update_id=1,
            kind="managed_bot",
            managed_bot_user_id=7001,
            managed_bot_username="mix_1_bot",
            managed_bot_first_name="Mix One",
        )
        await ManagerBotRuntime()._handle_managed_bot(session, update)
        batch = await _service(session).get_batch(batch_id)
        assert batch.created_count == 1
        bots, _ = await BotRepository(session).list()
        assert any(b.telegram_id == 7001 for b in bots)


# --- aiogram managed_bot update parsing (real provider, no network) ---------
def test_aiogram_parses_managed_bot_update() -> None:
    from aiogram.types import ManagedBotUpdated, Update, User

    user = User(id=4242, is_bot=True, first_name="Mix", username="mix_1_bot")
    managed = ManagedBotUpdated(user=user, bot=user)
    update = Update(update_id=11, managed_bot=managed)

    provider = AiogramBotProvider("123456:TEST-TOKEN")

    async def fake_get_updates(**kwargs):  # type: ignore[no-untyped-def]
        return [update]

    provider._bot.get_updates = fake_get_updates  # type: ignore[method-assign]
    parsed = asyncio.run(provider.get_updates(timeout=0))
    assert len(parsed) == 1
    assert parsed[0].kind == "managed_bot"
    assert parsed[0].managed_bot_user_id == 4242
    assert parsed[0].managed_bot_username == "mix_1_bot"
    assert parsed[0].managed_bot_first_name == "Mix"


def test_bot_update_defaults_are_backwards_compatible() -> None:
    update = BotUpdate(update_id=1)
    assert update.kind == "message"
    assert update.managed_bot_user_id is None
    assert update.managed_bot_username == ""


# --- native creation path still idempotent ----------------------------------
async def test_native_creation_repeated_adoption_keeps_single_bot() -> None:
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot"])
    )
    async with session_scope() as session:
        manager = await _seed_manager(session, "666666:MANAGERTOKEN")
        service = BotFactoryService(
            session,
            session_provider_factory=lambda **kw: provider,
            bot_service=_manager(session),
        )
        batch = await service.create_batch(
            prefix="Mix", count=1, manager_bot_id=manager.id
        )
        await service.check_availability(batch.id)
        await service.enqueue_candidates(batch.id)
        await service.run_queue_once(batch.id)
        rows = await service.list_candidates(batch.id)
        assert rows[0].bot_id
        bot_id = rows[0].bot_id
        # A repeated adoption call (idempotent) does not create a second bot.
        again = await service.adopt_created(batch.id, "mix_1_bot", 8888)
        assert again.bot_id == bot_id
