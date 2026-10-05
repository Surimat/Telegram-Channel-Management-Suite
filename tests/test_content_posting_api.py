"""Content Studio posting API tests (v1.2).

Drives the real posting endpoints against the deterministic fake bot provider
(no network, no credentials).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

CONTENT = "/api/v1/content"


@pytest_asyncio.fixture
async def posting_client() -> AsyncClient:
    from backend.app.api.deps import get_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.providers.fake_bot import FakeTelegramBotProvider

    await init_models()
    app = create_app()

    def _bot_factory(token, *, provider_name="auto", settings=None):
        return FakeTelegramBotProvider(token)

    app.dependency_overrides[get_provider_factory] = lambda: _bot_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_channel(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/channels", json={"reference": "@demo"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_bot(client: AsyncClient) -> str:
    resp = await client.post("/api/v1/bots", json={"token": "111:AAA", "kind": "managed"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_item(client: AsyncClient, text: str = "Привет, мир") -> str:
    source = await client.post(
        f"{CONTENT}/sources", json={"kind": "manual", "reference": text}
    )
    assert source.status_code == 201, source.text
    grabbed = await client.post(f"{CONTENT}/sources/{source.json()['id']}/grab")
    assert grabbed.status_code == 200, grabbed.text
    return grabbed.json()["item_ids"][0]


@pytest.mark.asyncio
async def test_posting_flow_via_api(posting_client: AsyncClient) -> None:
    channel_id = await _make_channel(posting_client)
    await _make_bot(posting_client)
    item_id = await _make_item(posting_client)

    planned = await posting_client.post(
        f"{CONTENT}/items/{item_id}/plan",
        json={"targets": [{"channel_id": channel_id}]},
    )
    assert planned.status_code == 200, planned.text
    pub = planned.json()["publications"][0]
    assert pub["status"] == "planned"

    preview = await posting_client.get(f"{CONTENT}/items/{item_id}/preview")
    assert preview.status_code == 200
    assert preview.json()["text"]

    published = await posting_client.post(
        f"{CONTENT}/publications/{pub['id']}/publish"
    )
    assert published.status_code == 200, published.text
    assert published.json()["ok"] is True

    listed = await posting_client.get(f"{CONTENT}/items/{item_id}/publications")
    assert listed.json()["publications"][0]["status"] == "published"


@pytest.mark.asyncio
async def test_calendar_and_validation_api(posting_client: AsyncClient) -> None:
    await _make_channel(posting_client)
    item_id = await _make_item(posting_client, "Текст с **незакрытым")

    validation = await posting_client.get(f"{CONTENT}/items/{item_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["ok"] is False

    calendar = await posting_client.get(f"{CONTENT}/calendar")
    assert calendar.status_code == 200
    assert "entries" in calendar.json()


@pytest.mark.asyncio
async def test_moderation_and_release_api(posting_client: AsyncClient) -> None:
    source = await posting_client.post(
        f"{CONTENT}/sources", json={"kind": "manual", "reference": "Реклама казино"}
    )
    source_id = source.json()["id"]
    updated = await posting_client.put(
        f"{CONTENT}/sources/{source_id}/moderation",
        json={"blocked_keywords": ["казино"]},
    )
    assert updated.status_code == 200
    assert updated.json()["blocked_keywords"] == ["казино"]

    grabbed = await posting_client.post(f"{CONTENT}/sources/{source_id}/grab")
    assert grabbed.json()["new_items"] == 0
    assert grabbed.json()["blocked"] == 1


@pytest.mark.asyncio
async def test_buttons_api(posting_client: AsyncClient) -> None:
    item_id = await _make_item(posting_client)
    saved = await posting_client.put(
        f"{CONTENT}/items/{item_id}/buttons",
        json={"rows": [[{"text": "Сайт", "action": "url", "value": "https://example.com"}]]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["rows"][0][0]["text"] == "Сайт"

    bad = await posting_client.put(
        f"{CONTENT}/items/{item_id}/buttons",
        json={"rows": [[{"text": "X", "action": "url", "value": "bad"}]]},
    )
    assert bad.status_code == 400
