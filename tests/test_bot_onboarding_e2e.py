"""v2.0 mass bot-to-channel onboarding — queue integration on a fake provider.

One mixed queue is driven through the *real* ``BotOnboardingService`` and the
*real* ``BindingService`` against a deterministic fake Telegram provider, so the
whole onboarding path is exercised end to end:

* several bots connected successfully;
* a bot that is present but lacks the right (needs permission);
* a bot whose check fails, then is retried and succeeds;
* a bot that is skipped;
* a queue that survives a "restart" (crash mid-verify → ``recover()`` → resumes).

No real user or channel is ever contacted; the provider never does I/O.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.core.security import seal_secret
from backend.app.db.models.binding import BindingStatus
from backend.app.db.models.bot import Bot
from backend.app.db.models.bot_onboarding import OnboardingStatus
from backend.app.db.models.channel import Channel
from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import FloodWaitError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.types import BotChannelStatus
from backend.app.services.binding_service import BindingService
from backend.app.services.bot_onboarding import BotOnboardingService

pytestmark = pytest.mark.asyncio

SECRET_TOKEN = "123456:SUPER-SECRET-TOKEN"

_READY = BotChannelStatus(
    found=True,
    present=True,
    status="administrator",
    is_admin=True,
    can_set_reactions=True,
    can_delete_messages=True,
    can_post_messages=True,
    can_edit_messages=True,
)
_MEMBER_NO_RIGHT = BotChannelStatus(
    found=True,
    present=True,
    status="member",
    is_admin=False,
    can_set_reactions=False,
    can_delete_messages=True,
)
# Telegram id → the channel status the fake returns for that bot.
_STATUS_BY_BOT: dict[int, BotChannelStatus] = {
    2001: _READY,
    2002: _READY,
    2003: _MEMBER_NO_RIGHT,
    2004: _READY,  # will be made to fail first, then succeed
    2005: _READY,
}


def _make_provider() -> FakeTelegramBotProvider:
    provider = FakeTelegramBotProvider(SECRET_TOKEN)

    async def _status(chat_id, bot_id):  # type: ignore[no-untyped-def]
        if int(bot_id) == 2004 and provider.fail_posting is False and _fail_once["armed"]:
            _fail_once["armed"] = False
            raise FloodWaitError(60)
        return _STATUS_BY_BOT.get(int(bot_id), _READY)

    provider.get_bot_channel_status = _status  # type: ignore[method-assign]
    return provider


_fail_once = {"armed": False}


@pytest_asyncio.fixture(autouse=True)
async def _models() -> None:
    _fail_once["armed"] = False
    await init_models()


async def _seed(session) -> tuple[Channel, list[Bot]]:
    channel = Channel(
        reference="@mass", title="Mass Канал", username="mass", telegram_id=-100500
    )
    session.add(channel)
    bots: list[Bot] = []
    for i, tg in enumerate((2001, 2002, 2003, 2004, 2005)):
        bot = Bot(
            kind="managed",
            username=f"mass_{i}_bot",
            title=f"Mass {i}",
            telegram_id=tg,
            token_encrypted=seal_secret(SECRET_TOKEN),
        )
        session.add(bot)
        bots.append(bot)
    await session.flush()
    return channel, bots


async def test_mixed_queue_success_permission_error_retry_skip_and_binding() -> None:
    provider = _make_provider()
    factory = lambda token, **kw: provider  # noqa: E731
    async with session_scope() as session:
        channel, bots = await _seed(session)
        service = BotOnboardingService(session, provider_factory=factory)
        batch = await service.create_batch(
            bot_ids=[b.id for b in bots], channel_id=channel.id
        )
        rows = await service.list_candidates(batch.id)
        # Give up front: 2004's first check must fail.
        _fail_once["armed"] = True
        # Skip the last candidate up front.
        await service.skip_candidate(rows[4].id)

        # Drain the queue one bot per tick (bounded, restart-safe).
        for _ in range(6):
            await service.run_queue_once(batch.id)

        progress = await service.queue_progress(batch.id)
        assert progress.ready == 2, progress.as_dict()
        assert progress.needs_permission == 1, progress.as_dict()
        assert progress.failed == 1, progress.as_dict()
        assert progress.skipped == 1, progress.as_dict()
        assert progress.active == 0

        # Retry the failed bot (2004): the fake now returns ready.
        failed_row = next(
            r for r in await service.list_candidates(batch.id)
            if r.status == OnboardingStatus.FAILED.value
        )
        assert "подождать" in failed_row.last_error.lower()
        await service.retry_candidate(failed_row.id)
        await service.run_queue_once(batch.id)
        assert (await service.queue_progress(batch.id)).ready == 3

        # Verify the outcome through the *Binding Service* for every ready bot.
        binding_service = BindingService(session, provider_factory=factory)
        ready_rows = [
            r for r in await service.list_candidates(batch.id)
            if r.status == OnboardingStatus.READY.value
        ]
        assert len(ready_rows) == 3
        for row in ready_rows:
            assert row.binding_id
            binding = await binding_service.get(row.binding_id)
            assert binding is not None
            assert binding.channel_id == channel.id
            assert binding.bot_id == row.bot_id
            assert binding.function == batch.function == "reactions"
            assert binding.status is BindingStatus.READY
            # A fresh independent check agrees with the stored state.
            check = await binding_service.check(binding.id)
            assert str(check.status) == "ready"

        # The batch is settled and completed once its active queue drained.
        done = await service.get_batch(batch.id)
        assert done.completed_at is not None
        assert done.ready_count == 3
        assert done.failed_count == 0  # the retried bot is no longer failed


async def test_queue_resumes_after_a_restart_without_duplicates() -> None:
    provider = _make_provider()
    factory = lambda token, **kw: provider  # noqa: E731
    async with session_scope() as session:
        channel, bots = await _seed(session)
        service = BotOnboardingService(session, provider_factory=factory)
        batch = await service.create_batch(
            bot_ids=[bots[0].id, bots[1].id, bots[3].id], channel_id=channel.id
        )

        # One bot verified, then the process "dies" mid-verify on the next.
        await service.run_queue_once(batch.id)
        rows = await service.list_candidates(batch.id)
        stuck = rows[1]
        stuck.status = OnboardingStatus.VERIFYING.value
        await session.flush()

        # Recovery (on startup) must revive the stuck row, not drop or duplicate it.
        revived = await service.recover()
        assert revived == 1
        assert (
            (await service.list_candidates(batch.id))[1].status
            == OnboardingStatus.QUEUED.value
        )

        # Resume: the queue completes with exactly one binding per bot.
        for _ in range(4):
            await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress.ready == 3
        assert progress.active == 0

        rows = await service.list_candidates(batch.id)
        binding_ids = [r.binding_id for r in rows]
        assert all(binding_ids)
        assert len(set(binding_ids)) == 3  # no duplicate bindings

        # No secret ever leaks into the serialized state.
        for row in rows:
            blob = str(service.result_dict(row)) + repr(row)
            assert SECRET_TOKEN not in blob


__all__: list[str] = []
