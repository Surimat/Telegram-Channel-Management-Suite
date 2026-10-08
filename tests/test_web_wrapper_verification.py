"""Reproducible browser scenarios for the Web Wrapper Hub (v1.8.x verification).

Goal: turn the Web Wrapper Hub from "architecturally implemented" into
*actually verified* on practical scenarios — **without** any external site, any
authorization, any account or any AI credential.

Two layers are exercised over the **real** wrapper pipeline
(engine → provider → router):

1. :class:`FixtureBrowserRuntime` — real HTTP GETs against a local
   :class:`FixtureSite` + real HTML parsing. Deterministic in CI, no browser
   binary required. Covers: open a page, find text, extract structure, search.
2. Route-level: the normalized :class:`ChatResponse` and provider failover.

The genuine Playwright/Chromium path is proven separately by
``test_web_wrapper_playwright_integration.py`` (skipped when Playwright is
absent). Nothing here defeats CAPTCHA/MFA/auth: the fixture site is a plain
public page the test itself serves on ``127.0.0.1``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.web_fixtures import FixtureBrowserRuntime, FixtureSite

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "agent" / "WEB_WRAPPER_BENCHMARK.json"


def _def(definition_id: str, website: str, **kw):
    from backend.app.ai.gateway.types import Capability
    from backend.app.ai.gateway.wrappers.definition import WrapperDefinition

    caps = kw.pop("capabilities", Capability(text=True))
    return WrapperDefinition(
        id=definition_id,
        name=definition_id,
        website=website,
        capabilities=caps,
        enabled=True,
        **kw,
    )


def _provider(definition, runtime, *, enabled=True, name="web:fixture"):
    from backend.app.ai.gateway.wrappers.engine import (
        GenericWebWrapperProvider,
        WebWrapperEngine,
    )

    return GenericWebWrapperProvider(
        definition=definition,
        engine=WebWrapperEngine(runtime),
        enabled=enabled,
        configured_name=name,
    )


def _request(text=""):
    from backend.app.ai.gateway.types import ChatMessage, ChatRequest

    return ChatRequest(messages=[ChatMessage(role="user", content=text)], correlation_id="t")


@pytest.fixture(scope="module")
def site():
    s = FixtureSite().start()
    yield s
    s.stop()


# ---------------------------------------------------------------------------
# 1. Scenario: open a page
# ---------------------------------------------------------------------------
async def test_open_page_reads_title_and_text(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(_def("open", "/"), runtime)
    resp = await provider.chat(_request("open"))
    assert resp.ok is True
    assert resp.source == "web"
    assert "Каталог каналов" in resp.text
    assert resp.status == "available"
    # The real page was fetched over HTTP (title parsed from the document).
    assert runtime.actions[0] == ("open", "/", "")


# ---------------------------------------------------------------------------
# 2. Scenario: find text
# ---------------------------------------------------------------------------
async def test_find_text_on_article(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def("find", "/article", response_selector="article.body", response_take_last=False),
        runtime,
    )
    resp = await provider.chat(_request("find"))
    assert resp.ok is True
    assert "найти-меня" in resp.text


# ---------------------------------------------------------------------------
# 3. Scenario: extract structured data
# ---------------------------------------------------------------------------
async def test_extract_structured_links(site: FixtureSite) -> None:
    from backend.app.ai.gateway.types import Capability

    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def(
            "extract",
            "/extract",
            capabilities=Capability(text=True, structured=True),
            response_selector="ul.links li.link",
            extraction="structured",
        ),
        runtime,
    )
    resp = await provider.chat(_request("extract"))
    assert resp.ok is True
    assert resp.structured is not None
    assert resp.structured["kind"] == "extraction"
    items = resp.structured["items"]
    assert len(items) == 2
    hrefs = [i["href"] for i in items]
    assert hrefs == ["/a", "/b"]
    assert "Канал А" in resp.text and "Канал Б" in resp.text


async def test_extract_table_rows_attributes(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def(
            "extract-rows",
            "/extract",
            response_selector="tr.row",
            extraction="structured",
            extract_attrs=("data-kind",),
        ),
        runtime,
    )
    resp = await provider.chat(_request("rows"))
    items = resp.structured["items"]
    assert len(items) == 2
    assert items[0]["attributes"]["data-kind"] == "news"
    assert items[1]["attributes"]["data-kind"] == "funny"


async def test_extract_missing_selector_is_honest(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def(
            "extract-missing",
            "/extract",
            response_selector="ul.nope li.nope",
            extraction="structured",
        ),
        runtime,
    )
    resp = await provider.chat(_request("missing"))
    assert resp.ok is False
    assert "структур" in resp.error.lower()
    assert resp.error_category == "wrapper_selector"


# ---------------------------------------------------------------------------
# 4. Scenario: search / navigate
# ---------------------------------------------------------------------------
async def test_search_page_returns_results(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def(
            "search",
            "/",
            input_selector="input[name='q'], .search",
            response_selector="ul.results li.result a.result-link",
            response_take_last=False,
        ),
        runtime,
    )
    resp = await provider.chat(_request("Альфа"))
    assert resp.ok is True
    assert "Альфа" in resp.text
    # It really navigated to the search URL.
    assert any(a[0] == "fill" for a in runtime.actions)
    assert "/search" in runtime._url


# ---------------------------------------------------------------------------
# 5. Route-level: normalized response + failover
# ---------------------------------------------------------------------------
async def test_router_returns_normalized_response(site: FixtureSite) -> None:
    from backend.app.ai.gateway.router import AIRouter

    runtime = FixtureBrowserRuntime(site)
    web = _provider(_def("norm", "/"), runtime)
    router = AIRouter(max_attempts=1)
    resp = await router.route(_request("open"), [web])
    assert resp.ok is True
    assert resp.provider_used == "web:fixture"
    assert resp.source == "web"
    assert len(resp.attempts) == 1
    assert resp.attempts[0]["ok"] is True


async def test_router_fails_over_transient_provider(site: FixtureSite) -> None:
    from backend.app.ai.gateway.providers import FakeProvider
    from backend.app.ai.gateway.router import AIRouter

    bad = FakeProvider(provider="api-bad", fail_with="network_error")
    good = FakeProvider(provider="api-good", reply="ответ")
    router = AIRouter(max_attempts=1)
    resp = await router.route(_request("hi"), [bad, good])
    assert resp.ok is True
    assert resp.provider_used == "api-good"
    assert resp.fallback_used is True


async def test_router_excludes_incompatible_provider(site: FixtureSite) -> None:
    from backend.app.ai.gateway.router import AIRouter
    from backend.app.ai.gateway.types import Capability

    runtime = FixtureBrowserRuntime(site)
    disabled = _provider(_def("off", "/"), runtime, enabled=False)
    image_only = _provider(
        _def("img", "/", capabilities=Capability(text=False, image=True)), runtime
    )
    router = AIRouter(max_attempts=1)
    eligible = router._eligible([disabled, image_only], _request("x"))
    # Only the text-capable provider passes capability filtering; the image-only
    # one is excluded. The disabled one is filtered later (availability).
    assert [p.name for p in eligible] == ["web:fixture"]
    # A disabled provider is skipped at execution time → no answer is claimed.
    resp = await router.route(_request("x"), [disabled])
    assert resp.ok is False
    assert resp.provider_used == ""


async def test_missing_selector_falls_back_to_page_text(site: FixtureSite) -> None:
    # A text extraction with an unmatched selector degrades to the page text
    # rather than inventing: it is explicitly the whole page, not a claim that
    # the selector matched. A *structured* extraction is strict (see below).
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def("noselector", "/article", response_selector=".does-not-exist"),
        runtime,
    )
    resp = await provider.chat(_request("find"))
    assert resp.ok is True
    assert "Заголовок статьи" in resp.text


# ---------------------------------------------------------------------------
# 6. Failure classification (honest, no false success)
# ---------------------------------------------------------------------------
async def test_login_page_is_detected_not_bypassed(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def("login", "/login", login_markers=("sign in", "log in")),
        runtime,
    )
    resp = await provider.chat(_request("open"))
    assert resp.ok is False
    assert resp.error_category == "auth_required"


async def test_http_error_is_reported(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(_def("boom", "/boom"), runtime)
    resp = await provider.chat(_request("open"))
    assert resp.ok is False
    assert resp.status in ("unavailable", "network_error")


async def test_missing_selector_is_selector_error(site: FixtureSite) -> None:
    runtime = FixtureBrowserRuntime(site)
    provider = _provider(
        _def(
            "noselector-strict",
            "/article",
            response_selector=".does-not-exist",
            extraction="structured",
        ),
        runtime,
    )
    resp = await provider.chat(_request("find"))
    assert resp.ok is False
    assert resp.error_category == "wrapper_selector"


def test_browser_unavailable_when_runtime_reports_so() -> None:
    from backend.app.ai.gateway.browser import FakeBrowserRuntime
    from backend.app.ai.gateway.wrappers.engine import WebWrapperEngine

    runtime = FakeBrowserRuntime(_available=False)
    engine = WebWrapperEngine(runtime)
    assert engine.available() is False
    provider = _provider(_def("una", "/"), runtime)
    assert provider.availability().status == "unavailable"


# ---------------------------------------------------------------------------
# 7. Benchmark artifact integrity
# ---------------------------------------------------------------------------
def test_benchmark_artifact_exists_and_passes() -> None:
    assert BENCHMARK.exists(), "run tests/web_wrapper_bench.py to regenerate"
    data = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    assert data["scenarios_total"] >= 4
    assert data["scenarios_failed"] == 0, data["results"]
    assert data["scenarios_passed"] == data["scenarios_total"]
    assert data["external_network"] is False
    names = {r["name"] for r in data["results"]}
    assert {"open_page", "find_text", "extract_data", "search_nav"} <= names
    assert data["results"]
    assert all(r["success"] is True for r in data["results"])


def test_benchmark_artifact_contains_no_secrets() -> None:
    text = BENCHMARK.read_text(encoding="utf-8").lower()
    for needle in ("api_key", "api_hash", "password", "session_string", "auth_key", "bearer "):
        assert needle not in text, f"benchmark leaked {needle!r}"


def test_fixture_site_is_local_only(site: FixtureSite) -> None:
    assert site.url("/").startswith("http://127.0.0.1:")
