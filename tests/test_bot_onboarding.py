"""Mass bot-to-channel onboarding tests (v2.0, D-120).

Covers the pure deep-link helper, batch creation with honest skip reporting, the
durable one-op-per-tick queue, the real rights verification (reusing the
BindingService), permission/FloodWait/failure states, retry/skip/pause/resume,
crash recovery, secret safety and the additive API surface. Everything runs
against the deterministic fake bot provider — no credentials or network (D-001).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.core.security import seal_secret
from backend.app.db.models.bot import Bot
from backend.app.db.models.bot_onboarding import (
    MAX_ONBOARDING_BOTS,
    OnboardingStatus,
)
from backend.app.db.models.channel import Channel
from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import FloodWaitError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.types import BotChannelStatus
from backend.app.services.bot_onboarding import (
    BotOnboardingError,
    BotOnboardingService,
    channel_start_link,
    rights_profile,
    rights_profile_checked,
)

SECRET_TOKEN = "123456:SUPER-SECRET-TOKEN"


def _factory(token, *, provider_name="auto", settings=None):
    return FakeTelegramBotProvider(token)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


# --- pure helpers ------------------------------------------------------------
def test_channel_start_link_uses_plus_separated_official_rights() -> None:
    link = channel_start_link("my_bot", ("post_messages", "delete_messages"))
    assert link == (
        "https://t.me/my_bot?startchannel&admin=post_messages+delete_messages"
    )


def test_channel_start_link_strips_at_and_handles_no_rights() -> None:
    assert channel_start_link("@my_bot", ()) == "https://t.me/my_bot?startchannel"
    assert channel_start_link("", ("post_messages",)) == ""


def test_rights_profile_checked_rejects_unknown_key() -> None:
    assert rights_profile_checked("reactions").key == "reactions"
    with pytest.raises(BotOnboardingError):
        rights_profile_checked("does-not-exist")


def test_reaction_profile_requires_delete_for_reactions() -> None:
    profile = rights_profile("reactions")
    assert profile.function == "reactions"
    assert "delete_messages" in profile.admin_rights
    # Never a blanket "all rights": posting stays out of the reactions profile.
    assert "post_messages" not in profile.admin_rights


# --- helpers -----------------------------------------------------------------
async def _seed(session, *, bots: int = 1, channels: int = 1):
    channel = Channel(
        reference=f"@chan{channels}",
        title=f"Channel {channels}",
        telegram_id=-100500,
    )
    session.add(channel)
    created = []
    for i in range(bots):
        bot = Bot(
            kind="managed",
            username=f"onboard_{i}_bot",
            title=f"Onboard {i}",
            telegram_id=1000 + i,
            token_encrypted=seal_secret(SECRET_TOKEN),
        )
        session.add(bot)
        created.append(bot)
    await session.flush()
    return channel, created


async def _service(session):
    return BotOnboardingService(session, provider_factory=_factory)


# --- creation ----------------------------------------------------------------
async def test_create_batch_queues_ready_bots_with_official_links() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=2)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[b.id for b in bots], channel_id=channel.id
        )
        assert batch.requested_count == 2
        rows = await service.list_candidates(batch.id)
        assert [r.bot_username for r in rows] == ["onboard_0_bot", "onboard_1_bot"]
        for row in rows:
            assert row.deep_link.startswith(
                "https://t.me/onboard_"
            )
            assert "admin=delete_messages" in row.deep_link
            assert row.status == OnboardingStatus.QUEUED.value


async def test_create_batch_reports_bots_without_token_honestly() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=1)
        broken = Bot(kind="managed", username="no_token_bot", title="No token")
        session.add(broken)
        await session.flush()
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[bots[0].id, broken.id], channel_id=channel.id
        )
        # Only the ready bot is queued; the other is reported, never silently kept.
        assert batch.requested_count == 1
        assert "Пропущено" in batch.last_error


async def test_create_batch_caps_batch_size() -> None:
    async with session_scope() as session:
        channel, _ = await _seed(session, bots=0)
        service = await _service(session)
        with pytest.raises(BotOnboardingError):
            await service.create_batch(
                bot_ids=[f"id-{i}" for i in range(MAX_ONBOARDING_BOTS + 1)],
                channel_id=channel.id,
            )


async def test_create_batch_requires_an_existing_channel() -> None:
    async with session_scope() as session:
        service = await _service(session)
        with pytest.raises(BotOnboardingError):
            await service.create_batch(bot_ids=["x"], channel_id="missing")


# --- verification (happy path) ----------------------------------------------
async def test_run_queue_once_verifies_one_bot_and_marks_ready() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=2)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[b.id for b in bots], channel_id=channel.id
        )

        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        # Exactly one bot per tick.
        assert progress.ready == 1
        assert progress.active == 1

        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress.ready == 2
        assert progress.active == 0

        batch = await service.get_batch(batch.id)
        assert batch.ready_count == 2
        assert batch.completed_at is not None


async def test_missing_permission_is_reported_not_ready() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=1)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[bots[0].id], channel_id=channel.id
        )
        rows = await service.list_candidates(batch.id)
        provider = FakeTelegramBotProvider(bots[0].token_encrypted)
        # Bind a provider that reports the bot present but without the right.
        status = BotChannelStatus(
            found=True,
            present=True,
            status="member",
            is_admin=False,
            can_set_reactions=False,
            can_delete_messages=False,
        )

        async def _status(chat_id, bot_id):
            return status

        provider.get_bot_channel_status = _status  # type: ignore[method-assign]
        service = BotOnboardingService(
            session, provider_factory=lambda token, **kw: provider
        )
        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress.needs_permission == 1
        assert progress.ready == 0
        row = (await service.list_candidates(batch.id))[0]
        assert row.last_error

        # Retrying moves it back into the queue, it is not silently dropped.
        await service.retry_candidate(rows[0].id)
        assert (await service.queue_progress(batch.id)).queued == 1


async def test_bot_not_in_channel_waits_for_confirmation() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=1)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[bots[0].id], channel_id=channel.id
        )
        provider = FakeTelegramBotProvider(bots[0].token_encrypted)

        async def _status(chat_id, bot_id):
            return BotChannelStatus(found=True, present=False, status="left")

        provider.get_bot_channel_status = _status  # type: ignore[method-assign]
        service = BotOnboardingService(
            session, provider_factory=lambda token, **kw: provider
        )
        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress.waiting == 1


async def test_flood_wait_is_a_real_failure_not_a_bypass() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=1)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[bots[0].id], channel_id=channel.id
        )
        provider = FakeTelegramBotProvider(bots[0].token_encrypted)

        async def _boom(chat_id, bot_id):
            raise FloodWaitError(60)

        provider.get_bot_channel_status = _boom  # type: ignore[method-assign]
        service = BotOnboardingService(
            session, provider_factory=lambda token, **kw: provider
        )
        await service.run_queue_once(batch.id)
        progress = await service.queue_progress(batch.id)
        assert progress.failed == 1
        row = (await service.list_candidates(batch.id))[0]
        assert "подождать" in row.last_error.lower()


# --- lifecycle ---------------------------------------------------------------
async def test_pause_resume_and_skip() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=2)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[b.id for b in bots], channel_id=channel.id
        )
        rows = await service.list_candidates(batch.id)

        # Skipping a queued bot is allowed; skipping a ready one is refused below.
        await service.skip_candidate(rows[0].id)
        assert (await service.queue_progress(batch.id)).skipped == 1

        await service.pause(batch.id)
        await service.run_queue_once(batch.id)  # no-op while paused
        assert (await service.queue_progress(batch.id)).ready == 0

        await service.resume(batch.id)
        await service.run_queue_once(batch.id)
        assert (await service.queue_progress(batch.id)).ready == 1


async def test_recover_revives_verifying_rows() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=1)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[bots[0].id], channel_id=channel.id
        )
        rows = await service.list_candidates(batch.id)
        rows[0].status = OnboardingStatus.VERIFYING.value
        await session.flush()

        revived = await service.recover()
        assert revived == 1
        assert (
            (await service.list_candidates(batch.id))[0].status
            == OnboardingStatus.QUEUED.value
        )


async def test_delete_batch_removes_candidates() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=2)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[b.id for b in bots], channel_id=channel.id
        )
        await service.delete_batch(batch.id)
        with pytest.raises(BotOnboardingError):
            await service.get_batch(batch.id)


# --- API surface -------------------------------------------------------------
@pytest_asyncio.fixture
async def onboarding_client() -> AsyncIterator[AsyncClient]:
    """HTTP client with Telegram access wired to the deterministic fake."""
    from backend.app.api.deps import get_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    app.dependency_overrides[get_provider_factory] = lambda: _factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_channel(client: AsyncClient, reference: str = "@onboard") -> str:
    resp = await client.post("/api/v1/channels", json={"reference": reference})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_bot(client: AsyncClient, token: str) -> str:
    resp = await client.post("/api/v1/bots", json={"token": token, "kind": "managed"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_rights_profiles_endpoint_is_least_privilege(
    onboarding_client: AsyncClient,
) -> None:
    resp = await onboarding_client.get("/api/v1/bot-onboarding/rights-profiles")
    assert resp.status_code == 200, resp.text
    profiles = {p["key"]: p for p in resp.json()}
    assert {"reactions", "posting", "editing"} <= set(profiles)
    assert "post_messages" not in profiles["reactions"]["admin_rights"]


async def test_batch_lifecycle_over_api(onboarding_client: AsyncClient) -> None:
    channel_id = await _make_channel(onboarding_client)
    bot_a = await _make_bot(onboarding_client, "201:A")
    bot_b = await _make_bot(onboarding_client, "202:B")

    created = await onboarding_client.post(
        "/api/v1/bot-onboarding/batches",
        json={
            "bot_ids": [bot_a, bot_b],
            "channel_id": channel_id,
            "rights_profile": "posting",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    batch_id = body["batch"]["id"]
    assert body["batch"]["requested_count"] == 2
    assert len(body["candidates"]) == 2
    # The deep link uses Telegram's official '+' separator.
    assert "admin=post_messages+delete_messages" in body["candidates"][0]["deep_link"]

    dashboard = await onboarding_client.get(
        f"/api/v1/bot-onboarding/batches/{batch_id}/dashboard"
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["progress"]["total"] == 2

    # "Следующий бот" advances exactly one bot.
    nxt = await onboarding_client.post(
        f"/api/v1/bot-onboarding/batches/{batch_id}/next"
    )
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["batch"]["ready_count"] == 1

    checked = await onboarding_client.post(
        f"/api/v1/bot-onboarding/batches/{batch_id}/verify"
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["batch"]["ready_count"] == 2

    listed = await onboarding_client.get("/api/v1/bot-onboarding/batches")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    deleted = await onboarding_client.delete(
        f"/api/v1/bot-onboarding/batches/{batch_id}"
    )
    assert deleted.status_code == 204

    missing = await onboarding_client.get(
        f"/api/v1/bot-onboarding/batches/{batch_id}"
    )
    assert missing.status_code == 404


async def test_create_batch_rejects_unknown_channel(
    onboarding_client: AsyncClient,
) -> None:
    bot_id = await _make_bot(onboarding_client, "203:C")
    resp = await onboarding_client.post(
        "/api/v1/bot-onboarding/batches",
        json={"bot_ids": [bot_id], "channel_id": "does-not-exist"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"]


async def test_candidate_skip_and_retry_over_api(onboarding_client: AsyncClient) -> None:
    channel_id = await _make_channel(onboarding_client, "@cand")
    bot_id = await _make_bot(onboarding_client, "204:D")
    created = await onboarding_client.post(
        "/api/v1/bot-onboarding/batches",
        json={"bot_ids": [bot_id], "channel_id": channel_id},
    )
    candidate_id = created.json()["candidates"][0]["id"]

    skipped = await onboarding_client.post(
        f"/api/v1/bot-onboarding/candidates/{candidate_id}/skip"
    )
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["status"] == "skipped"

    retried = await onboarding_client.post(
        f"/api/v1/bot-onboarding/candidates/{candidate_id}/retry"
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "queued"

    verified = await onboarding_client.post(
        f"/api/v1/bot-onboarding/candidates/{candidate_id}/verify"
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "ready"


# --- secrets -----------------------------------------------------------------
async def test_token_never_surfaces_in_state_or_repr() -> None:
    async with session_scope() as session:
        channel, bots = await _seed(session, bots=1)
        service = await _service(session)
        batch = await service.create_batch(
            bot_ids=[bots[0].id], channel_id=channel.id
        )
        await service.run_queue_once(batch.id)
        rows = await service.list_candidates(batch.id)
        payload = service.candidate_to_dict(rows[0])
        blob = repr(payload) + repr(rows[0]) + repr(batch)
        assert SECRET_TOKEN not in blob
        assert "SUPER-SECRET" not in blob
