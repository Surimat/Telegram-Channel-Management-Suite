"""Unified channel state overview tests (D-127).

The overview is a read-only aggregation over data that already exists, so these
tests seed *real* rows (channels, bindings, audience sources, invite jobs, bot
queues, content, durable jobs, events) in the temporary SQLite DB and assert the
derived per-channel attention level. Nothing is mocked: the service reads the
same tables the modules write.
"""

from __future__ import annotations

import pytest

from backend.app.db.base import new_id
from backend.app.db.models.audience import AudienceSource, ScanStatus
from backend.app.db.models.binding import BindingStatus, BotChannelBinding
from backend.app.db.models.bot import Bot, BotKind
from backend.app.db.models.bot_factory import BatchStatus, BotBatch, BotCandidate, QueueState
from backend.app.db.models.bot_onboarding import OnboardingBatch
from backend.app.db.models.channel import Channel, ChannelKind, ChannelStatus
from backend.app.db.models.content import (
    ContentItem,
    ContentItemStatus,
    ContentSource,
    Publication,
    PublicationStatus,
)
from backend.app.db.models.content_ops import ContentOperation
from backend.app.db.models.event import Event, EventLevel
from backend.app.db.models.invite import InviteJob, InviteJobStatus
from backend.app.db.models.job import Job, JobStatus
from backend.app.db.models.post import Post
from backend.app.db.session import init_models, session_scope
from backend.app.services.channel_overview import (
    ATTENTION_ERROR,
    ATTENTION_INFO,
    ATTENTION_OK,
    ATTENTION_WARNING,
    ChannelOverviewService,
)

CHANNELS = "/api/v1/channels"


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


async def _seed_channel(
    *, status: ChannelStatus = ChannelStatus.VERIFIED, modules: str | None = None
) -> str:
    channel_id = new_id()
    async with session_scope() as session:
        session.add(
            Channel(
                id=channel_id,
                reference="@ov",
                username="ov",
                title="Канал обзора",
                kind=ChannelKind.CHANNEL,
                status=status,
                **({"modules": modules} if modules is not None else {}),
            )
        )
    return channel_id


async def _seed_bot(username: str = "helper_bot") -> str:
    bot_id = new_id()
    async with session_scope() as session:
        session.add(Bot(id=bot_id, kind=BotKind.MANAGED, username=username, title="Helper"))
    return bot_id


async def _overview() -> dict:
    async with session_scope() as session:
        return await ChannelOverviewService(session).build()


def _channel(report: dict, channel_id: str) -> dict:
    return next(c for c in report["channels"] if c["id"] == channel_id)


# --- empty install ----------------------------------------------------------
async def test_empty_overview_is_honest_and_ok() -> None:
    report = await _overview()
    assert report["channels"] == []
    assert report["totals"]["channels"] == 0
    assert report["attention"]["level"] == ATTENTION_OK
    # An empty install is never an error.
    assert report["events"]["status"] == ATTENTION_OK


# --- per-section levels -----------------------------------------------------
async def test_ready_bot_binding_is_ok() -> None:
    channel_id = await _seed_channel()
    bot_id = await _seed_bot()
    async with session_scope() as session:
        session.add(
            BotChannelBinding(
                bot_id=bot_id, channel_id=channel_id, status=BindingStatus.READY
            )
        )
    report = await _overview()
    item = _channel(report, channel_id)
    assert item["bindings"]["status"] == ATTENTION_OK
    assert item["bindings"]["counts"]["ready"] == 1
    assert item["attention"]["level"] == ATTENTION_OK


async def test_binding_needs_permission_warns() -> None:
    channel_id = await _seed_channel()
    bot_id = await _seed_bot()
    async with session_scope() as session:
        session.add(
            BotChannelBinding(
                bot_id=bot_id, channel_id=channel_id, status=BindingStatus.NEEDS_PERMISSION
            )
        )
    item = _channel(await _overview(), channel_id)
    assert item["bindings"]["status"] == ATTENTION_WARNING
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_failed_publication_is_error() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(
            Publication(
                channel_id=channel_id,
                status=PublicationStatus.FAILED,
            )
        )
    item = _channel(await _overview(), channel_id)
    assert item["content"]["status"] == ATTENTION_ERROR
    assert item["attention"]["level"] == ATTENTION_ERROR


async def test_needs_review_is_warning() -> None:
    channel_id = await _seed_channel()
    source_id = new_id()
    async with session_scope() as session:
        session.add(ContentSource(id=source_id, channel_id=channel_id, title="Источник"))
        session.add(
            ContentItem(
                source_id=source_id,
                status=ContentItemStatus.NEEDS_REVIEW,
            )
        )
    item = _channel(await _overview(), channel_id)
    assert item["content"]["status"] == ATTENTION_WARNING
    assert item["content"]["counts"]["needs_review"] == 1
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_scheduled_publication_is_info() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(Publication(channel_id=channel_id, status=PublicationStatus.SCHEDULED))
    item = _channel(await _overview(), channel_id)
    assert item["content"]["status"] == ATTENTION_INFO
    assert item["attention"]["level"] == ATTENTION_INFO


async def test_audience_scan_failed_warns() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(AudienceSource(channel_id=channel_id, scan_status=ScanStatus.FAILED))
    item = _channel(await _overview(), channel_id)
    assert item["audience"]["status"] == ATTENTION_WARNING
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_active_audience_scan_is_info() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(AudienceSource(channel_id=channel_id, scan_status=ScanStatus.SCANNING))
    item = _channel(await _overview(), channel_id)
    assert item["audience"]["status"] == ATTENTION_INFO
    assert item["attention"]["level"] == ATTENTION_INFO


async def test_failed_invite_warns() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(InviteJob(channel_id=channel_id, status=InviteJobStatus.FAILED))
    item = _channel(await _overview(), channel_id)
    assert item["invites"]["status"] == ATTENTION_WARNING
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_factory_failed_is_error() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(
            BotBatch(
                channel_id=channel_id,
                status=BatchStatus.CREATING,
                created_count=1,
                failed_count=2,
            )
        )
    item = _channel(await _overview(), channel_id)
    assert item["bots"]["status"] == ATTENTION_ERROR
    assert item["bots"]["counts"]["factory_failed"] == 2
    assert item["attention"]["level"] == ATTENTION_ERROR


async def test_factory_pending_is_info() -> None:
    channel_id = await _seed_channel()
    batch_id = new_id()
    async with session_scope() as session:
        session.add(BotBatch(id=batch_id, channel_id=channel_id, status=BatchStatus.CREATING))
        session.add(
            BotCandidate(
                batch_id=batch_id,
                index=1,
                queue_state=QueueState.QUEUED.value,
            )
        )
    item = _channel(await _overview(), channel_id)
    assert item["bots"]["status"] == ATTENTION_INFO
    assert item["bots"]["counts"]["factory_pending"] == 1
    assert item["attention"]["level"] == ATTENTION_INFO


async def test_onboarding_permission_warns() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(
            OnboardingBatch(
                channel_id=channel_id,
                requested_count=3,
                ready_count=1,
                permission_count=1,
            )
        )
    item = _channel(await _overview(), channel_id)
    assert item["bots"]["status"] == ATTENTION_WARNING
    assert item["bots"]["counts"]["onboarding_permission"] == 1
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_ai_unavailable_warns_pipeline() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        session.add(
            ContentOperation(channel_id=channel_id, stage="ai", status="ai_unavailable")
        )
    item = _channel(await _overview(), channel_id)
    assert item["pipeline"]["status"] == ATTENTION_WARNING
    assert item["pipeline"]["counts"]["ai_unavailable"] == 1
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_failed_queue_job_warns() -> None:
    channel_id = await _seed_channel()
    post_id = new_id()
    async with session_scope() as session:
        session.add(Post(id=post_id, registry_channel_id=channel_id))
        session.add(Job(kind="reaction.job", status=JobStatus.FAILED, group_key=post_id))
    item = _channel(await _overview(), channel_id)
    assert item["queue"]["status"] == ATTENTION_WARNING
    assert item["queue"]["counts"]["failed"] == 1
    assert item["attention"]["level"] == ATTENTION_WARNING


async def test_channel_error_status_is_error() -> None:
    channel_id = await _seed_channel(status=ChannelStatus.ERROR)
    item = _channel(await _overview(), channel_id)
    assert item["attention"]["level"] == ATTENTION_ERROR


async def test_error_beats_warning_and_info() -> None:
    channel_id = await _seed_channel()
    async with session_scope() as session:
        # A warning (audience) and an error (content) on the same channel.
        session.add(AudienceSource(channel_id=channel_id, scan_status=ScanStatus.FAILED))
        session.add(Publication(channel_id=channel_id, status=PublicationStatus.FAILED))
    item = _channel(await _overview(), channel_id)
    assert item["attention"]["level"] == ATTENTION_ERROR


async def test_unresolved_channel_event_is_surfaced() -> None:
    await _seed_channel()
    async with session_scope() as session:
        session.add(
            Event(
                module="channels",
                level=EventLevel.ERROR,
                message="Проверка канала не удалась.",
                resolved=False,
            )
        )
    report = await _overview()
    assert report["events"]["status"] == ATTENTION_ERROR
    assert report["events"]["counts"]["unresolved_errors"] == 1
    assert report["attention"]["level"] == ATTENTION_ERROR


# --- module gate ------------------------------------------------------------
async def test_modules_reported_effectively() -> None:
    # Never-configured channel: every module stays enabled (legacy, D-124).
    legacy_id = await _seed_channel()
    legacy = _channel(await _overview(), legacy_id)
    assert {m["id"]: m["enabled"] for m in legacy["modules"]} == {
        "reactions": True,
        "audience": True,
        "invites": True,
        "analytics": True,
    }

    # Configured map: a switched-off module is reported off.
    configured_id = await _seed_channel(modules='{"reactions": false, "audience": true}')
    configured = _channel(await _overview(), configured_id)
    enabled = {m["id"]: m["enabled"] for m in configured["modules"]}
    assert enabled["reactions"] is False
    assert enabled["audience"] is True


# --- safety -----------------------------------------------------------------
async def test_overview_contains_no_secret_token() -> None:
    channel_id = await _seed_channel()
    bot_id = new_id()
    async with session_scope() as session:
        session.add(
            Bot(
                id=bot_id,
                kind=BotKind.MANAGED,
                username="secret_bot",
                token_encrypted="enc:SUPERSECRETTOKENVALUE",
            )
        )
        session.add(BotChannelBinding(bot_id=bot_id, channel_id=channel_id))
    report = await _overview()
    assert "SUPERSECRETTOKENVALUE" not in str(report)


# --- API --------------------------------------------------------------------
async def test_overview_endpoint_returns_shape(client) -> None:  # type: ignore[no-untyped-def]
    created = await client.post(CHANNELS, json={"reference": "@ovapi", "title": "API"})
    assert created.status_code == 201, created.text
    channel_id = created.json()["id"]

    resp = await client.get(f"{CHANNELS}/overview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totals"]["channels"] == 1
    assert body["attention"]["level"] in {"ok", "info", "warning", "error"}
    assert len(body["channels"]) == 1
    item = body["channels"][0]
    assert item["id"] == channel_id
    assert set(item["bindings"]) >= {"status", "label", "counts", "items"}
    assert isinstance(item["modules"], list) and len(item["modules"]) == 4
    # The route must not shadow the {channel_id} route with the literal "overview".
    single = await client.get(f"{CHANNELS}/{channel_id}")
    assert single.status_code == 200
