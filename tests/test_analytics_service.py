"""Analytics service + repository tests (PHASE 8).

Seeds a small, deterministic dataset directly in a temporary SQLite DB and checks
the aggregates and the plain-language summaries. No Telegram, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from backend.app.db.models.audience import (
    AudienceSource,
    AudienceUser,
    SourceType,
    SourceUserLink,
)
from backend.app.db.models.invite import InviteStatus, InviteTask
from backend.app.db.models.post import Post, PostStatus
from backend.app.db.models.reaction import ReactionJob, ReactionJobStatus


@pytest_asyncio.fixture
async def seeded_db():
    from backend.app.db.session import dispose_engine, init_models, session_scope

    await init_models()
    now = datetime.now(UTC)
    async with session_scope() as session:
        # --- posts: 3 in the current window, 1 older, across categories -----
        session.add(
            Post(
                text="Спасибо за донат!",
                category="donation",
                category_title="Донат / поддержка",
                classification_source="rules",
                status=PostStatus.DONE,
                created_at=now - timedelta(days=1),
            )
        )
        session.add(
            Post(
                text="Новость дня",
                category="news",
                category_title="Новости",
                classification_source="llm",
                status=PostStatus.DONE,
                created_at=now - timedelta(days=2),
            )
        )
        session.add(
            Post(
                text="Шутка",
                category="funny",
                category_title="Смешное",
                classification_source="rules",
                status=PostStatus.PLANNED,
                created_at=now - timedelta(days=3),
            )
        )
        session.add(
            Post(
                text="Старый пост",
                category="news",
                category_title="Новости",
                classification_source="rules",
                status=PostStatus.DONE,
                created_at=now - timedelta(days=40),
            )
        )

        # --- reactions: 2 done, 1 failed ------------------------------------
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
        session.add(
            ReactionJob(
                post_id="p2",
                bot_id="b1",
                reaction="👍",
                status=ReactionJobStatus.DONE,
                created_at=now - timedelta(days=2),
                completed_at=now - timedelta(days=2),
            )
        )
        session.add(
            ReactionJob(
                post_id="p3",
                bot_id="b2",
                reaction="🔥",
                status=ReactionJobStatus.FAILED,
                created_at=now - timedelta(days=2),
                error="network",
            )
        )

        # --- audience --------------------------------------------------------
        src = AudienceSource(
            title="Новостной канал",
            username="newschan",
            source_type=SourceType.CHANNEL,
            discovered_count=10,
            new_count=8,
            duplicate_count=2,
            error_count=0,
        )
        session.add(src)
        await session.flush()
        for i in range(4):
            user = AudienceUser(
                telegram_user_id=5000 + i,
                username=f"user{i}",
                first_seen_at=now - timedelta(days=i),
            )
            session.add(user)
            await session.flush()
            session.add(
                SourceUserLink(source_id=src.id, user_id=user.id, discovery_method="participants")
            )

        # --- invites ---------------------------------------------------------
        session.add(
            InviteTask(
                job_id="job1",
                user_id="u1",
                telegram_user_id=5000,
                status=InviteStatus.INVITED,
            )
        )
        session.add(
            InviteTask(
                job_id="job1",
                user_id="u2",
                telegram_user_id=5001,
                status=InviteStatus.PRIVACY,
            )
        )

    async with session_scope() as session:
        yield session
    await dispose_engine()


async def test_content_analytics(seeded_db) -> None:
    from backend.app.services.analytics_service import AnalyticsService

    data = await AnalyticsService(seeded_db).content(days=30)
    assert data["posts_total"] == 4
    assert data["posts_window"] == 3  # the 40-day-old post is excluded
    assert data["posts_previous_window"] == 1  # the 40-day-old post
    assert data["change_percent"] == 200.0
    assert len(data["per_day"]) == 30
    assert sum(p["count"] for p in data["per_day"]) == 3
    cats = {c["key"]: c["count"] for c in data["by_category"]}
    assert cats == {"news": 2, "donation": 1, "funny": 1}
    assert "Всего постов: 4" in data["summary"]


async def test_reactions_analytics(seeded_db) -> None:
    from backend.app.services.analytics_service import AnalyticsService

    data = await AnalyticsService(seeded_db).reactions(days=30)
    assert data["reactions_total"] == 3
    assert data["by_status"][ReactionJobStatus.DONE.value] == 2
    assert data["by_status"][ReactionJobStatus.FAILED.value] == 1
    assert data["success_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert sum(p["count"] for p in data["completed_per_day"]) == 2
    emoji = {e["reaction"] for e in data["by_emoji"]}
    assert emoji == {"❤️", "👍", "🔥"}
    assert "Не удалось: 1" in data["summary"]


async def test_audience_analytics(seeded_db) -> None:
    from backend.app.services.analytics_service import AnalyticsService

    data = await AnalyticsService(seeded_db).audience(days=30)
    assert data["audience_total"] == 4
    assert data["new_7d"] == 4
    assert data["sources_total"] == 1
    assert data["links_total"] == 4
    assert data["top_sources"][0]["username"] == "newschan"
    assert data["top_sources"][0]["users"] == 4
    eff = data["source_effectiveness"][0]
    assert eff["discovered"] == 10
    assert eff["new"] == 8
    assert data["invites"][InviteStatus.INVITED.value] == 1
    assert data["invites"][InviteStatus.PRIVACY.value] == 1
    assert "4 уникальных пользователей" in data["summary"]


async def test_overview_combines_and_explains(seeded_db) -> None:
    from backend.app.services.analytics_service import AnalyticsService

    data = await AnalyticsService(seeded_db).overview(days=30)
    assert data["headline"]["posts_total"] == 4
    assert data["headline"]["reactions_total"] == 3
    assert data["headline"]["audience_total"] == 4
    assert data["headline"]["sources_total"] == 1
    assert data["summary"]
    assert any("Активность заметно выросла" in note for note in data["summary"])
    assert any("Успешность" in note for note in data["summary"])


async def test_empty_database_is_safe(client) -> None:
    """A fresh DB must not error and must explain the empty state."""
    from backend.app.db.session import session_scope
    from backend.app.services.analytics_service import AnalyticsService

    async with session_scope() as session:
        service = AnalyticsService(session)
        content = await service.content(days=30)
        reactions = await service.reactions(days=30)
        audience = await service.audience(days=30)

    assert content["posts_total"] == 0
    assert content["change_percent"] is None
    assert "Постов пока нет" in content["summary"]
    assert reactions["reactions_total"] == 0
    assert reactions["success_rate"] is None
    assert "Реакций пока не было" in reactions["summary"]
    assert audience["audience_total"] == 0
    assert "Аудитория пока не собиралась" in audience["summary"]


async def test_days_are_clamped(seeded_db) -> None:
    from backend.app.services.analytics_service import AnalyticsService

    service = AnalyticsService(seeded_db)
    assert (await service.content(days=0))["days"] == 1
    assert (await service.content(days=9999))["days"] == 365


async def test_percent_change_helpers() -> None:
    from backend.app.services.analytics_service import _percent_change

    assert _percent_change(0, 0) is None
    assert _percent_change(10, 0) == 100.0
    assert _percent_change(15, 10) == 50.0
    assert _percent_change(5, 10) == -50.0
