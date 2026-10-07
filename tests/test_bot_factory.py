"""Bot Factory tests (v1.3).

Covers generation/validation (pure), the availability check against the fake
provider, native creation + token registration, deep-link mode without any user
account, and the honest Telegram-limit messaging. No real credentials or network
are used (D-001).
"""

from __future__ import annotations

import pytest

from backend.app.db.models.bot import BotKind
from backend.app.db.models.bot_factory import (
    BOT_CREATE_LIMIT_NOTE,
    BatchStatus,
    CandidateStatus,
    QueueState,
)
from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import BotCreateLimitError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.fake_session import (
    FakeBotFactoryScenario,
    FakeSessionProvider,
)
from backend.app.services.bot_factory import (
    BotFactoryError,
    BotFactoryService,
    generate_name,
    generate_username,
    manager_deep_link,
    sanitize_prefix,
    validate_username,
)
from backend.app.services.bot_service import BotService


def _bot_factory(token, *, provider_name="auto", settings=None):
    return FakeTelegramBotProvider(token)


def _manager(session):
    return BotService(session, provider_factory=_bot_factory)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


# --- pure helpers ------------------------------------------------------------
def test_sanitize_prefix_keeps_only_allowed_chars():
    assert sanitize_prefix("Mix Media!") == "MixMedia"
    assert sanitize_prefix("  ") == ""


def test_generate_username_is_valid_and_deterministic():
    username = generate_username("{prefix}_{index}_bot", "MixMedia", 3)
    assert username == "mixmedia_3_bot"
    ok, reason = validate_username(username)
    assert ok, reason


def test_generate_username_truncates_and_suffixes_bot():
    username = generate_username("{prefix}_{index}_bot", "A" * 40, 1)
    assert len(username) <= 32
    assert username.endswith("bot")


def test_generate_name_uses_topic_and_style():
    assert generate_name("{prefix} Helper {index}", "Mix", 2) == "Mix Helper 2"
    assert generate_name("{prefix} {index}", "Mix", 2, topic="news").startswith("Mix")


def test_validate_username_rejects_bad_values():
    for bad in ("", "abc", "no_suffix", "1start_bot", "has space bot", "a" * 40):
        ok, _ = validate_username(bad)
        assert not ok, bad
    ok, reason = validate_username("good_name_bot")
    assert ok, reason


def test_manager_deep_link_uses_official_newbot_path():
    link = manager_deep_link("@ctrl_bot", "mix_1_bot", "Mix 1")
    assert link.startswith("https://t.me/newbot/ctrl_bot/mix_1_bot")
    assert "name=Mix" in link
    assert manager_deep_link("", "x_bot") == ""


# --- service (DB) ------------------------------------------------------------
def _factory(provider: FakeSessionProvider):
    def _build(**kwargs):  # type: ignore[no-untyped-def]
        return provider
    return _build


def _service(session, provider: FakeSessionProvider | None = None) -> BotFactoryService:
    """Bot Factory wired to fakes for both bot and user-session providers."""
    return BotFactoryService(
        session,
        session_provider_factory=_factory(provider) if provider is not None else None,
        bot_service=_manager(session),
    )


async def _seed_account():
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


async def test_create_batch_generates_candidates():
    async with session_scope() as session:
        service = BotFactoryService(session)
        batch = await service.create_batch(prefix="MixMedia", count=3, topic="news")
        assert batch.status is BatchStatus.DRAFT
        assert batch.requested_count == 3
        assert batch.note == BOT_CREATE_LIMIT_NOTE
        rows = await service.list_candidates(batch.id)
        assert len(rows) == 3
        assert [r.suggested_username for r in rows] == [
            "mixmedia_1_bot",
            "mixmedia_2_bot",
            "mixmedia_3_bot",
        ]
        assert all(r.creation_status is CandidateStatus.GENERATED for r in rows)


async def test_create_batch_requires_prefix_and_count():
    async with session_scope() as session:
        service = BotFactoryService(session)
        with pytest.raises(BotFactoryError):
            await service.create_batch(prefix="", count=2)
        with pytest.raises(BotFactoryError):
            await service.create_batch(prefix="Mix", count=0)
        with pytest.raises(BotFactoryError):
            await service.create_batch(prefix="Mix", count=999)


async def test_check_availability_marks_free_and_taken():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(
            available=["mixmedia_1_bot", "mixmedia_3_bot"]
        )
    )
    async with session_scope() as session:
        service = _service(session, provider)
        batch = await service.create_batch(prefix="MixMedia", count=3)
        await service.check_availability(batch.id)
        rows = await service.list_candidates(batch.id)
        by_user = {r.suggested_username: r for r in rows}
        assert by_user["mixmedia_1_bot"].creation_status is CandidateStatus.AVAILABLE
        assert by_user["mixmedia_2_bot"].creation_status is CandidateStatus.OCCUPIED
        assert by_user["mixmedia_3_bot"].username_status == "available"
        assert by_user["mixmedia_2_bot"].username_status == "occupied"


async def test_check_availability_requires_account():
    async with session_scope() as session:
        service = _service(session)
        batch = await service.create_batch(prefix="Mix", count=1)
        with pytest.raises(BotFactoryError) as exc:
            await service.check_availability(batch.id)
        assert "аккаунт" in exc.value.message.lower()


async def test_regenerate_candidate_bumps_index():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot"])
    )
    async with session_scope() as session:
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=1)
        rows = await service.list_candidates(batch.id)
        row = await service.regenerate_candidate(rows[0].id)
        assert row.suggested_username == "mix_2_bot"
        assert row.creation_status is CandidateStatus.GENERATED


async def test_native_creation_registers_bot_and_token():
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot", "mix_2_bot"])
    )
    await _seed_account()
    async with session_scope() as session:
        # A manager bot is required to fetch tokens.
        manager = await _manager(session).add_bot(
            "777777:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=2, manager_bot_id=manager.id)
        await service.check_availability(batch.id)
        batch = await service.create_batch_bots(batch.id)
        assert batch.created_count == 2
        assert batch.status is BatchStatus.COMPLETED
        rows = await service.list_candidates(batch.id)
        assert all(r.creation_status is CandidateStatus.CREATED for r in rows)
        assert all(r.bot_id for r in rows)
        assert all(r.telegram_id for r in rows)
        # Tokens are fetched via the manager and sealed; never returned.
        result = await service.register_tokens(batch.id)
        assert result["imported"] == 2
        rows = await service.list_candidates(batch.id)
        assert all(r.creation_status is CandidateStatus.TOKEN_IMPORTED for r in rows)
        for row in rows:
            bot = await _manager(session).get(row.bot_id)
            assert bot is not None
            assert bot.has_token
            assert bot.token_encrypted  # sealed, not plaintext


async def test_deeplink_mode_without_account_keeps_links():
    async with session_scope() as session:
        service = _service(session)
        manager = await _manager(session).add_bot(
            "888888:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        batch = await service.create_batch(prefix="Mix", count=2, manager_bot_id=manager.id)
        batch = await service.create_batch_bots(batch.id, via_deeplink=True)
        rows = await service.list_candidates(batch.id)
        assert batch.status is BatchStatus.READY
        assert all(r.deep_link.startswith("https://t.me/newbot/") for r in rows)
        assert all(r.creation_status is CandidateStatus.GENERATED for r in rows)


async def test_adopt_created_registers_deeplink_bot():
    async with session_scope() as session:
        service = _service(session)
        manager = await _manager(session).add_bot(
            "999999:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        batch = await service.create_batch(prefix="Mix", count=1, manager_bot_id=manager.id)
        row = await service.adopt_created(
            batch.id, "mix_1_bot", 123456, title="Mix One"
        )
        assert row.creation_status is CandidateStatus.CREATED
        assert row.bot_id
        bot = await _manager(session).get(row.bot_id)
        assert bot is not None and bot.kind is BotKind.MANAGED


async def test_creation_limit_error_is_reported_honestly():
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(
            available=["mix_1_bot"],
            create_error=BotCreateLimitError(),
        )
    )
    await _seed_account()
    async with session_scope() as session:
        service = _service(session, provider)
        manager = await _manager(session).add_bot(
            "555555:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        batch = await service.create_batch(prefix="Mix", count=1, manager_bot_id=manager.id)
        await service.check_availability(batch.id)
        batch = await service.create_batch_bots(batch.id)
        assert batch.created_count == 0
        assert batch.failed_count == 1
        rows = await service.list_candidates(batch.id)
        assert rows[0].creation_status is CandidateStatus.FAILED
        assert "лимит" in rows[0].error.lower()


async def test_dashboard_reports_counts_and_limit_note():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot"])
    )
    async with session_scope() as session:
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=2)
        await service.check_availability(batch.id)
        data = await service.dashboard(batch.id)
        assert data["counts"]["available"] == 1
        assert data["counts"]["occupied"] == 1
        assert data["limit_note"] == BOT_CREATE_LIMIT_NOTE


async def test_delete_batch_removes_candidates():
    async with session_scope() as session:
        service = BotFactoryService(session)
        batch = await service.create_batch(prefix="Mix", count=2)
        await service.delete_batch(batch.id)
        with pytest.raises(BotFactoryError):
            await service.get_batch(batch.id)


# --- creation queue (v1.7) ---------------------------------------------------
async def test_enqueue_marks_free_candidates_queued():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot", "mix_3_bot"])
    )
    async with session_scope() as session:
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=3)
        await service.check_availability(batch.id)
        await service.enqueue_candidates(batch.id)
        rows = await service.list_candidates(batch.id)
        by_user = {r.suggested_username: r for r in rows}
        assert by_user["mix_1_bot"].queue_state == QueueState.QUEUED.value
        assert by_user["mix_3_bot"].queue_state == QueueState.QUEUED.value
        # The occupied one is never queued (it is skipped during the check).
        assert by_user["mix_2_bot"].queue_state != QueueState.QUEUED.value
        progress = await service.queue_progress(batch.id)
        assert progress["queued"] == 2


async def test_run_queue_once_creates_one_bot_per_pass():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot", "mix_2_bot"])
    )
    async with session_scope() as session:
        manager = await _manager(session).add_bot(
            "111111:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=2, manager_bot_id=manager.id)
        await service.check_availability(batch.id)
        await service.enqueue_candidates(batch.id)

        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress["success"] == 1
        assert progress["queued"] == 1

        # Drain the rest — the batch settles as completed.
        await service.run_queue_once(batch.id)
        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress["success"] == 2
        assert progress["queued"] == 0
        batch = await service.get_batch(batch.id)
        assert batch.status is BatchStatus.COMPLETED


async def test_retry_and_skip_candidate():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(
            available=["mix_1_bot"], create_error=BotCreateLimitError()
        )
    )
    async with session_scope() as session:
        manager = await _manager(session).add_bot(
            "222222:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=1, manager_bot_id=manager.id)
        await service.check_availability(batch.id)
        await service.enqueue_candidates(batch.id)
        await service.run_queue_once(batch.id)
        rows = await service.list_candidates(batch.id)
        row = rows[0]
        assert row.queue_state == QueueState.FAILED.value

        # Retry re-queues the failed operation and bumps the attempt counter.
        row = await service.retry_candidate(row.id)
        assert row.queue_state == QueueState.QUEUED.value
        assert row.creation_status is CandidateStatus.READY

        # Skip ends it without touching the rest of the queue.
        row = await service.skip_candidate(row.id)
        assert row.queue_state == QueueState.SKIPPED.value
        batch = await service.get_batch(batch.id)
        assert batch.skipped_count == 1


async def test_created_candidate_cannot_be_retried():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot"])
    )
    async with session_scope() as session:
        manager = await _manager(session).add_bot(
            "333333:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=1, manager_bot_id=manager.id)
        rows = await service.list_candidates(batch.id)
        await service.adopt_created(batch.id, "mix_1_bot", 4242)
        with pytest.raises(BotFactoryError):
            await service.retry_candidate(rows[0].id)


async def test_cancel_and_resume_queue():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot", "mix_2_bot"])
    )
    async with session_scope() as session:
        manager = await _manager(session).add_bot(
            "444444:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=2, manager_bot_id=manager.id)
        await service.check_availability(batch.id)
        await service.enqueue_candidates(batch.id)

        batch = await service.cancel_queue(batch.id)
        assert batch.queue_cancelled is True
        assert batch.status is BatchStatus.CANCELLED
        # A cancelled queue is a no-op for the durable handler.
        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress["success"] == 0

        batch = await service.resume_queue(batch.id)
        assert batch.queue_cancelled is False
        progress = await service.queue_progress(batch.id)
        assert progress["queued"] == 2


async def test_token_mask_never_contains_full_token():
    await _seed_account()
    provider = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot"])
    )
    async with session_scope() as session:
        manager = await _manager(session).add_bot(
            "666666:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        service = _service(session, provider)
        batch = await service.create_batch(prefix="Mix", count=1, manager_bot_id=manager.id)
        await service.check_availability(batch.id)
        await service.create_batch_bots(batch.id)
        await service.register_tokens(batch.id)
        rows = await service.list_candidates(batch.id)
        assert rows[0].token_mask
        # Only a head/tail shape is shown; the mask is derived from the numeric id,
        # never from the sealed token (D-110).
        assert "…" in rows[0].token_mask
        assert rows[0].token_mask != str(rows[0].telegram_id)


async def test_deeplink_queue_without_account_queues_hand_made_bots():
    async with session_scope() as session:
        service = _service(session)
        manager = await _manager(session).add_bot(
            "999111:MANAGERTOKEN", kind=BotKind.MANAGER, title="Manager"
        )
        batch = await service.create_batch(prefix="Mix", count=2, manager_bot_id=manager.id)
        await service.create_batch_bots(batch.id, via_deeplink=True)
        rows = await service.list_candidates(batch.id)
        assert all(r.queue_state == QueueState.QUEUED.value for r in rows)
        assert all(r.deep_link for r in rows)
