"""v1.1 donor discovery service tests (fake provider, no network).

Covers the explainable scoring, the Telegram/manual/web providers, storing
candidates as proposals, the explicit add-to-sources action and comparison.
"""

from __future__ import annotations

import pytest

from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.session import init_models, session_scope
from backend.app.providers.discovery_base import (
    DiscoveredChannel,
    DiscoveryQuery,
    ManualDiscoveryProvider,
    WebDiscoveryProvider,
)
from backend.app.providers.fake_session import FakeDiscoveryScenario, FakeSessionProvider
from backend.app.services.donor_discovery_service import (
    DonorDiscoveryService,
    assess_candidate,
)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def factory_for(provider: FakeSessionProvider):
    def _factory(
        *,
        api_id="",
        api_hash="",
        session_path=None,
        provider_name="auto",
        settings=None,
        proxy=None,
    ):
        provider._session_path = session_path
        return provider

    return _factory


# --- scoring -----------------------------------------------------------------


def test_assess_large_healthy_channel_is_suitable() -> None:
    a = assess_candidate(DiscoveredChannel(username="big", subscribers=5000, avg_views=900))
    assert a.fit == "suitable"
    assert a.confidence == "medium"
    assert "healthy_reach" in a.signals
    assert a.explanations
    assert a.summary


def test_assess_tiny_channel_is_doubtful() -> None:
    a = assess_candidate(DiscoveredChannel(username="tiny", subscribers=50, avg_views=1))
    assert a.fit == "doubtful"
    assert "small" in a.signals
    assert "poor_reach" in a.signals


def test_assess_without_data_is_unknown() -> None:
    a = assess_candidate(DiscoveredChannel())
    assert a.fit == "unknown"
    assert a.confidence == "low"


# --- providers ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_provider_parses_reference() -> None:
    provider = ManualDiscoveryProvider()
    result = await provider.discover(DiscoveryQuery(topic="https://t.me/durov/"))
    assert result.ok is True
    assert result.candidates[0].username == "durov"
    assert result.candidates[0].partial is True


@pytest.mark.asyncio
async def test_manual_provider_requires_text() -> None:
    result = await ManualDiscoveryProvider().discover(DiscoveryQuery())
    assert result.ok is False


@pytest.mark.asyncio
async def test_web_provider_inert_by_default() -> None:
    provider = WebDiscoveryProvider()
    assert provider.available is False
    result = await provider.discover(DiscoveryQuery(topic="x"))
    assert result.ok is False
    assert result.available is False
    assert result.how_to_fix


# --- service -----------------------------------------------------------------


async def _service_with_account(db, channels, **kwargs):
    db.add(UserSession(telegram_user_id=1, username="u", status=SessionStatus.ONLINE, api_id="1"))
    await db.flush()
    provider = FakeSessionProvider(discovery=FakeDiscoveryScenario(channels=channels))
    return DonorDiscoveryService(db, session_provider_factory=factory_for(provider), **kwargs)


async def test_discover_stores_candidates_without_adding_sources() -> None:
    from backend.app.db.repositories.audience import AudienceSourceRepository

    async with session_scope() as db:
        svc = await _service_with_account(
            db,
            [
                {"username": "news1", "title": "News", "subscribers": 5000, "avg_views": 900},
                {"username": "small", "title": "Small", "subscribers": 100},
            ],
        )
        result = await svc.discover(DiscoveryQuery(topic="news"), providers=["telegram"])
        assert result["stored"] == 2
        candidates = await svc.list_candidates()
        assert {c.username for c in candidates} == {"news1", "small"}
        # Discovery is a proposal only — nothing is added to audience sources.
        sources, total = await AudienceSourceRepository(db).list()
        assert total == 0
        assert sources == []


async def test_discover_without_account_reports_honestly() -> None:
    async with session_scope() as db:
        svc = DonorDiscoveryService(db)  # no session provider factory
        result = await svc.discover(DiscoveryQuery(topic="news"), providers=["telegram"])
        report = result["providers"][0]
        assert report["ok"] is False
        assert report["how_to_fix"]


async def test_add_to_sources_is_explicit_and_idempotent() -> None:
    async with session_scope() as db:
        svc = await _service_with_account(
            db, [{"username": "news1", "title": "News", "subscribers": 5000, "avg_views": 900}]
        )
        await svc.discover(DiscoveryQuery(topic="news"), providers=["telegram"])
        candidate = (await svc.list_candidates())[0]
        added = await svc.add_to_sources(candidate.id)
        assert added.added is True
        assert added.added_source_id
        # Calling again returns the same record (no duplicate source).
        again = await svc.add_to_sources(candidate.id)
        assert again.added_source_id == added.added_source_id


async def test_compare_names_best_candidate() -> None:
    async with session_scope() as db:
        svc = await _service_with_account(
            db,
            [
                {"username": "big", "title": "Big", "subscribers": 5000, "avg_views": 900},
                {"username": "tiny", "title": "Tiny", "subscribers": 50, "avg_views": 1},
            ],
        )
        await svc.discover(DiscoveryQuery(topic="x"), providers=["telegram"])
        candidates = await svc.list_candidates()
        result = await svc.compare([c.id for c in candidates])
        assert result["best_title"] == "Big"
        assert result["best_reason"]


async def test_compare_requires_two() -> None:
    async with session_scope() as db:
        svc = DonorDiscoveryService(db)
        with pytest.raises(ValueError):
            await svc.compare(["only-one"])


async def test_provider_status_lists_three_sources() -> None:
    async with session_scope() as db:
        svc = DonorDiscoveryService(db)
        status = svc.provider_status()
        assert {s["name"] for s in status} == {"telegram", "web", "manual"}
        manual = next(s for s in status if s["name"] == "manual")
        assert manual["available"] is True


async def test_clear_removes_candidates() -> None:
    async with session_scope() as db:
        svc = await _service_with_account(
            db, [{"username": "news1", "subscribers": 5000, "avg_views": 900}]
        )
        await svc.discover(DiscoveryQuery(topic="news"), providers=["telegram"])
        deleted = await svc.clear()
        assert deleted == 1
        assert await svc.list_candidates() == []


# --- v1.1: Telegram recommendations + comparison metrics ---------------------


async def test_seed_channel_merges_recommendations_and_dedupes() -> None:
    from backend.app.db.models.session import SessionStatus as _Status
    from backend.app.db.models.session import UserSession as _UserSession

    async with session_scope() as db:
        db.add(_UserSession(telegram_user_id=1, username="u", status=_Status.ONLINE, api_id="1"))
        await db.flush()
        provider = FakeSessionProvider(
            discovery=FakeDiscoveryScenario(
                channels=[{"username": "news1", "subscribers": 5000, "avg_views": 900}],
                recommendations=[
                    {"username": "news1", "subscribers": 5000, "avg_views": 900},
                    {"username": "rec1", "subscribers": 8000, "avg_views": 1200},
                ],
            )
        )
        svc = DonorDiscoveryService(db, session_provider_factory=factory_for(provider))
        result = await svc.discover(
            DiscoveryQuery(topic="news", seed_channel="@news1"), providers=["telegram"]
        )
        # The duplicate (news1 appears in both search and recommendations) is dropped.
        assert result["stored"] == 2
        assert {c.username for c in await svc.list_candidates()} == {"news1", "rec1"}
        report = result["providers"][0]
        assert report["ok"] is True
        assert "рекомендац" in report["message"].lower()


async def test_seed_channel_works_without_keywords() -> None:
    async with session_scope() as db:
        db.add(
            UserSession(telegram_user_id=1, username="u", status=SessionStatus.ONLINE, api_id="1")
        )
        await db.flush()
        provider = FakeSessionProvider(
            discovery=FakeDiscoveryScenario(
                recommendations=[{"username": "rec1", "subscribers": 8000}]
            )
        )
        svc = DonorDiscoveryService(db, session_provider_factory=factory_for(provider))
        result = await svc.discover(DiscoveryQuery(seed_channel="@news1"), providers=["telegram"])
        assert result["stored"] == 1


async def test_candidate_metrics_are_honest() -> None:
    from backend.app.services.donor_discovery_service import candidate_to_dict

    class _Row:
        id = "c1"
        query = "news"
        provider = "telegram"
        provider_title = "Telegram"
        username = "news1"
        title = "News"
        telegram_id = 1
        kind = "channel"
        subscribers = 5000
        avg_views = 1000
        activity = 0.2
        language = "ru"
        fit = "suitable"
        fit_title = "Подходит"
        fit_score = 62.0
        confidence = "medium"
        signals = "[]"
        explanations = "[]"
        summary = "ok"
        added = False
        added_source_id = ""
        partial = False

    data = candidate_to_dict(_Row())
    assert data["reach_ratio"] == 0.2
    assert data["reaction_ratio"] == 0.2
    assert data["score_label"] == "62/100"

    # Without view data the ratio stays 0 (never invented).
    _Row.avg_views = 0
    _Row.activity = 0.0
    data = candidate_to_dict(_Row())
    assert data["reach_ratio"] == 0.0
    assert data["reaction_ratio"] == 0.0
