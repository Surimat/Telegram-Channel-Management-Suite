"""v2.0 Этап 2 — Web Wrappers and free multimodal AI providers.

Covers the new surface *without network or credentials*:

* the model-level capability catalog is honest (only actually-probed operations
  are marked ``verified``; nothing requires a key it does not need);
* :class:`PollinationsProvider` needs no key and refuses image/file requests
  honestly so the router can fail over;
* first-run provisioning is additive + idempotent and never overwrites the
  owner (a disabled row is not re-enabled);
* browser preflight is honest and the API stays usable without a browser;
* the free web-wrapper definitions are present, disabled by default and never
  claim a bypass of an anti-bot/login wall.

No test here contacts an external host: the HTTP transport is fake and the browser
launch probe is monkeypatched.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.ai.gateway import catalog, registry
from backend.app.ai.gateway.http import FakeHttpTransport, HttpResponse
from backend.app.ai.gateway.preflight import STEP_MISSING, STEP_OK, BrowserPreflight, PrepStep
from backend.app.ai.gateway.providers import (
    Llm7Provider,
    PollinationsImageProvider,
    PollinationsProvider,
)
from backend.app.ai.gateway.router import AIRouter
from backend.app.ai.gateway.types import Capability, ChatMessage, ChatRequest
from backend.app.ai.gateway.wrappers.definition import LIBRARY, get_definition


def _req(text: str = "привет", **kw) -> ChatRequest:
    base = {
        "messages": [ChatMessage(role="user", content=text)],
        "requires": Capability(text=True),
        "correlation_id": "v2",
    }
    base.update(kw)
    return ChatRequest(**base)


def _ok_transport() -> FakeHttpTransport:
    reply = HttpResponse(
        status=200,
        text='{"choices":[{"message":{"content":"ответ"}}]}',
    )
    return FakeHttpTransport({"pollinations": reply, "llm7": reply})


# ---------------------------------------------------------------------------
# Model-level capability catalog
# ---------------------------------------------------------------------------
def test_catalog_only_probed_operations_are_verified() -> None:
    for model in catalog.MODEL_CATALOG:
        if model.verified:
            assert model.verified_operations, f"{model.provider} verified without ops"
            assert set(model.verified_operations) <= set(model.operations)


def test_pollinations_is_keyless_and_verified_for_text() -> None:
    m = next(x for x in catalog.MODEL_CATALOG if x.provider == "pollinations")
    assert m.auth == catalog.AUTH_NONE
    assert m.availability == catalog.AVAIL_READY
    assert m.verified and catalog.OP_TEXT in m.verified_operations
    # It is honestly text-only: it must not claim vision/file.
    assert catalog.OP_IMAGE not in m.operations
    assert catalog.OP_FILE not in m.operations


def test_models_supporting_returns_honest_vision_list() -> None:
    vision = catalog.models_supporting(catalog.OP_IMAGE)
    providers = {m.provider for m in vision}
    assert "pollinations" not in providers
    assert "google" in providers  # Gemini declares vision (needs key)


def test_keyless_providers_are_never_verified_for_vision() -> None:
    """Honesty: no free, keyless provider may claim verified image understanding."""
    for model in catalog.MODEL_CATALOG:
        if model.auth == catalog.AUTH_NONE:
            assert catalog.OP_IMAGE not in model.verified_operations, model.provider


def test_llm7_is_keyless_and_verified_for_text() -> None:
    m = next(x for x in catalog.MODEL_CATALOG if x.provider == "llm7")
    assert m.auth == catalog.AUTH_NONE
    assert m.availability == catalog.AVAIL_READY
    assert m.verified and catalog.OP_TEXT in m.verified_operations
    assert catalog.OP_IMAGE not in m.operations


def test_pollinations_image_is_verified_for_generation_only() -> None:
    m = next(x for x in catalog.MODEL_CATALOG if x.provider == "pollinations_image")
    assert m.auth == catalog.AUTH_NONE
    assert m.verified
    assert catalog.OP_IMAGE_GEN in m.verified_operations
    # Generation is not understanding.
    assert catalog.OP_IMAGE not in m.operations
    assert catalog.OP_IMAGE_GEN in catalog.models_supporting(catalog.OP_IMAGE_GEN)[0].operations


# ---------------------------------------------------------------------------
# Free provider adapter
# ---------------------------------------------------------------------------
async def test_pollinations_needs_no_key() -> None:
    provider = PollinationsProvider(transport=_ok_transport())
    info = provider.info
    assert info.auth_mode == "no_auth"
    assert info.auth_required is False
    assert info.cost == "free"
    assert provider.availability().usable is True


async def test_pollinations_serves_text() -> None:
    provider = PollinationsProvider(transport=_ok_transport())
    resp = await provider.chat(_req("скажи привет"))
    assert resp.ok is True
    assert resp.text == "ответ"


async def test_pollinations_refuses_image_honestly() -> None:
    from backend.app.ai.gateway.types import MODALITY_IMAGE, Attachment

    provider = PollinationsProvider(transport=_ok_transport())
    req = _req(
        "что на картинке",
        requires=Capability(text=True, image=True),
        messages=[
            ChatMessage(
                role="user",
                content="что на картинке",
                attachments=[Attachment(kind=MODALITY_IMAGE, reference="x.png")],
            )
        ],
    )
    resp = await provider.chat(req)
    assert resp.ok is False
    assert resp.error  # an honest reason, not an empty success


async def test_pollinations_fails_over_to_vision_capable_provider() -> None:
    """A text-only provider must never serve an image request when another can."""
    from backend.app.ai.gateway.providers import FakeProvider

    text_only = PollinationsProvider(transport=_ok_transport())
    vision = FakeProvider(provider="vision", capabilities=Capability(text=True, image=True))
    req = _req("что на картинке", requires=Capability(text=True, image=True))
    resp = await AIRouter(max_attempts=2).route(req, [text_only, vision])
    assert resp.ok is True
    assert resp.provider_used == "vision"


async def test_llm7_needs_no_key_and_serves_text() -> None:
    provider = Llm7Provider(transport=_ok_transport())
    info = provider.info
    assert info.auth_mode == "no_auth"
    assert info.auth_required is False
    assert info.cost == "free"
    assert provider.availability().usable is True
    resp = await provider.chat(_req("привет"))
    assert resp.ok is True and resp.text == "ответ"


async def test_llm7_refuses_image_honestly() -> None:
    from backend.app.ai.gateway.types import MODALITY_IMAGE, Attachment

    provider = Llm7Provider(transport=_ok_transport())
    req = _req(
        "что на картинке",
        requires=Capability(text=True, image=True),
        messages=[
            ChatMessage(
                role="user",
                content="что на картинке",
                attachments=[Attachment(kind=MODALITY_IMAGE, reference="x.png")],
            )
        ],
    )
    resp = await provider.chat(req)
    assert resp.ok is False and resp.error


async def test_pollinations_image_generates_and_needs_no_key() -> None:
    transport = FakeHttpTransport(
        {"image.pollinations.ai": HttpResponse(status=200, text="")}
    )
    provider = PollinationsImageProvider(transport=transport)
    assert provider.info.auth_mode == "no_auth"
    assert provider.info.auth_required is False
    resp = await provider.chat(_req("красный круг"))
    assert resp.ok is True
    assert resp.structured and resp.structured["image_url"].startswith(
        "https://image.pollinations.ai/prompt/"
    )
    # Deterministic: the same prompt yields the same seed/url.
    again = await provider.chat(_req("красный круг"))
    assert again.text == resp.text


async def test_pollinations_image_never_claims_vision() -> None:
    provider = PollinationsImageProvider(transport=FakeHttpTransport())
    assert provider.info.capabilities.image is False
    assert provider.info.capabilities.text is False
    assert provider.info.capabilities.verified is False


async def test_web_session_expiry_fails_over_to_api_provider() -> None:
    """An expired web session (login wall) must fall over, not fail the request."""
    from backend.app.ai.gateway.browser import FakeBrowserRuntime, PageSnapshot
    from backend.app.ai.gateway.providers import FakeProvider
    from backend.app.ai.gateway.wrappers.definition import WrapperDefinition
    from backend.app.ai.gateway.wrappers.engine import (
        GenericWebWrapperProvider,
        WebWrapperEngine,
    )

    runtime = FakeBrowserRuntime(
        _available=True,
        queue=[
            PageSnapshot(url="https://example.test/", title="Sign in", text="Please sign in"),
        ],
    )
    definition = WrapperDefinition(
        id="sess",
        name="sess",
        website="https://example.test/",
        capabilities=Capability(text=True),
        enabled=True,
        input_selector="textarea",
        response_selector=".answer",
        login_markers=("sign in",),
    )
    expired = GenericWebWrapperProvider(
        definition=definition,
        engine=WebWrapperEngine(runtime),
        enabled=True,
        configured_name="web:sess",
    )
    fallback = FakeProvider(provider="pollinations", reply="ответ")

    # Force the web wrapper first (manual strategy orders by priority) so the
    # expired session is genuinely attempted before the API fallback.
    req = _req("привет", strategy="manual")
    resp = await AIRouter(max_attempts=2).route(req, [expired, fallback])
    assert resp.ok is True
    assert resp.provider_used == "pollinations"
    assert resp.fallback_used is True


# ---------------------------------------------------------------------------
# First-run provisioning (out of the box)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def session():
    from backend.app.db.session import get_session_factory, init_models

    await init_models()
    factory = get_session_factory()
    async with factory() as s:
        yield s


async def test_provision_is_additive_and_idempotent(session) -> None:
    from backend.app.services.ai_gateway_service import AiGatewayService

    svc = AiGatewayService(session, transport=_ok_transport())
    created = await svc.provision_free_providers()
    assert "pollinations" in created
    await session.commit()

    # Second run changes nothing.
    again = await svc.provision_free_providers()
    assert again == []

    rows = {r.provider: r for r in await svc.list_providers()}
    assert rows["pollinations"].enabled is True  # free + keyless: ready
    assert rows["pollinations"].api_key_encrypted == ""
    assert rows["pollinations"].auth_mode == "no_auth"
    assert rows["llm7"].enabled is True  # second keyless free text path
    assert rows["llm7"].auth_mode == "no_auth"
    assert rows["pollinations_image"].enabled is False  # generation: opt-in
    assert rows["ollama"].enabled is False  # needs a local server


def test_registry_maps_new_free_kinds() -> None:
    from backend.app.ai.gateway.registry import ProviderConfig, build_provider

    llm7 = build_provider(
        ProviderConfig(provider="llm7", kind="llm7", enabled=True),
        transport=_ok_transport(),
    )
    assert llm7.info.auth_required is False and llm7.name == "llm7"
    image = build_provider(
        ProviderConfig(provider="pollinations_image", kind="pollinations_image", enabled=True),
        transport=_ok_transport(),
    )
    assert image.info.auth_required is False
    assert image.info.capabilities.image is False
    assert registry.KIND_LLM7 in registry.ALL_KINDS


async def test_provision_never_overwrites_owner_choice(session) -> None:
    from backend.app.services.ai_gateway_service import AiGatewayService

    svc = AiGatewayService(session, transport=_ok_transport())
    # The owner disabled the free provider on an earlier run…
    await svc.provision_free_providers()
    await session.commit()
    row = await svc.get_provider("pollinations")
    row.enabled = False
    await session.commit()

    # …so provisioning must not re-enable it.
    created = await svc.provision_free_providers()
    assert created == []
    row = await svc.get_provider("pollinations")
    assert row.enabled is False


# ---------------------------------------------------------------------------
# Browser preflight honesty
# ---------------------------------------------------------------------------
def test_preflight_reports_steps_and_api_note() -> None:
    from backend.app.ai.gateway.preflight import preflight

    pf = preflight()
    ids = [s.id for s in pf.steps]
    assert "package" in ids and "chromium" in ids and "api" in ids
    assert pf.api_works_without_browser is True


async def test_browser_prepare_never_raises_without_browser(monkeypatch) -> None:
    from backend.app.services import ai_gateway_service as mod
    from backend.app.services.ai_gateway_service import AiGatewayService

    fake = BrowserPreflight(
        available=False,
        steps=[PrepStep(id="package", title="Пакет Playwright", status=STEP_MISSING)],
    )

    async def _fake_probe(*, headless: bool = True):
        return fake

    monkeypatch.setattr(mod, "browser_probe", _fake_probe)
    svc = AiGatewayService(session=None)  # type: ignore[arg-type]
    result = await svc.browser_prepare()
    assert result.available is False
    assert result.steps[0].status == STEP_MISSING


def test_preflight_available_implies_ok_steps() -> None:
    # A synthetic "available" preflight keeps its steps coherent.
    pf = BrowserPreflight(
        available=True,
        steps=[
            PrepStep(id="package", title="Пакет Playwright", status=STEP_OK),
            PrepStep(id="chromium", title="Сборка Chromium", status=STEP_OK),
        ],
    )
    assert pf.available is True
    assert pf.detail() == "Браузерный движок готов к работе."


# ---------------------------------------------------------------------------
# Free web-wrapper definitions (honest, opt-in)
# ---------------------------------------------------------------------------
def test_free_wrapper_definitions_exist_and_are_disabled() -> None:
    ids = {d.id for d in LIBRARY}
    assert {"duckai", "copilot"} <= ids
    for wid in ("duckai", "copilot", "chatgpt", "gemini"):
        d = get_definition(wid)
        assert d is not None
        assert d.enabled is False, f"{wid} must be opt-in (owner + browser)"


def test_wrapper_definition_never_promises_bypass() -> None:
    duckai = get_definition("duckai")
    assert duckai is not None
    assert duckai.auth_mode == "browser_session"
    # Honesty: it must say it does NOT bypass the anti-bot check.
    assert "НЕ обходит" in duckai.note


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client() -> AsyncClient:
    from fastapi import Depends

    from backend.app.api.deps import get_ai_gateway_service
    from backend.app.db.session import get_session, init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()

    def _override(session=Depends(get_session)):
        from backend.app.services.ai_gateway_service import AiGatewayService

        return AiGatewayService(session, transport=_ok_transport())

    app.dependency_overrides[get_ai_gateway_service] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_api_models_matrix(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ai-gateway/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["operations"]["text"] == "Текст"
    poll = next(i for i in body["items"] if i["provider"] == "pollinations")
    assert poll["auth"] == "no_auth" and poll["verified"] is True


async def test_api_provision_then_operations(client: AsyncClient) -> None:
    prov = await client.post("/api/v1/ai-gateway/provision")
    assert prov.status_code == 200
    assert "pollinations" in prov.json()["providers"]

    ops = await client.get("/api/v1/ai-gateway/operations")
    assert ops.status_code == 200
    text = next(i for i in ops.json()["items"] if i["operation"] == "text")
    assert text["available"] is True and "pollinations" in text["providers"]
    # No vision provider is configured, so vision is honestly unavailable.
    vision = next(
        i for i in ops.json()["items"] if i["operation"] == "image_understanding"
    )
    assert vision["available"] is False
    # Image generation is reported too; it is off by default (opt-in).
    gen = next(
        i for i in ops.json()["items"] if i["operation"] == "image_generation"
    )
    assert gen["available"] is False


async def test_api_browser_preflight_no_launch(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ai-gateway/browser/preflight")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_works_without_browser"] is True
    assert isinstance(body["steps"], list) and body["steps"]
