"""Bot Factory API tests (v1.3).

Drives the HTTP endpoints with both provider factories overridden to fakes.
No real credentials or network (D-001).
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.fake_session import (
    FakeBotFactoryScenario,
    FakeSessionProvider,
)


def _bot_factory(token, *, provider_name="auto", settings=None):
    return FakeTelegramBotProvider(token)


@pytest_asyncio.fixture
async def factory_client() -> AsyncClient:
    from backend.app.api.deps import (
        get_provider_factory,
        get_session_provider_factory,
    )
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app

    await init_models()
    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )
    shared = FakeSessionProvider(
        bot_factory=FakeBotFactoryScenario(available=["mix_1_bot", "mix_2_bot"])
    )

    def session_factory(**kwargs):  # type: ignore[no-untyped-def]
        return shared

    app = create_app()
    app.dependency_overrides[get_provider_factory] = lambda: _bot_factory
    app.dependency_overrides[get_session_provider_factory] = lambda: session_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_templates_endpoint(factory_client: AsyncClient) -> None:
    resp = await factory_client.get("/api/v1/bot-factory/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert any(t["key"] == "index" for t in data)


async def test_batch_lifecycle_over_api(factory_client: AsyncClient) -> None:
    # Add a manager bot so deep links and token fetching work.
    manager = await factory_client.post(
        "/api/v1/bots", json={"token": "777777:MANAGER", "kind": "manager"}
    )
    assert manager.status_code == 201, manager.text
    manager_id = manager.json()["id"]

    created = await factory_client.post(
        "/api/v1/bot-factory/batches",
        json={"prefix": "Mix", "count": 2, "manager_bot_id": manager_id},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    batch_id = body["batch"]["id"]
    assert len(body["candidates"]) == 2
    assert body["batch"]["limit_note"]
    assert "токен" not in body["batch"]  # never leaks a token field

    checked = await factory_client.post(f"/api/v1/bot-factory/batches/{batch_id}/check")
    assert checked.status_code == 200, checked.text
    statuses = {c["suggested_username"]: c["creation_status"] for c in checked.json()["candidates"]}
    assert statuses["mix_1_bot"] == "available"
    assert statuses["mix_2_bot"] == "available"

    created_bots = await factory_client.post(
        f"/api/v1/bot-factory/batches/{batch_id}/create"
    )
    assert created_bots.status_code == 200, created_bots.text
    assert created_bots.json()["batch"]["created_count"] == 2

    tokens = await factory_client.post(f"/api/v1/bot-factory/batches/{batch_id}/tokens")
    assert tokens.status_code == 200, tokens.text
    assert tokens.json()["imported"] == 2

    dashboard = await factory_client.get(
        f"/api/v1/bot-factory/batches/{batch_id}/dashboard"
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"]["tokens"] == 2


async def test_deeplink_creation_without_account(factory_client: AsyncClient) -> None:
    manager = await factory_client.post(
        "/api/v1/bots", json={"token": "888888:MANAGER", "kind": "manager"}
    )
    manager_id = manager.json()["id"]
    created = await factory_client.post(
        "/api/v1/bot-factory/batches",
        json={"prefix": "Mix", "count": 1, "manager_bot_id": manager_id},
    )
    batch_id = created.json()["batch"]["id"]
    resp = await factory_client.post(
        f"/api/v1/bot-factory/batches/{batch_id}/create?via_deeplink=true"
    )
    assert resp.status_code == 200, resp.text
    candidate = resp.json()["candidates"][0]
    assert candidate["deep_link"].startswith("https://t.me/newbot/")


async def test_delete_batch_over_api(factory_client: AsyncClient) -> None:
    created = await factory_client.post(
        "/api/v1/bot-factory/batches", json={"prefix": "Mix", "count": 1}
    )
    batch_id = created.json()["batch"]["id"]
    resp = await factory_client.delete(f"/api/v1/bot-factory/batches/{batch_id}")
    assert resp.status_code == 204
    missing = await factory_client.get(f"/api/v1/bot-factory/batches/{batch_id}")
    assert missing.status_code == 404
