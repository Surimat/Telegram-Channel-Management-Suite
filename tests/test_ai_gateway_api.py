"""API tests for the AI Gateway (v1.8).

Runs the real router/service over a temporary SQLite DB, with the service built
from a fake transport and a fake browser runtime (no network, no credentials).
Asserts the API key is never returned and the honest availability states.
"""

from __future__ import annotations

import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from backend.app.ai.gateway.browser import FakeBrowserRuntime, PageSnapshot
from backend.app.ai.gateway.http import FakeHttpTransport, HttpResponse

BASE = "/api/v1/ai-gateway"


def _make_service(session, *, browser_available: bool = False):
    from backend.app.services.ai_gateway_service import AiGatewayService

    return AiGatewayService(
        session,
        transport=FakeHttpTransport(
            {
                "/chat/completions": HttpResponse(
                    status=200,
                    text='{"choices":[{"message":{"content":"ответ шлюза"}}]}',
                )
            }
        ),
        browser_runtime=FakeBrowserRuntime(
            _available=browser_available,
            queue=[
                PageSnapshot(url="http://x", title="Chat", text="box"),
                PageSnapshot(url="http://x", text="box"),
                PageSnapshot(url="http://x", text="box"),
                PageSnapshot(url="http://x", response_text="ответ обёртки"),
            ],
        ),
    )


@pytest_asyncio.fixture
async def gw_client() -> AsyncClient:
    from backend.app.api.deps import get_ai_gateway_service
    from backend.app.db.session import get_session, init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()

    def _override(session=Depends(get_session)):
        return _make_service(session)

    app.dependency_overrides[get_ai_gateway_service] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def gw_web_client() -> AsyncClient:
    """Same as ``gw_client`` but with an *available* fake browser runtime."""
    from backend.app.api.deps import get_ai_gateway_service
    from backend.app.db.session import get_session, init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()

    def _override(session=Depends(get_session)):
        return _make_service(session, browser_available=True)

    app.dependency_overrides[get_ai_gateway_service] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _add_provider(client: AsyncClient, **overrides) -> dict:
    payload = {
        "provider": "test-openai",
        "kind": "openai_compatible",
        "model": "test-model",
        "base_url": "https://example.test/v1",
        "api_key": "super-secret-key",
        "enabled": True,
        "cost": "free",
    }
    payload.update(overrides)
    resp = await client.post(f"{BASE}/providers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_status_defaults(gw_client: AsyncClient) -> None:
    resp = await gw_client.get(f"{BASE}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["providers"] == 0
    assert body["browser_available"] is False
    assert "не гарантирует" in body["note"]


async def test_provider_crud_never_returns_key(gw_client: AsyncClient) -> None:
    created = await _add_provider(gw_client)
    assert created["has_key"] is True
    assert "api_key" not in created
    assert "super-secret-key" not in str(created)

    listed = await gw_client.get(f"{BASE}/providers")
    body = listed.json()
    assert body["items"][0]["provider"] == "test-openai"
    assert body["items"][0]["has_key"] is True
    assert "super-secret-key" not in listed.text
    assert "openai_compatible" in [k["value"] for k in body["kinds"]]


async def test_toggle_and_delete(gw_client: AsyncClient) -> None:
    await _add_provider(gw_client)
    off = await gw_client.post(
        f"{BASE}/providers/test-openai/toggle", json={"enabled": False}
    )
    assert off.status_code == 200
    assert off.json()["enabled"] is False
    assert off.json()["status"] == "unavailable"
    deleted = await gw_client.delete(f"{BASE}/providers/test-openai")
    assert deleted.status_code == 204
    assert (await gw_client.get(f"{BASE}/providers")).json()["items"] == []


async def test_unknown_kind_rejected(gw_client: AsyncClient) -> None:
    resp = await gw_client.post(
        f"{BASE}/providers", json={"provider": "x", "kind": "magic"}
    )
    assert resp.status_code == 400


async def test_chat_routes_through_provider(gw_client: AsyncClient) -> None:
    await _add_provider(gw_client)
    resp = await gw_client.post(
        f"{BASE}/chat", json={"text": "привет", "provider": "test-openai"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["text"] == "ответ шлюза"
    assert body["provider_used"] == "test-openai"
    assert body["status"] == "available"


async def test_chat_without_providers_is_honest(gw_client: AsyncClient) -> None:
    resp = await gw_client.post(f"{BASE}/chat", json={"text": "привет"})
    body = resp.json()
    assert body["ok"] is False
    assert body["error_category"] == "no_provider"


async def test_route_settings_roundtrip(gw_client: AsyncClient) -> None:
    resp = await gw_client.put(
        f"{BASE}/settings", json={"key": "ai_gateway_strategy", "value": "free_first"}
    )
    assert resp.status_code == 200
    assert resp.json()["strategy"] == "free_first"
    bad = await gw_client.put(
        f"{BASE}/settings", json={"key": "ai_gateway_strategy", "value": "nonsense"}
    )
    assert bad.status_code == 400
    unknown = await gw_client.put(
        f"{BASE}/settings", json={"key": "no_such_key", "value": "1"}
    )
    assert unknown.status_code == 400


async def test_browser_status_reports_unavailable(gw_client: AsyncClient) -> None:
    resp = await gw_client.get(f"{BASE}/browser")
    body = resp.json()
    assert body["available"] is False
    assert "Docker" in body["docker_note"]


async def test_wrapper_library_present(gw_client: AsyncClient) -> None:
    resp = await gw_client.get(f"{BASE}/wrappers")
    body = resp.json()
    assert any(w["id"] == "generic" for w in body["items"])
    assert all("capabilities" in w for w in body["items"])


async def test_use_case_matrix_marks_available(gw_client: AsyncClient) -> None:
    await _add_provider(gw_client)
    resp = await gw_client.get(f"{BASE}/use-cases")
    body = resp.json()
    assert body["items"]
    text_cases = [i for i in body["items"] if i["modality"] == "text"]
    assert any(i["available"] for i in text_cases)
    image_cases = [i for i in body["items"] if i["modality"] == "image"]
    assert all(not i["available"] for i in image_cases)


async def test_request_history_records_metadata_only(gw_client: AsyncClient) -> None:
    await _add_provider(gw_client)
    await gw_client.post(f"{BASE}/chat", json={"text": "секретный промпт"})
    resp = await gw_client.get(f"{BASE}/requests")
    body = resp.json()
    assert body["items"]
    assert "секретный промпт" not in resp.text
    assert body["items"][0]["provider"] == "test-openai"


async def test_web_wrapper_provider_via_api(gw_client: AsyncClient) -> None:
    # A web provider with an available fake browser runtime.
    resp = await gw_client.post(
        f"{BASE}/providers",
        json={
            "provider": "web:generic",
            "kind": "web",
            "wrapper_id": "generic",
            "enabled": True,
            "cost": "free",
        },
    )
    assert resp.status_code == 201
    chat = await gw_client.post(
        f"{BASE}/chat", json={"text": "сделай пост", "provider": "web:generic"}
    )
    body = chat.json()
    # Browser is unavailable in the default service for this fixture.
    assert body["ok"] is False


async def test_web_wrapper_serves_answer_when_browser_available(
    gw_web_client: AsyncClient,
) -> None:
    """End-to-end: a web provider really answers through the API."""
    await gw_web_client.post(
        f"{BASE}/providers",
        json={
            "provider": "web:generic",
            "kind": "web",
            "wrapper_id": "generic",
            "enabled": True,
            "cost": "free",
        },
    )
    chat = await gw_web_client.post(
        f"{BASE}/chat", json={"text": "сделай пост", "provider": "web:generic"}
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["ok"] is True
    assert body["text"] == "ответ обёртки"
    assert body["provider_used"] == "web:generic"
    assert body["source"] == "web"


async def test_web_provider_pinned_name_routes_even_when_custom(
    gw_web_client: AsyncClient,
) -> None:
    """A web provider configured under a custom name must still route by name."""
    await gw_web_client.post(
        f"{BASE}/providers",
        json={
            "provider": "my-web",
            "kind": "web",
            "wrapper_id": "generic",
            "enabled": True,
            "cost": "free",
        },
    )
    chat = await gw_web_client.post(
        f"{BASE}/chat", json={"text": "сделай пост", "provider": "my-web"}
    )
    body = chat.json()
    assert body["ok"] is True
    assert body["provider_used"] == "my-web"


async def test_unknown_wrapper_provider_is_not_available(
    gw_web_client: AsyncClient,
) -> None:
    """A provider with a wrapper id that does not exist must not be usable."""
    resp = await gw_web_client.post(
        f"{BASE}/providers",
        json={
            "provider": "ghost-web",
            "kind": "web",
            "wrapper_id": "does_not_exist",
            "enabled": True,
            "cost": "free",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["enabled"] is True  # owner asked for enabled...
    chat = await gw_web_client.post(
        f"{BASE}/chat", json={"text": "hi", "provider": "ghost-web"}
    )
    chat_body = chat.json()
    # ...but it can never serve: no wrapper definition exists.
    assert chat_body["ok"] is False
