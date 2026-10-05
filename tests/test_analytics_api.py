"""Analytics API tests (PHASE 8).

Exercises the read-only endpoints and asserts the response shape, the
plain-language summaries, and that no secrets/PII leak into analytics responses.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ANALYTICS_BASE = "/api/v1/analytics"

# Words that must never appear in analytics payloads.
_FORBIDDEN = ("api_hash", "token", "password", "session", "phone")


@pytest_asyncio.fixture
async def analytics_client() -> AsyncClient:
    from backend.app.db.models.audience import AudienceSource, AudienceUser, SourceType
    from backend.app.db.models.post import Post, PostStatus
    from backend.app.db.models.reaction import ReactionJob, ReactionJobStatus
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app

    await init_models()
    now = datetime.now(UTC)
    async with session_scope() as session:
        session.add(
            Post(
                text="Донат",
                category="donation",
                category_title="Донат / поддержка",
                classification_source="rules",
                status=PostStatus.DONE,
                created_at=now - timedelta(days=1),
            )
        )
        session.add(
            Post(
                text="Новость",
                category="news",
                category_title="Новости",
                classification_source="llm",
                status=PostStatus.DONE,
                created_at=now - timedelta(days=2),
            )
        )
        session.add(
            ReactionJob(
                post_id="p1",
                bot_id="b1",
                reaction="❤️",
                status=ReactionJobStatus.DONE,
                created_at=now - timedelta(days=1),
                completed_at=now - timedelta(days=1),
            )
        )
        session.add(AudienceSource(title="Канал", username="chan", source_type=SourceType.CHANNEL))
        session.add(AudienceUser(telegram_user_id=9001, username="u1", first_seen_at=now))

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_overview_endpoint(analytics_client: AsyncClient) -> None:
    resp = await analytics_client.get(f"{ANALYTICS_BASE}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["headline"]["posts_total"] == 2
    assert body["headline"]["reactions_total"] == 1
    assert body["headline"]["audience_total"] == 1
    assert isinstance(body["summary"], list) and body["summary"]
    assert body["content"]["summary"]
    assert body["reactions"]["summary"]
    assert body["audience"]["summary"]
    # No user account is connected in this fixture: the overview stays useful
    # but explains that historical data is unavailable to this connection type.
    assert body["account_connected"] is False
    assert "историческая" in body["account_note"].lower()


async def test_content_endpoint(analytics_client: AsyncClient) -> None:
    resp = await analytics_client.get(f"{ANALYTICS_BASE}/content", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7
    assert body["posts_total"] == 2
    assert len(body["per_day"]) == 7
    assert {c["key"] for c in body["by_category"]} == {"donation", "news"}
    # classification source is titled for the UI.
    assert {s["title"] for s in body["by_source"]} == {"Обычные правила", "Мини-ИИ"}


async def test_reactions_endpoint(analytics_client: AsyncClient) -> None:
    resp = await analytics_client.get(f"{ANALYTICS_BASE}/reactions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reactions_total"] == 1
    assert body["success_rate"] == 1.0
    assert body["by_emoji"][0]["reaction"] == "❤️"


async def test_audience_endpoint(analytics_client: AsyncClient) -> None:
    resp = await analytics_client.get(f"{ANALYTICS_BASE}/audience")
    assert resp.status_code == 200
    body = resp.json()
    assert body["audience_total"] == 1
    assert body["sources_total"] == 1
    assert body["top_sources"][0]["username"] == "chan"


async def test_days_validation(analytics_client: AsyncClient) -> None:
    url = f"{ANALYTICS_BASE}/content"
    assert (await analytics_client.get(url, params={"days": 0})).status_code == 422
    assert (await analytics_client.get(url, params={"days": 999})).status_code == 422


async def test_no_secret_or_pii_leak(analytics_client: AsyncClient) -> None:
    for path in ("overview", "content", "reactions", "audience"):
        resp = await analytics_client.get(f"{ANALYTICS_BASE}/{path}")
        assert resp.status_code == 200
        low = resp.text.lower()
        for word in _FORBIDDEN:
            assert word not in low, f"{word!r} leaked into /analytics/{path}"
