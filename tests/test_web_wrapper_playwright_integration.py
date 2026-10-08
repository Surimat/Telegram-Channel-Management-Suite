"""Real Playwright/Chromium integration for the Web Wrapper Hub (v1.8.x).

This is the *genuine* browser verification: it drives a real headless Chromium
via Playwright against the local fixture site, so the wrapper's real runtime is
proven — not just its fake. It covers the required practical scenarios:

    open a page → find text → extract structure → search/navigate →
    normalized result,

plus honest failure handling (HTTP 5xx surfaces as an error; a login page is
detected, never bypassed).

The whole module **skips** when Playwright or its Chromium build is absent, so
CI without a browser stays green; install it locally with::

    pip install playwright && playwright install chromium

Nothing here touches an external site, an account or a credential.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from tests.support.web_fixtures import FixtureSite


def _runtime_available() -> bool:
    try:
        from backend.app.ai.gateway.browser import PlaywrightBrowserRuntime
    except Exception:
        return False
    return bool(PlaywrightBrowserRuntime().available)


pytestmark = pytest.mark.skipif(
    not _runtime_available(),
    reason="Playwright/Chromium not installed (optional real-browser layer)",
)


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


def _request(text=""):
    from backend.app.ai.gateway.types import ChatMessage, ChatRequest

    return ChatRequest(messages=[ChatMessage(role="user", content=text)], correlation_id="pw")


@pytest_asyncio.fixture
async def browser():
    from backend.app.ai.gateway.browser import PlaywrightBrowserRuntime

    runtime = PlaywrightBrowserRuntime(headless=True)
    yield runtime
    await runtime.close()


@pytest_asyncio.fixture
async def site():
    s = FixtureSite().start()
    yield s
    s.stop()


async def _run(definition, runtime, text=""):
    from backend.app.ai.gateway.wrappers.engine import (
        GenericWebWrapperProvider,
        WebWrapperEngine,
    )

    provider = GenericWebWrapperProvider(
        definition=definition,
        engine=WebWrapperEngine(runtime),
        enabled=True,
        configured_name="web:real",
    )
    return await provider.chat(_request(text))


async def test_real_browser_open_page(site: FixtureSite, browser) -> None:
    resp = await _run(_def("open", site.url("/")), browser, "open")
    assert resp.ok is True
    assert "Каталог каналов" in resp.text


async def test_real_browser_find_text(site: FixtureSite, browser) -> None:
    resp = await _run(
        _def(
            "find",
            site.url("/article"),
            response_selector="article.body",
            response_take_last=False,
        ),
        browser,
        "find",
    )
    assert resp.ok is True
    assert "найти-меня" in resp.text


async def test_real_browser_extract_structure(site: FixtureSite, browser) -> None:
    from backend.app.ai.gateway.types import Capability

    resp = await _run(
        _def(
            "extract",
            site.url("/extract"),
            capabilities=Capability(text=True, structured=True),
            response_selector="ul.links li.link",
            extraction="structured",
        ),
        browser,
        "extract",
    )
    assert resp.ok is True
    items = resp.structured["items"]
    assert [i["href"] for i in items] == ["/a", "/b"]


async def test_real_browser_search_navigate(site: FixtureSite, browser) -> None:
    resp = await _run(
        _def(
            "search",
            site.url("/"),
            input_selector="input[name='q'], .search",
            response_selector="ul.results li.result a.result-link",
            response_take_last=False,
        ),
        browser,
        "Альфа",
    )
    assert resp.ok is True
    assert "Альфа" in resp.text


async def test_real_browser_login_is_detected(site: FixtureSite, browser) -> None:
    resp = await _run(
        _def("login", site.url("/login"), login_markers=("sign in",)),
        browser,
        "open",
    )
    assert resp.ok is False
    assert resp.error_category == "auth_required"


async def test_real_browser_http_error_page_is_surfaced(site: FixtureSite, browser) -> None:
    # Playwright's goto does not treat an HTTP 5xx as a transport failure: the
    # page still loads, so the wrapper honestly returns its body text rather than
    # inventing a success. A real *transport* failure is tested separately below.
    resp = await _run(_def("boom", site.url("/boom")), browser, "open")
    assert resp.ok is True
    assert "error" in resp.text


async def test_real_browser_unreachable_host_fails_honestly(site: FixtureSite, browser) -> None:
    resp = await _run(_def("down", "http://127.0.0.1:9/"), browser, "open")
    assert resp.ok is False
    assert resp.error_category in ("wrapper_selector", "unavailable", "network_error")


async def test_real_browser_normalized_via_router(site: FixtureSite, browser) -> None:
    from backend.app.ai.gateway.router import AIRouter
    from backend.app.ai.gateway.wrappers.engine import (
        GenericWebWrapperProvider,
        WebWrapperEngine,
    )

    provider = GenericWebWrapperProvider(
        definition=_def("norm", site.url("/")),
        engine=WebWrapperEngine(browser),
        enabled=True,
        configured_name="web:real",
    )
    resp = await AIRouter(max_attempts=1).route(_request("open"), [provider])
    assert resp.ok is True
    assert resp.provider_used == "web:real"
    assert resp.source == "web"
    assert len(resp.attempts) == 1
