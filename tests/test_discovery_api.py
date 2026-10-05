"""API tests for donor discovery (v1.1).

The Telegram provider is exercised through the deterministic fake; candidates are
proposals and are only added to audience sources on an explicit request.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

DISCOVERY = "/api/v1/discovery"


@pytest_asyncio.fixture
async def discovery_client() -> AsyncClient:
    from backend.app.api.deps import get_session_provider_factory
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app
    from backend.app.providers.fake_session import FakeDiscoveryScenario, FakeSessionProvider

    await init_models()
    async with session_scope() as db:
        db.add(
            UserSession(
                telegram_user_id=1, username="u", status=SessionStatus.ONLINE, api_id="1"
            )
        )

    provider = FakeSessionProvider(
        discovery=FakeDiscoveryScenario(
            channels=[
                {"username": "news1", "title": "News", "subscribers": 5000, "avg_views": 900},
                {"username": "small", "title": "Small", "subscribers": 50, "avg_views": 1},
            ]
        )
    )

    def _factory(
        *,
        api_id="",
        api_hash="",
        session_path=None,
        provider_name="auto",
        settings=None,
        proxy=None,
    ):
        return provider

    app = create_app()
    app.dependency_overrides[get_session_provider_factory] = lambda: _factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_providers_endpoint_lists_sources(discovery_client: AsyncClient) -> None:
    resp = await discovery_client.get(f"{DISCOVERY}/providers")
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()}
    assert names == {"telegram", "web", "manual"}


async def test_search_requires_topic(discovery_client: AsyncClient) -> None:
    resp = await discovery_client.post(f"{DISCOVERY}/search", json={"topic": ""})
    assert resp.status_code == 400


async def test_search_stores_candidates_and_add_is_explicit(
    discovery_client: AsyncClient,
) -> None:
    search = await discovery_client.post(
        f"{DISCOVERY}/search", json={"topic": "news", "providers": ["telegram"]}
    )
    assert search.status_code == 200
    body = search.json()
    assert body["stored"] == 2
    assert {c["username"] for c in body["candidates"]} == {"news1", "small"}

    listing = await discovery_client.get(f"{DISCOVERY}/candidates")
    items = listing.json()["items"]
    assert len(items) == 2
    assert all(item["added"] is False for item in items)

    candidate_id = next(c["id"] for c in items if c["username"] == "news1")
    added = await discovery_client.post(f"{DISCOVERY}/candidates/{candidate_id}/add")
    assert added.status_code == 200
    assert added.json()["source_id"]

    after = (await discovery_client.get(f"{DISCOVERY}/candidates")).json()["items"]
    added_candidate = next(c for c in after if c["id"] == candidate_id)
    assert added_candidate["added"] is True


async def test_compare_names_best(discovery_client: AsyncClient) -> None:
    await discovery_client.post(
        f"{DISCOVERY}/search", json={"topic": "news", "providers": ["telegram"]}
    )
    items = (await discovery_client.get(f"{DISCOVERY}/candidates")).json()["items"]
    ids = [c["id"] for c in items]
    resp = await discovery_client.post(f"{DISCOVERY}/compare", json={"candidate_ids": ids})
    assert resp.status_code == 200
    assert resp.json()["best_title"] == "News"
    assert resp.json()["best_reason"]


async def test_compare_requires_two(discovery_client: AsyncClient) -> None:
    resp = await discovery_client.post(
        f"{DISCOVERY}/compare", json={"candidate_ids": ["only"]}
    )
    assert resp.status_code == 400


async def test_clear(discovery_client: AsyncClient) -> None:
    await discovery_client.post(
        f"{DISCOVERY}/search", json={"topic": "news", "providers": ["telegram"]}
    )
    resp = await discovery_client.post(f"{DISCOVERY}/candidates/clear")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert (await discovery_client.get(f"{DISCOVERY}/candidates")).json()["items"] == []
