"""Content Studio API tests (v1.2): sources, items, cleaner, dashboard.

Uses manual/public sources so no Telegram access or credentials are needed.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def content_client() -> AsyncClient:
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_content_providers_listed(content_client: AsyncClient):
    resp = await content_client.get("/api/v1/content/providers")
    assert resp.status_code == 200
    kinds = {p["kind"] for p in resp.json()}
    assert {"telegram", "rss", "atom", "manual"} <= kinds


@pytest.mark.asyncio
async def test_source_item_and_clean_flow(content_client: AsyncClient):
    created = await content_client.post(
        "/api/v1/content/sources",
        json={"kind": "manual", "reference": "Текст с рекламой\nРеклама: промокод"},
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    grabbed = await content_client.post(f"/api/v1/content/sources/{source_id}/grab")
    assert grabbed.status_code == 200
    body = grabbed.json()
    assert body["ok"] and body["new_items"] == 1
    item_id = body["item_ids"][0]

    # Cleaner preview shows the change and is cancellable.
    preview = await content_client.get(f"/api/v1/content/items/{item_id}/clean")
    assert preview.status_code == 200
    assert preview.json()["changed"] is True

    applied = await content_client.post(f"/api/v1/content/items/{item_id}/clean", json={})
    assert applied.status_code == 200
    assert "Реклама" not in applied.json()["cleaned_text"]

    reverted = await content_client.post(f"/api/v1/content/items/{item_id}/clean/revert")
    assert reverted.json()["cleaned_text"] == ""

    # Rights unknown → warning present, then clearable.
    rights = await content_client.get(f"/api/v1/content/items/{item_id}/rights")
    assert rights.json()["warning"]
    patched = await content_client.patch(
        f"/api/v1/content/items/{item_id}", json={"rights_status": "own"}
    )
    assert patched.status_code == 200
    assert patched.json()["rights_status"] == "own"


@pytest.mark.asyncio
async def test_dashboard_counts(content_client: AsyncClient):
    await content_client.post(
        "/api/v1/content/sources", json={"kind": "manual", "reference": "Материал"}
    )
    dashboard = await content_client.get("/api/v1/content/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert "drafts" in data and "scheduled" in data


@pytest.mark.asyncio
async def test_rewrite_reports_unavailable_honestly(content_client: AsyncClient):
    created = await content_client.post(
        "/api/v1/content/sources", json={"kind": "manual", "reference": "Текст"}
    )
    source_id = created.json()["id"]
    grabbed = await content_client.post(f"/api/v1/content/sources/{source_id}/grab")
    item_id = grabbed.json()["item_ids"][0]
    resp = await content_client.post(
        f"/api/v1/content/items/{item_id}/rewrite", json={"mode": "rephrase"}
    )
    assert resp.status_code == 200
    # No generative model in tests → honest unavailable message, no crash.
    assert resp.json()["ok"] is False
    assert "Рерайт недоступен" in resp.json()["message"]


@pytest.mark.asyncio
async def test_delete_source(content_client: AsyncClient):
    created = await content_client.post(
        "/api/v1/content/sources", json={"kind": "manual", "reference": "Удаляемый"}
    )
    source_id = created.json()["id"]
    deleted = await content_client.delete(f"/api/v1/content/sources/{source_id}")
    assert deleted.status_code == 204
    listed = await content_client.get("/api/v1/content/sources")
    assert all(s["id"] != source_id for s in listed.json()["items"])
