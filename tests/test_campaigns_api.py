"""Tests for invite-link campaigns (no-session promotion) and donor analytics.

Campaign links are created through the deterministic fake bot provider, so no
real Telegram access is needed. Donor analytics is tested as pure logic plus the
service/API path.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

CAMPAIGNS = "/api/v1/campaigns"
DONORS = "/api/v1/donors"


@pytest_asyncio.fixture
async def product_client() -> AsyncClient:
    from backend.app.api.deps import get_provider_factory, get_session_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.providers.fake_bot import FakeTelegramBotProvider
    from tests.conftest import make_fake_session_factory

    await init_models()
    app = create_app()

    def _bot_factory(token, *, provider_name="auto", settings=None):
        return FakeTelegramBotProvider(token)

    app.dependency_overrides[get_provider_factory] = lambda: _bot_factory
    app.dependency_overrides[get_session_provider_factory] = lambda: make_fake_session_factory()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_campaign_lifecycle_and_link(product_client: AsyncClient) -> None:
    channel = await product_client.post("/api/v1/channels", json={"reference": "@promo"})
    channel_id = channel.json()["id"]
    bot = await product_client.post("/api/v1/bots", json={"token": "222:BBB", "kind": "managed"})
    bot_id = bot.json()["id"]
    await product_client.post(
        "/api/v1/bindings", json={"bot_id": bot_id, "channel_id": channel_id}
    )

    created = await product_client.post(
        CAMPAIGNS,
        json={"name": "Промо", "channel_id": channel_id, "risk_mode": "conservative"},
    )
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["status"] == "draft"
    assert campaign["risk_mode"] == "conservative"

    link = await product_client.post(
        f"{CAMPAIGNS}/{campaign['id']}/links", json={"label": "Весна"}
    )
    assert link.status_code == 201, link.text
    assert link.json()["link"].startswith("https://t.me/")
    assert link.json()["status"] == "active"

    detail = await product_client.get(f"{CAMPAIGNS}/{campaign['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["links"]) == 1
    assert body["campaign"]["status"] == "active"

    revoked = await product_client.post(
        f"{CAMPAIGNS}/{campaign['id']}/links/{link.json()['id']}/revoke"
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


async def test_campaign_list_exposes_risk_modes(product_client: AsyncClient) -> None:
    resp = await product_client.get(CAMPAIGNS)
    assert resp.status_code == 200
    body = resp.json()
    assert "conservative" in body["risk_modes"]
    assert body["total"] == 0


async def test_campaign_requires_name(product_client: AsyncClient) -> None:
    resp = await product_client.post(CAMPAIGNS, json={"name": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"]["hint"]


async def test_campaign_delete(product_client: AsyncClient) -> None:
    created = await product_client.post(CAMPAIGNS, json={"name": "Temp"})
    campaign_id = created.json()["id"]
    deleted = await product_client.delete(f"{CAMPAIGNS}/{campaign_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert (await product_client.get(f"{CAMPAIGNS}/{campaign_id}")).status_code == 404


# --- donor heuristics (pure) -------------------------------------------------
def test_assess_donor_flags_artificial_activity() -> None:
    from backend.app.services.donor_heuristics import DonorInput, assess_donor

    result = assess_donor(
        DonorInput(
            subscribers=10000,
            avg_views=100,
            participant_data=True,
            sample_size=100,
            sample_bots=40,
            completeness="complete",
        )
    )
    assert result.quality == "suspect"
    assert result.bot_probability == "high"
    assert result.bot_share_estimate == 0.4
    assert "high_bot_share" in result.signals
    assert result.explanations


def test_assess_donor_is_conservative_without_data() -> None:
    from backend.app.services.donor_heuristics import DonorInput, assess_donor

    result = assess_donor(DonorInput())
    assert result.quality == "unknown"
    assert result.bot_share_estimate is None
    assert result.confidence == "low"
    assert "Недостаточно данных" in result.summary


def test_assess_donor_healthy_channel() -> None:
    from backend.app.services.donor_heuristics import DonorInput, assess_donor

    result = assess_donor(
        DonorInput(subscribers=5000, avg_views=2000, posts_count=100, completeness="complete")
    )
    assert result.quality == "good"
    assert result.bot_probability == "low"


# --- donor API ---------------------------------------------------------------
async def test_donor_analyze_and_list(product_client: AsyncClient) -> None:
    source = await product_client.post(
        "/api/v1/audience/sources", json={"reference": "@donor"}
    )
    assert source.status_code in (200, 201), source.text
    source_id = source.json()["id"]

    analyzed = await product_client.post(f"{DONORS}/analyze/{source_id}")
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["source_id"] == source_id
    assert body["quality"] in {"unknown", "good", "average", "suspect"}

    listed = await product_client.get(DONORS)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["note"]


async def test_donor_analyze_unknown_source_404(product_client: AsyncClient) -> None:
    resp = await product_client.post(f"{DONORS}/analyze/nope")
    assert resp.status_code == 404
