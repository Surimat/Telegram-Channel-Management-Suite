"""Web Wrapper benchmark — reproducible browser scenarios (v1.8.x verification).

Runs the *real* wrapper pipeline (engine → provider → router) over the local
fixture site and records a machine-readable result at
``agent/WEB_WRAPPER_BENCHMARK.json``:

    open page → find text → extract structured data → search/navigate →
    normalized result (through the gateway response shape).

It uses :class:`FixtureBrowserRuntime` (real HTTP + real HTML), so it is fully
deterministic and needs **no external site, no browser binary and no AI
credential**. The genuine Playwright path is proven by
``tests/test_web_wrapper_playwright_integration.py`` (skipped when absent).

Run directly to regenerate the artifact:

    PYTHONPATH=. python tests/web_wrapper_bench.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.ai.gateway.types import Capability, ChatMessage, ChatRequest  # noqa: E402
from tests.support.web_fixtures import FixtureBrowserRuntime, FixtureSite  # noqa: E402


@dataclass(slots=True)
class Scenario:
    name: str
    description: str
    definition: object  # WrapperDefinition
    request: ChatRequest
    check: object  # callable(ChatResponse) -> tuple[bool, str]


@dataclass(slots=True)
class ScenarioResult:
    name: str
    description: str
    success: bool
    latency_ms: int
    timeout: bool
    extraction_correct: bool
    provider_used: str
    fallback_used: bool
    browser_errors: list[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "timeout": self.timeout,
            "extraction_correct": self.extraction_correct,
            "provider_used": self.provider_used,
            "fallback_used": self.fallback_used,
            "browser_errors": self.browser_errors,
            "detail": self.detail,
        }


def _definitions():
    from backend.app.ai.gateway.wrappers.definition import WrapperDefinition

    open_def = WrapperDefinition(
        id="fixture-open",
        name="Fixture Open",
        website="/",
        capabilities=Capability(text=True),
        input_selector="",
        response_selector="",
        extraction="text",
        enabled=True,
    )
    find_def = WrapperDefinition(
        id="fixture-find",
        name="Fixture Find",
        website="/article",
        capabilities=Capability(text=True),
        response_selector="article.body",
        response_take_last=False,
        extraction="text",
        enabled=True,
    )
    extract_def = WrapperDefinition(
        id="fixture-extract",
        name="Fixture Extract",
        website="/extract",
        capabilities=Capability(text=True, structured=True),
        response_selector="ul.links li.link",
        extraction="structured",
        enabled=True,
    )
    nav_def = WrapperDefinition(
        id="fixture-nav",
        name="Fixture Navigate",
        website="/",
        capabilities=Capability(text=True),
        # open with a search then read results
        response_selector="ul.results li.result a.result-link",
        response_take_last=False,
        extraction="text",
        enabled=True,
    )
    return open_def, find_def, extract_def, nav_def


def build_scenarios(site: FixtureSite) -> list[Scenario]:
    open_def, find_def, extract_def, _nav = _definitions()

    def req(text: str = "", *, url_def=None) -> ChatRequest:
        return ChatRequest(
            messages=[ChatMessage(role="user", content=text)],
            correlation_id=f"bench-{text or 'x'}",
        )

    # 1. open a page and confirm the title/text is visible in the snapshot.
    async def check_open(resp) -> tuple[bool, str]:
        ok = resp.ok and "Каталог каналов" in resp.text
        return ok, "title/text present" if ok else f"text={resp.text[:60]!r}"

    # 2. find text on a page (article body).
    async def check_find(resp) -> tuple[bool, str]:
        ok = resp.ok and "найти-меня" in resp.text
        return ok, "phrase found" if ok else f"text={resp.text[:60]!r}"

    # 3. extract structured data (links with hrefs).
    async def check_extract(resp) -> tuple[bool, str]:
        items = (resp.structured or {}).get("items") or []
        hrefs = [i.get("href") for i in items]
        ok = resp.ok and "/a" in hrefs and "/b" in hrefs
        return ok, f"{len(items)} items" if ok else f"items={items!r}"

    # 4. search / navigate: fill the search box, read results.
    async def check_nav(resp) -> tuple[bool, str]:
        ok = resp.ok and "Альфа" in resp.text
        return ok, "results read" if ok else f"text={resp.text[:60]!r}"

    from backend.app.ai.gateway.wrappers.definition import WrapperDefinition

    # For the nav scenario we open "/" then fill the search box (→ /search?q=)
    # and read the result links.
    nav_def2 = WrapperDefinition(
        id="fixture-nav",
        name="Fixture Navigate",
        website="/",
        capabilities=Capability(text=True),
        open_steps=(),
        input_selector="input[name='q'], .search",
        response_selector="ul.results li.result a.result-link",
        response_take_last=False,
        extraction="text",
        enabled=True,
    )

    return [
        Scenario(
            "open_page",
            "Открыть страницу и прочитать заголовок",
            open_def,
            req("open"),
            check_open,
        ),
        Scenario("find_text", "Найти текст на странице", find_def, req("find"), check_find),
        Scenario(
            "extract_data",
            "Извлечь структурированные данные",
            extract_def,
            req("extract"),
            check_extract,
        ),
        Scenario("search_nav", "Поиск и навигация", nav_def2, req("Альфа"), check_nav),
    ]


async def run_benchmark() -> dict[str, object]:
    from backend.app.ai.gateway.wrappers.engine import (
        GenericWebWrapperProvider,
        WebWrapperEngine,
    )

    site = FixtureSite().start()
    results: list[ScenarioResult] = []
    try:
        scenarios = build_scenarios(site)
        for sc in scenarios:
            runtime = FixtureBrowserRuntime(site)
            engine = WebWrapperEngine(runtime)
            provider = GenericWebWrapperProvider(
                definition=sc.definition,
                engine=engine,
                enabled=True,
                configured_name="web:fixture",
            )
            started = time.perf_counter()
            errors: list[str] = []
            timeout = False
            try:
                resp = await provider.chat(sc.request)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(type(exc).__name__)
                resp = None
            latency = int((time.perf_counter() - started) * 1000)
            success = False
            extraction_ok = False
            detail = ""
            if resp is not None:
                timeout = resp.status == "network_error" and "timeout" in (resp.error or "").lower()
                success, detail = await sc.check(resp)
                extraction_ok = "extract" in sc.name and success
            else:
                detail = "no response"
            results.append(
                ScenarioResult(
                    name=sc.name,
                    description=sc.description,
                    success=success,
                    latency_ms=latency,
                    timeout=timeout,
                    extraction_correct=extraction_ok,
                    provider_used=getattr(resp, "provider_used", ""),
                    fallback_used=bool(getattr(resp, "fallback_used", False)),
                    browser_errors=errors
                    + ([getattr(resp, "error", "")] if resp and not resp.ok else []),
                    detail=detail,
                )
            )

        results.extend(await _run_router_scenarios(site))
    finally:
        site.stop()

    passed = sum(1 for r in results if r.success)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": "fixture-http (real HTTP + real HTML)",
        "external_network": False,
        "scenarios_total": len(results),
        "scenarios_passed": passed,
        "scenarios_failed": len(results) - passed,
        "success_rate": round(passed / len(results) * 100, 1) if results else 0.0,
        "results": [r.as_dict() for r in results],
    }


def _result(
    name,
    description,
    ok,
    latency,
    detail,
    *,
    timeout=False,
    extract=False,
    provider="",
    fallback=False,
    errors=None,
):
    return ScenarioResult(
        name=name,
        description=description,
        success=bool(ok),
        latency_ms=latency,
        timeout=timeout,
        extraction_correct=extract,
        provider_used=provider,
        fallback_used=fallback,
        browser_errors=list(errors or []),
        detail=detail,
    )


async def _run_router_scenarios(site: FixtureSite) -> list[ScenarioResult]:
    """Router-level scenarios: normalized response end-to-end + failover."""
    from backend.app.ai.gateway.providers import FakeProvider
    from backend.app.ai.gateway.router import STRATEGY_FREE_FIRST, AIRouter
    from backend.app.ai.gateway.types import SourceKind
    from backend.app.ai.gateway.wrappers.engine import (
        GenericWebWrapperProvider,
        WebWrapperEngine,
    )

    out: list[ScenarioResult] = []
    open_def, _, _, _ = _definitions()

    # 5. normalized response: the web wrapper succeeds via the router and the
    #    response carries the unified metadata (provider_used/attempts/status).
    runtime = FixtureBrowserRuntime(site)
    web = GenericWebWrapperProvider(
        definition=open_def,
        engine=WebWrapperEngine(runtime),
        enabled=True,
        configured_name="web:fixture",
    )
    router = AIRouter(max_attempts=1)
    started = time.perf_counter()
    resp = await router.route(
        ChatRequest(
            messages=[ChatMessage(role="user", content="open")],
            correlation_id="bench-router",
        ),
        [web],
    )
    latency = int((time.perf_counter() - started) * 1000)
    normalized = (
        resp.ok
        and resp.provider_used == "web:fixture"
        and resp.source == SourceKind.WEB
        and resp.status == "available"
        and isinstance(resp.attempts, list)
        and len(resp.attempts) == 1
    )
    out.append(
        _result(
            "normalized_response",
            "Единый нормализованный ответ через роутер",
            normalized,
            latency,
            f"ok={resp.ok} provider={resp.provider_used} source={resp.source} status={resp.status}",
            provider=resp.provider_used,
        )
    )

    # 6. failover: the first provider fails past its retries (transient) → the
    #    router falls back to the next provider and flags it.
    bad_api = FakeProvider(provider="api-bad", fail_with="network_error")
    good_api = FakeProvider(provider="api-good", reply="ответ api", source=SourceKind.API)
    router2 = AIRouter(max_attempts=1)
    started = time.perf_counter()
    resp2 = await router2.route(
        ChatRequest(
            messages=[ChatMessage(role="user", content="hi")],
            strategy=STRATEGY_FREE_FIRST,
            correlation_id="bench-failover",
        ),
        [bad_api, good_api],
    )
    latency = int((time.perf_counter() - started) * 1000)
    failover_ok = resp2.ok and resp2.provider_used == "api-good" and resp2.fallback_used is True
    out.append(
        _result(
            "failover_transient",
            "Провайдер падает (transient) → отвечает резервный",
            failover_ok,
            latency,
            (
                f"provider={resp2.provider_used} fallback={resp2.fallback_used} "
                f"attempts={len(resp2.attempts)}"
            ),
            provider=resp2.provider_used,
            fallback=resp2.fallback_used,
        )
    )

    # 7. free-first ordering: a free/local provider is tried before a paid one.
    free = FakeProvider(
        provider="free-local", reply="free", cost="free", source=SourceKind.LOCAL, priority=0
    )
    paid = FakeProvider(
        provider="paid-api", reply="paid", cost="premium", source=SourceKind.API, priority=9
    )
    router3 = AIRouter(max_attempts=1)
    # FakeProvider sources are LOCAL/API → free-first must order free before paid.
    resp3 = await router3.route(
        ChatRequest(
            messages=[ChatMessage(role="user", content="hi")],
            strategy=STRATEGY_FREE_FIRST,
            correlation_id="bench-free",
        ),
        [paid, free],
    )
    order = router3.describe([paid, free], ChatRequest(strategy=STRATEGY_FREE_FIRST))["order"]
    free_ok = resp3.provider_used == "free-local" and order[0] == "free-local"
    out.append(
        _result(
            "free_first_order",
            "Free-first: сначала бесплатный/локальный",
            free_ok,
            0,
            f"order={order} used={resp3.provider_used}",
            provider=resp3.provider_used,
        )
    )
    return out


def main() -> int:
    data = asyncio.run(run_benchmark())
    out = REPO_ROOT / "agent" / "WEB_WRAPPER_BENCHMARK.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: data[k] for k in ("scenarios_total", "scenarios_passed", "scenarios_failed")}
    print(json.dumps(summary, ensure_ascii=False))
    print(f"wrote {out}")
    return 0 if data["scenarios_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
