"""Gateway-level verification: honesty, failover, security and content hooks.

Complements ``test_ai_gateway.py`` / ``test_ai_gateway_api.py`` and the browser
scenarios. Everything runs over the real service/router with fake transports and
the local fixture browser runtime — no network, no credentials, no external site.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.support.web_fixtures import FixtureSite

BASE = "/api/v1/ai-gateway"


@pytest_asyncio.fixture
async def site():
    s = FixtureSite().start()
    yield s
    s.stop()


# ---------------------------------------------------------------------------
# Capability matrix honesty
# ---------------------------------------------------------------------------
async def test_capability_matrix_marks_image_cases_unavailable_without_vision() -> None:
    """A text-only provider must not be listed as able to serve image cases, and
    a non-structured provider must not be listed for the structured classification
    use case."""
    from backend.app.ai.gateway.providers import FakeProvider
    from backend.app.ai.gateway.types import Capability, SourceKind
    from backend.app.services.ai_gateway_service import AiGatewayService

    text_only = FakeProvider(
        provider="text-only", capabilities=Capability(text=True), source=SourceKind.API
    )

    class _Svc(AiGatewayService):
        async def build_providers(self):  # type: ignore[override]
            return [text_only]

    svc = _Svc(session=None)  # type: ignore[arg-type]
    matrix = await svc.capability_matrix()
    image_cases = [m for m in matrix if m["modality"] == "image"]
    assert image_cases and all(not m["available"] for m in image_cases)
    # Classification is structured → excluded for a plain text provider.
    classification = [m for m in matrix if m["id"] == "classification"]
    assert classification and not classification[0]["available"]
    # A plain text case (e.g. rewrite) is served.
    rewrite = [m for m in matrix if m["id"] == "rewrite"]
    assert rewrite and rewrite[0]["available"]


async def test_capability_matrix_marks_vision_structured_provider() -> None:
    from backend.app.ai.gateway.providers import FakeProvider
    from backend.app.ai.gateway.types import Capability, SourceKind
    from backend.app.services.ai_gateway_service import AiGatewayService

    vision = FakeProvider(
        provider="vision",
        capabilities=Capability(text=True, image=True, structured=True),
        source=SourceKind.API,
    )

    class _Svc(AiGatewayService):
        async def build_providers(self):  # type: ignore[override]
            return [vision]

    svc = _Svc(session=None)  # type: ignore[arg-type]
    matrix = await svc.capability_matrix()
    assert all(m["available"] for m in matrix if m["modality"] == "image")
    assert all(m["available"] for m in matrix if m["id"] == "classification")


# ---------------------------------------------------------------------------
# Failover and regional failure (transient → fallback → honest narrative)
# ---------------------------------------------------------------------------
async def test_region_blocked_falls_over_and_narrates(site) -> None:
    from backend.app.ai.gateway.http import FakeHttpTransport, HttpResponse
    from backend.app.ai.gateway.providers import OpenAICompatibleProvider
    from backend.app.ai.gateway.router import AIRouter
    from backend.app.ai.gateway.types import ChatMessage, ChatRequest

    blocked = OpenAICompatibleProvider(
        provider="blocked",
        model="m",
        base_url="https://blocked.test/v1",
        api_key="k",
        transport=FakeHttpTransport({"": HttpResponse(status=451, text="")}),
    )
    good = OpenAICompatibleProvider(
        provider="good",
        model="m",
        base_url="https://good.test/v1",
        api_key="k",
        transport=FakeHttpTransport(
            {"": HttpResponse(status=200, text='{"choices":[{"message":{"content":"ok"}}]}')}
        ),
    )
    router = AIRouter(max_attempts=1)
    resp = await router.route(
        ChatRequest(messages=[ChatMessage(role="user", content="hi")]),
        [blocked, good],
    )
    assert resp.ok is True
    assert resp.provider_used == "good"
    assert resp.fallback_used is True
    categories = [a.get("status") for a in resp.attempts]
    assert "region_blocked" in categories


async def test_all_transient_providers_are_reported_not_silently_ok(site) -> None:
    from backend.app.ai.gateway.http import FakeHttpTransport, HttpResponse
    from backend.app.ai.gateway.providers import OpenAICompatibleProvider
    from backend.app.ai.gateway.router import AIRouter
    from backend.app.ai.gateway.types import ChatMessage, ChatRequest

    def blocked(name):
        return OpenAICompatibleProvider(
            provider=name,
            model="m",
            base_url="https://x.test/v1",
            api_key="k",
            transport=FakeHttpTransport({"": HttpResponse(status=451, text="")}),
        )

    router = AIRouter(max_attempts=1)
    resp = await router.route(
        ChatRequest(messages=[ChatMessage(role="user", content="hi")]),
        [blocked("a"), blocked("b")],
    )
    assert resp.ok is False
    assert resp.status == "region_blocked"
    assert resp.error


# ---------------------------------------------------------------------------
# Security: no browser profile / cookie / key anywhere
# ---------------------------------------------------------------------------
_SECRET_MARKERS = (
    "api_key",
    "api_hash",
    "password",
    "session_string",
    "auth_key",
    "cookie",
    "user_data_dir",
    "storage_state",
)


def test_diagnostics_contains_no_browser_profile_or_key() -> None:
    from backend.app.services.ai_gateway_service import AiGatewayService

    svc = AiGatewayService(session=None)  # type: ignore[arg-type]
    text = repr(svc.diagnostics()).lower()
    for marker in _SECRET_MARKERS:
        assert marker not in text, f"diagnostics leaked {marker!r}"


def test_provider_view_never_exposes_key() -> None:
    from backend.app.services.ai_gateway_service import ProviderView

    secret = "sk-super-secret-value-should-never-appear"
    view = ProviderView(
        provider="x",
        kind="openai_compatible",
        kind_label="OpenAI",
        model="m",
        base_url="https://x.test/v1",
        auth_mode="api_key",
        has_key=True,
        enabled=True,
        priority=0,
        cost="free",
        source="api",
        capabilities={"text": True},
        wrapper_id="",
        region_status="",
        note="",
    )
    text = repr(view.as_dict())
    # ``auth_mode="api_key"`` is a mode name, not a secret; the *value* of a key
    # must never appear. ProviderView has no key field at all.
    assert secret not in text
    assert "has_key" in text
    assert not hasattr(view, "api_key")


async def test_wrapper_library_has_no_credentials(site) -> None:
    from backend.app.services.ai_gateway_service import AiGatewayService

    svc = AiGatewayService(session=None)  # type: ignore[arg-type]
    text = repr(svc.wrapper_library()).lower()
    for marker in _SECRET_MARKERS:
        assert marker not in text


# ---------------------------------------------------------------------------
# Content integration hook
# ---------------------------------------------------------------------------
async def test_transform_routes_through_a_provider(site) -> None:
    from backend.app.ai.gateway.providers import FakeProvider
    from backend.app.ai.gateway.types import SourceKind
    from backend.app.services.ai_gateway_service import AiGatewayService

    provider = FakeProvider(provider="api", reply="переписанный текст", source=SourceKind.API)

    class _Svc(AiGatewayService):
        async def build_providers(self):  # type: ignore[override]
            return [provider]

        async def _setting(self, key):  # type: ignore[override]
            return ""

        async def _record(self, request, response):  # type: ignore[override]
            return None

    svc = _Svc(session=None)  # type: ignore[arg-type]
    resp = await svc.transform(task="rewrite", text="исходный текст", provider="api")
    assert resp.ok is True
    assert resp.text == "переписанный текст"
    assert resp.provider_used == "api"


# ---------------------------------------------------------------------------
# API: browser status is honest (single source of truth)
# ---------------------------------------------------------------------------
async def test_api_browser_status_reports_unavailable_without_playwright() -> None:
    from fastapi import Depends

    from backend.app.ai.gateway.browser import FakeBrowserRuntime
    from backend.app.api.deps import get_ai_gateway_service
    from backend.app.db.session import get_session, init_models
    from backend.app.main import create_app
    from backend.app.services.ai_gateway_service import AiGatewayService

    await init_models()
    app = create_app()

    def _override(session=Depends(get_session)):
        svc = AiGatewayService(session)
        svc._browser_runtime = FakeBrowserRuntime(_available=False)  # type: ignore[attr-defined]
        return svc

    app.dependency_overrides[get_ai_gateway_service] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"{BASE}/browser")
    app.dependency_overrides.clear()
    body = resp.json()
    assert body["available"] is False
    assert "Docker" in body["docker_note"]
