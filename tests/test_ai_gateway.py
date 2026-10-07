"""Unit tests for the AI Gateway domain (v1.8).

No network, no credentials: providers use the fake HTTP transport and the fake
browser runtime. Verifies routing, failover, rate-limit cooldown, the wrapper
engine pipeline, honest unavailability and secret handling.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.ai.gateway.browser import FakeBrowserRuntime, PageSnapshot
from backend.app.ai.gateway.errors import BrowserUnavailableError
from backend.app.ai.gateway.http import FakeHttpTransport, HttpResponse
from backend.app.ai.gateway.providers import (
    FakeProvider,
    OpenAICompatibleProvider,
)
from backend.app.ai.gateway.reliability import (
    CircuitBreaker,
    HealthStore,
    backoff_delays,
)
from backend.app.ai.gateway.router import (
    STRATEGY_FREE_FIRST,
    AIRouter,
)
from backend.app.ai.gateway.types import (
    STATUS_NETWORK_ERROR,
    STATUS_RATE_LIMITED,
    Capability,
    ChatMessage,
    ChatRequest,
)
from backend.app.ai.gateway.wrappers.definition import GENERIC_DEFINITION, WrapperStep
from backend.app.ai.gateway.wrappers.engine import (
    GenericWebWrapperProvider,
    WebWrapperEngine,
)


def _req(text: str = "привет", **kw) -> ChatRequest:
    base = {
        "messages": [ChatMessage(role="user", content=text)],
        "requires": Capability(text=True),
        "correlation_id": "c1",
    }
    base.update(kw)
    return ChatRequest(**base)


# ---------------------------------------------------------------------------
# Reliability
# ---------------------------------------------------------------------------
def test_backoff_is_bounded() -> None:
    delays = backoff_delays(5, base=1, factor=2, max_delay=4)
    assert delays == [1, 2, 4, 4]


def test_circuit_breaker_opens_and_recovers() -> None:
    now = {"t": 0.0}
    cb = CircuitBreaker(threshold=2, cooldown=10, clock=lambda: now["t"])
    assert cb.allows()
    cb.record_failure()
    assert cb.allows()
    cb.record_failure()
    assert not cb.allows()  # open
    now["t"] = 11
    assert cb.allows()  # half-open probe
    cb.record_success()
    assert cb.state == "closed"


def test_health_store_rate_limit_sets_cooldown() -> None:
    now = {"t": 0.0}
    hs = HealthStore(clock=lambda: now["t"])
    hs.record_failure("p", status=STATUS_RATE_LIMITED, error="slow down")
    assert hs.rate_limited("p")
    now["t"] = 61
    assert not hs.rate_limited("p")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
async def test_router_failover_uses_second_provider() -> None:
    a = FakeProvider(provider="a", fail_with=STATUS_NETWORK_ERROR)
    b = FakeProvider(provider="b", reply="B")
    router = AIRouter(retry_delays=[0.0])
    resp = await router.route(_req(), [a, b])
    assert resp.ok
    assert resp.provider_used == "b"
    assert resp.fallback_used is True
    assert len(resp.attempts) == 2


async def test_router_all_failed_reports_error() -> None:
    a = FakeProvider(provider="a", fail_with=STATUS_NETWORK_ERROR)
    b = FakeProvider(provider="b", fail_with=STATUS_NETWORK_ERROR)
    router = AIRouter(retry_delays=[0.0])
    resp = await router.route(_req(), [a, b])
    assert not resp.ok
    assert resp.provider_used == ""
    assert "Проверьте сетевой доступ" in resp.error  # region/network guidance


async def test_router_free_first_orders_free_providers() -> None:
    paid = FakeProvider(provider="paid", cost="premium", reply="P")
    free = FakeProvider(provider="free", cost="free", reply="F")
    router = AIRouter(retry_delays=[0.0])
    resp = await router.route(_req(strategy=STRATEGY_FREE_FIRST), [paid, free])
    assert resp.provider_used == "free"


async def test_router_skips_provider_without_capability() -> None:
    text_only = FakeProvider(
        provider="t", capabilities=Capability(text=True), reply="T"
    )
    image_cap = FakeProvider(
        provider="i", capabilities=Capability(text=True, image=True), reply="I"
    )
    router = AIRouter(retry_delays=[0.0])
    req = _req(requires=Capability(text=True, image=True))
    resp = await router.route(req, [text_only, image_cap])
    assert resp.provider_used == "i"


async def test_router_pinned_provider() -> None:
    a = FakeProvider(provider="a", reply="A")
    b = FakeProvider(provider="b", reply="B")
    router = AIRouter(retry_delays=[0.0])
    resp = await router.route(_req(provider="b"), [a, b])
    assert resp.provider_used == "b"


async def test_router_no_provider_is_honest() -> None:
    router = AIRouter()
    resp = await router.route(_req(), [])
    assert not resp.ok
    assert resp.error_category == "no_provider"
    assert resp.status == "unavailable"


def test_router_describe_dry_run() -> None:
    a = FakeProvider(provider="a", cost="premium")
    b = FakeProvider(provider="b", cost="free")
    router = AIRouter()
    info = router.describe([a, b], _req(strategy=STRATEGY_FREE_FIRST))
    assert info["order"][0] == "b"


# ---------------------------------------------------------------------------
# API providers over the fake transport
# ---------------------------------------------------------------------------
async def test_openai_compatible_parses_response() -> None:
    transport = FakeHttpTransport(
        {
            "/chat/completions": HttpResponse(
                status=200,
                text='{"choices":[{"message":{"content":"ответ"}}]}',
            )
        }
    )
    provider = OpenAICompatibleProvider(
        model="m", api_key="k", transport=transport
    )
    resp = await provider.chat(_req())
    assert resp.ok
    assert resp.text == "ответ"


async def test_openai_compatible_auth_required() -> None:
    transport = FakeHttpTransport({"/chat/completions": HttpResponse(status=401)})
    provider = OpenAICompatibleProvider(model="m", api_key="", transport=transport)
    resp = await provider.chat(_req())
    assert not resp.ok
    assert resp.status == "auth_required"


async def test_openai_compatible_region_blocked() -> None:
    transport = FakeHttpTransport({"/chat/completions": HttpResponse(status=451)})
    provider = OpenAICompatibleProvider(model="m", api_key="k", transport=transport)
    resp = await provider.chat(_req())
    assert not resp.ok
    assert resp.status == "region_blocked"


async def test_openai_compatible_network_error() -> None:
    transport = FakeHttpTransport(
        {"/chat/completions": HttpResponse(error="ConnectError")}
    )
    provider = OpenAICompatibleProvider(model="m", api_key="k", transport=transport)
    resp = await provider.chat(_req())
    assert not resp.ok
    assert resp.status == "network_error"


# ---------------------------------------------------------------------------
# Web wrappers
# ---------------------------------------------------------------------------
async def test_wrapper_engine_happy_path() -> None:
    runtime = FakeBrowserRuntime(
        queue=[
            PageSnapshot(url="http://x", title="Chat", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", response_text="готовый ответ"),
        ]
    )
    engine = WebWrapperEngine(runtime)
    run = await engine.run(GENERIC_DEFINITION, _req("сделай пост"))
    assert run.ok
    assert run.text == "готовый ответ"
    assert ("fill", GENERIC_DEFINITION.input_selector, "сделай пост") in runtime.actions


async def test_wrapper_login_wall_is_auth_required() -> None:
    runtime = FakeBrowserRuntime(
        queue=[PageSnapshot(url="http://x", title="Sign in", text=" войти ")]
    )
    engine = WebWrapperEngine(runtime)
    run = await engine.run(GENERIC_DEFINITION, _req())
    assert not run.ok
    assert run.login_required


async def test_wrapper_missing_response_is_selector_error() -> None:
    runtime = FakeBrowserRuntime(
        queue=[
            PageSnapshot(url="http://x", title="Chat", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", response_text=""),
        ]
    )
    engine = WebWrapperEngine(runtime)
    run = await engine.run(GENERIC_DEFINITION, _req())
    assert not run.ok
    assert run.selector_error


async def test_wrapper_engine_raises_when_no_browser() -> None:
    runtime = FakeBrowserRuntime(_available=False)
    engine = WebWrapperEngine(runtime)
    with pytest.raises(BrowserUnavailableError):
        await engine.run(GENERIC_DEFINITION, _req())


async def test_wrapper_provider_disabled_is_unavailable() -> None:
    runtime = FakeBrowserRuntime(queue=[PageSnapshot(response_text="x")])
    engine = WebWrapperEngine(runtime)
    provider = GenericWebWrapperProvider(
        definition=GENERIC_DEFINITION, engine=engine, enabled=False
    )
    assert not provider.availability().usable
    resp = await provider.chat(_req())
    assert not resp.ok


async def test_wrapper_provider_enabled_returns_answer() -> None:
    runtime = FakeBrowserRuntime(
        queue=[
            PageSnapshot(url="http://x", title="Chat", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", response_text="web ответ"),
        ]
    )
    engine = WebWrapperEngine(runtime)
    provider = GenericWebWrapperProvider(
        definition=GENERIC_DEFINITION, engine=engine, enabled=True
    )
    assert provider.availability().usable
    resp = await provider.chat(_req())
    assert resp.ok
    assert resp.text == "web ответ"
    assert resp.source == "web"


async def test_wrapper_open_steps_are_executed() -> None:
    runtime = FakeBrowserRuntime(
        queue=[
            PageSnapshot(url="http://x", title="Chat", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", text="box"),
            PageSnapshot(url="http://x", response_text="ok"),
        ]
    )
    definition = replace(
        GENERIC_DEFINITION,
        open_steps=(WrapperStep(action="click", selector="#new-chat"),),
    )
    engine = WebWrapperEngine(runtime)
    run = await engine.run(definition, _req())
    assert run.ok
    assert ("click", "#new-chat", "") in runtime.actions


# ---------------------------------------------------------------------------
# Independent verification (v1.8 audit): behavior, not just presence
# ---------------------------------------------------------------------------
class _CountingProvider(FakeProvider):
    """Fails the first ``fail_times`` calls transiently, then succeeds."""

    def __init__(self, *, fail_times: int = 1, status: str = STATUS_NETWORK_ERROR, **kw):
        super().__init__(**kw)
        self.fail_times = fail_times
        self.status = status
        self.attempts = 0

    async def chat(self, request):  # type: ignore[override]
        self.attempts += 1
        if self.attempts <= self.fail_times:
            from backend.app.ai.gateway.types import ChatResponse

            return ChatResponse(
                ok=False,
                provider_used=self.name,
                error="transient",
                error_category=self.status,
                status=self.status,
            )
        return await super().chat(request)


async def test_response_level_transient_is_retried() -> None:
    """A returned transient response (not an exception) must honour max_attempts."""
    p = _CountingProvider(provider="flaky", reply="OK", fail_times=1)
    router = AIRouter(max_attempts=3, retry_delays=[0.0, 0.0])
    resp = await router.route(_req(), [p])
    assert p.attempts == 2  # retried once, then succeeded
    assert resp.ok and resp.text == "OK"


async def test_retry_is_bounded_by_max_attempts() -> None:
    p = _CountingProvider(provider="dead", fail_times=10)
    router = AIRouter(max_attempts=2, retry_delays=[0.0])
    resp = await router.route(_req(), [p])
    assert p.attempts == 2  # never more than max_attempts
    assert not resp.ok


async def test_exception_transient_is_retried() -> None:
    from backend.app.ai.gateway.errors import ProviderTimeoutError

    class RaiseOnce(FakeProvider):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.attempts = 0

        async def chat(self, request):  # type: ignore[override]
            self.attempts += 1
            if self.attempts == 1:
                raise ProviderTimeoutError(provider=self.name)
            return await super().chat(request)

    p = RaiseOnce(provider="raisey", reply="OK")
    router = AIRouter(max_attempts=3, retry_delays=[0.0, 0.0])
    resp = await router.route(_req(), [p])
    assert p.attempts == 2
    assert resp.ok and resp.text == "OK"


async def test_timeout_maps_to_network_error() -> None:
    """A transport timeout becomes a network_error the router can fall back on."""
    transport = FakeHttpTransport(
        {"/chat/completions": HttpResponse(error="TimeoutError", timed_out=True)}
    )
    provider = OpenAICompatibleProvider(model="m", api_key="k", transport=transport)
    resp = await provider.chat(_req())
    assert not resp.ok
    assert resp.status == STATUS_NETWORK_ERROR


def _manual_req():
    from backend.app.ai.gateway.router import STRATEGY_MANUAL

    return _req(strategy=STRATEGY_MANUAL)


async def test_failover_on_timeout_to_second_provider() -> None:
    transport = FakeHttpTransport(
        {"/chat/completions": HttpResponse(error="TimeoutError", timed_out=True)}
    )
    # priority forces the timeout provider to be tried first under manual strategy.
    slow = OpenAICompatibleProvider(
        provider="slow", model="m", api_key="k", transport=transport, priority=10
    )
    fast = FakeProvider(provider="fast", reply="F", priority=0)
    router = AIRouter(retry_delays=[0.0], max_attempts=1)
    resp = await router.route(_manual_req(), [slow, fast])
    assert resp.ok and resp.provider_used == "fast"
    assert resp.fallback_used is True
    assert len(resp.attempts) == 2  # slow was actually attempted and failed


async def test_failover_on_region_block_to_second_provider() -> None:
    transport = FakeHttpTransport({"/chat/completions": HttpResponse(status=451)})
    blocked = OpenAICompatibleProvider(
        provider="blocked", model="m", api_key="k", transport=transport, priority=10
    )
    other = FakeProvider(provider="other", reply="O", priority=0)
    router = AIRouter(retry_delays=[0.0], max_attempts=1)
    resp = await router.route(_manual_req(), [blocked, other])
    assert resp.ok and resp.provider_used == "other"
    assert resp.fallback_used is True


async def test_failover_on_rate_limit_to_second_provider() -> None:
    transport = FakeHttpTransport({"/chat/completions": HttpResponse(status=429)})
    limited = OpenAICompatibleProvider(
        provider="limited", model="m", api_key="k", transport=transport, priority=10
    )
    other = FakeProvider(provider="other", reply="O", priority=0)
    router = AIRouter(retry_delays=[0.0], max_attempts=1)
    resp = await router.route(_manual_req(), [limited, other])
    assert resp.ok and resp.provider_used == "other"
    assert resp.fallback_used is True


async def test_vision_requested_from_text_only_provider_is_not_served() -> None:
    """A text-only provider must never be chosen for an image request."""
    text_only = FakeProvider(provider="t", capabilities=Capability(text=True))
    router = AIRouter(retry_delays=[0.0])
    resp = await router.route(
        _req(requires=Capability(text=True, image=True)), [text_only]
    )
    assert not resp.ok
    assert resp.error_category == "no_provider"
    assert text_only.calls == []  # never even called


async def test_unknown_wrapper_is_never_available() -> None:
    """A wrapper whose definition is missing must not report AVAILABLE."""
    from backend.app.ai.gateway import registry as reg

    runtime = FakeBrowserRuntime(queue=[PageSnapshot(response_text="x")])
    cfg = reg.ProviderConfig(
        provider="ghost", kind=reg.KIND_WEB, wrapper_id="nope", enabled=True
    )
    provider = reg.build_provider(cfg, browser_runtime=runtime)
    assert not provider.availability().usable
    assert "не найдено" in provider.availability().detail


async def test_wrapper_identity_keeps_configured_name() -> None:
    from backend.app.ai.gateway import registry as reg

    runtime = FakeBrowserRuntime(queue=[PageSnapshot(response_text="x")])
    cfg = reg.ProviderConfig(
        provider="my-wrapper",
        kind=reg.KIND_WEB,
        wrapper_id="generic",
        enabled=True,
    )
    provider = reg.build_provider(cfg, browser_runtime=runtime)
    assert provider.name == "my-wrapper"
    assert provider.availability().usable


async def test_browser_crash_is_classified_not_raised() -> None:
    """A mid-pipeline browser exception becomes a classified failure at the
    provider boundary, so the router can move on instead of crashing."""
    runtime = FakeBrowserRuntime(
        queue=[PageSnapshot(url="http://x", title="Chat", text="box")],
        fail_on="fill",
    )
    engine = WebWrapperEngine(runtime)
    provider = GenericWebWrapperProvider(
        definition=GENERIC_DEFINITION, engine=engine, enabled=True
    )
    resp = await provider.chat(_req())
    assert not resp.ok
    assert resp.error_category == "wrapper_selector"  # degraded, not a crash
