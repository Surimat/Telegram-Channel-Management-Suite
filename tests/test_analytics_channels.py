"""Per-channel analytics scoping tests (post-1.0 hardening).

Analytics can be scoped to one registry channel (``channel_id`` query param).
When omitted, behaviour is unchanged (global aggregates). These tests seed two
channels and assert the scoped numbers match only that channel's data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ANALYTICS_BASE = "/api/v1/analytics"


@pytest_asyncio.fixture
async def scoped_client() -> AsyncClient:
    from backend.app.db.models.audience import (
        AudienceSource,
        AudienceUser,
        SourceType,
        SourceUserLink,
    )
    from backend.app.db.models.channel import Channel, ChannelKind
    from backend.app.db.models.post import Post, PostStatus
    from backend.app.db.models.reaction import ReactionJob, ReactionJobStatus
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app

    await init_models()
    now = datetime.now(UTC)
    async with session_scope() as session:
        session.add(
            Channel(reference="@alpha", username="alpha", kind=ChannelKind.CHANNEL, id="ch-a")
        )
        session.add(
            Channel(reference="@beta", username="beta", kind=ChannelKind.CHANNEL, id="ch-b")
        )
        session.add(
            Post(
                id="post-a",
                text="Alpha donation",
                category="donation",
                classification_source="rules",
                status=PostStatus.DONE,
                registry_channel_id="ch-a",
                created_at=now - timedelta(days=1),
            )
        )
        session.add(
            Post(
                id="post-b",
                text="Beta news",
                category="news",
                classification_source="rules",
                status=PostStatus.DONE,
                registry_channel_id="ch-b",
                created_at=now - timedelta(days=1),
            )
        )
        session.add(
            ReactionJob(
                post_id="post-a",
                bot_id="b1",
                reaction="❤️",
                status=ReactionJobStatus.DONE,
                created_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
        )
        session.add(
            ReactionJob(
                post_id="post-b",
                bot_id="b2",
                reaction="👍",
                status=ReactionJobStatus.DONE,
                created_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
        )
        session.add(
            AudienceSource(
                id="src-a",
                title="Alpha source",
                username="alpha_src",
                source_type=SourceType.CHANNEL,
                channel_id="ch-a",
            )
        )
        session.add(
            AudienceSource(
                id="src-b",
                title="Beta source",
                username="beta_src",
                source_type=SourceType.CHANNEL,
                channel_id="ch-b",
            )
        )
        session.add(AudienceUser(id="ua", telegram_user_id=1001, username="ua", first_seen_at=now))
        session.add(AudienceUser(id="ub", telegram_user_id=1002, username="ub", first_seen_at=now))
        session.add(SourceUserLink(source_id="src-a", user_id="ua"))
        session.add(SourceUserLink(source_id="src-b", user_id="ub"))

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_global_overview_sees_both_channels(scoped_client: AsyncClient) -> None:
    body = (await scoped_client.get(f"{ANALYTICS_BASE}/overview")).json()
    assert body["channel_id"] == ""
    assert body["headline"]["posts_total"] == 2
    assert body["headline"]["audience_total"] == 2


async def test_content_scoped_to_channel(scoped_client: AsyncClient) -> None:
    body = (
        await scoped_client.get(f"{ANALYTICS_BASE}/content", params={"channel_id": "ch-a"})
    ).json()
    assert body["posts_total"] == 1
    assert {c["key"] for c in body["by_category"]} == {"donation"}


async def test_audience_scoped_to_channel(scoped_client: AsyncClient) -> None:
    body = (
        await scoped_client.get(f"{ANALYTICS_BASE}/audience", params={"channel_id": "ch-b"})
    ).json()
    assert body["audience_total"] == 1
    assert body["sources_total"] == 1
    assert body["top_sources"][0]["username"] == "beta_src"


async def test_overview_scoped_reports_channel_id(scoped_client: AsyncClient) -> None:
    body = (
        await scoped_client.get(f"{ANALYTICS_BASE}/overview", params={"channel_id": "ch-a"})
    ).json()
    assert body["channel_id"] == "ch-a"
    assert body["headline"]["posts_total"] == 1
    assert body["headline"]["audience_total"] == 1
