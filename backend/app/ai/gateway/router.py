"""AIRouter — provider selection and failover (v1.8, requirements 3/9/13).

Given a request, the router:

1. filters providers that can serve it (capability + modality + health),
2. orders them by the requested *strategy* (free-first, cheapest, fastest, best
   quality, manual, auto),
3. tries them in order, retrying transient failures, and **falls over** to the
   next provider on timeout/error/rate-limit/region-block,
4. returns the first success with honest metadata (``provider_used``,
   ``fallback_used``, ``attempts``, ``latency_ms``).

It never hides a *critical* error: if every provider fails, the last real error
is surfaced. It never bypasses a regional block — it simply tries another
provider and, failing that, tells the user to check their own network access.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable

from backend.app.ai.gateway.errors import GatewayError
from backend.app.ai.gateway.provider import AIProvider
from backend.app.ai.gateway.reliability import (
    ConcurrencyLimiter,
    HealthStore,
    backoff_delays,
    is_transient,
)
from backend.app.ai.gateway.types import (
    STATUS_AUTH_REQUIRED,
    STATUS_NETWORK_ERROR,
    STATUS_UNAVAILABLE,
    ChatRequest,
    ChatResponse,
)

# Routing strategies (requirement 3).
STRATEGY_AUTO = "auto"
STRATEGY_FREE_FIRST = "free_first"
STRATEGY_CHEAPEST = "cheapest"
STRATEGY_FASTEST = "fastest"
STRATEGY_BEST = "best_quality"
STRATEGY_MANUAL = "manual"

STRATEGIES = (
    STRATEGY_AUTO,
    STRATEGY_FREE_FIRST,
    STRATEGY_CHEAPEST,
    STRATEGY_FASTEST,
    STRATEGY_BEST,
    STRATEGY_MANUAL,
)

_COST_RANK = {"free": 0, "cheap": 1, "standard": 2, "premium": 3}
#: Source preference for the default "auto" strategy: local first, then API, then web.
_SOURCE_RANK = {"local": 0, "api": 1, "web": 2}

#: Failure statuses that justify a different provider (never retry auth gaps).
_FALLBACK_STATUSES = frozenset(
    {STATUS_UNAVAILABLE, STATUS_NETWORK_ERROR, "rate_limited", "region_blocked"}
)


class AIRouter:
    """Chooses providers and runs failover."""

    def __init__(
        self,
        *,
        health: HealthStore | None = None,
        limiter: ConcurrencyLimiter | None = None,
        max_attempts: int = 3,
        retry_delays: list[float] | None = None,
        sleep: Callable[[float], object] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.health = health or HealthStore()
        self.limiter = limiter or ConcurrencyLimiter(limit=2)
        self.max_attempts = max(1, max_attempts)
        self.retry_delays = retry_delays or backoff_delays(self.max_attempts)
        self._sleep = sleep
        self._clock = clock or time.monotonic

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def _capable(self, provider: AIProvider, request: ChatRequest) -> bool:
        caps = provider.info.capabilities
        return caps.at_least(request.requires)

    def _order(self, providers: list[AIProvider], strategy: str) -> list[AIProvider]:
        strategy = strategy or STRATEGY_AUTO

        def cost(p: AIProvider) -> int:
            return _COST_RANK.get(p.info.cost, 2)

        def source(p: AIProvider) -> int:
            return _SOURCE_RANK.get(str(p.info.source), 1)

        if strategy == STRATEGY_FREE_FIRST:
            return sorted(providers, key=lambda p: (cost(p), source(p), -p.info.priority))
        if strategy == STRATEGY_CHEAPEST:
            return sorted(providers, key=lambda p: (cost(p), -p.info.priority))
        if strategy == STRATEGY_FASTEST:
            return sorted(
                providers,
                key=lambda p: (
                    self.health.status(p.name).latency_ms or 10_000,
                    -p.info.priority,
                ),
            )
        if strategy == STRATEGY_BEST:
            return sorted(
                providers,
                key=lambda p: (cost(p), -p.info.priority),
                reverse=True,
            )
        if strategy == STRATEGY_MANUAL:
            return sorted(providers, key=lambda p: -p.info.priority)
        # auto: local/free first, then cost, then declared priority.
        return sorted(providers, key=lambda p: (source(p), cost(p), -p.info.priority))

    def _eligible(self, providers: Iterable[AIProvider], request: ChatRequest) -> list[AIProvider]:
        out: list[AIProvider] = []
        for provider in providers:
            if not self._capable(provider, request):
                continue
            if not self.health.breaker(provider.name).allows():
                continue
            out.append(provider)
        return out

    def _by_name(self, providers: list[AIProvider], name: str) -> list[AIProvider]:
        return [p for p in providers if p.name == name]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    async def route(
        self,
        request: ChatRequest,
        providers: list[AIProvider],
    ) -> ChatResponse:
        strategy = request.strategy or STRATEGY_AUTO
        if request.provider:
            pinned = self._by_name(providers, request.provider)
            ordered = pinned or []
            strategy = STRATEGY_MANUAL
        else:
            ordered = self._order(self._eligible(providers, request), strategy)

        attempts: list[dict[str, object]] = []
        last_error = ""
        last_category = "no_provider"
        last_status = STATUS_UNAVAILABLE
        started = self._clock()

        if not ordered:
            return ChatResponse(
                ok=False,
                error="Нет доступного провайдера для этого запроса.",
                error_category="no_provider",
                request_id=request.correlation_id,
                status=STATUS_UNAVAILABLE,
                attempts=attempts,
                latency_ms=0,
            )

        for index, provider in enumerate(ordered):
            if not self.health.breaker(provider.name).allows():
                continue
            avail = provider.availability()
            if not avail.usable:
                # An auth gap is reported but not retried elsewhere silently
                # unless another provider can serve it.
                attempts.append(
                    {
                        "provider": provider.name,
                        "status": avail.status,
                        "detail": avail.detail,
                        "ok": False,
                    }
                )
                last_error = avail.detail or avail.status
                last_status = avail.status
                last_category = avail.status
                if avail.status == STATUS_AUTH_REQUIRED:
                    # remember but keep trying others
                    continue
                continue

            call_started = self._clock()
            response = await self._attempt(provider, request)
            latency_ms = int((self._clock() - call_started) * 1000)
            response.latency_ms = latency_ms
            response.attempts = attempts
            attempts.append(
                {
                    "provider": provider.name,
                    "status": response.status,
                    "ok": response.ok,
                    "latency_ms": latency_ms,
                }
            )
            if response.ok:
                self.health.record_success(provider.name, latency_ms=latency_ms)
                response.fallback_used = index > 0
                response.attempts = attempts
                response.latency_ms = int((self._clock() - started) * 1000)
                return response
            self.health.record_failure(
                provider.name,
                status=response.status,
                error=response.error,
            )
            last_error = response.error
            last_category = response.error_category or response.status
            last_status = response.status

        # Everything failed.
        detail = last_error
        if last_status in ("region_blocked", STATUS_NETWORK_ERROR):
            detail = (
                f"{last_error} Проверьте сетевой доступ самостоятельно — Suite не "
                "обходит региональные ограничения."
            ).strip()
        return ChatResponse(
            ok=False,
            error=detail or "Все провайдеры недоступны.",
            error_category=last_category,
            request_id=request.correlation_id,
            status=last_status,
            attempts=attempts,
            latency_ms=int((self._clock() - started) * 1000),
        )

    async def _attempt(self, provider: AIProvider, request: ChatRequest) -> ChatResponse:
        """Call one provider, retrying transient failures; never raises for a
        normal failure.

        A provider reports a transient failure two ways: it *raises* a
        :class:`GatewayError` (transport-level), or it *returns* a non-ok
        :class:`ChatResponse` whose status is transient (an HTTP 5xx/429 that the
        adapter mapped to a response). Both must honour ``max_attempts`` — the
        retry loop re-runs the call until a non-transient result or the budget is
        spent.
        """
        sleeper = self._sleep or asyncio.sleep
        last: ChatResponse | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self.limiter.run(
                    provider.name, lambda: provider.chat(request)
                )
            except GatewayError as exc:
                response = ChatResponse(
                    ok=False,
                    provider_used=provider.name,
                    error=exc.message,
                    error_category=exc.category,
                    request_id=request.correlation_id,
                    status=_category_status(exc.category),
                )
            except Exception as exc:
                response = ChatResponse(
                    ok=False,
                    provider_used=provider.name,
                    error=f"{type(exc).__name__}: {exc}",
                    error_category="error",
                    request_id=request.correlation_id,
                    status=STATUS_NETWORK_ERROR,
                )
            last = response
            if response.ok or not is_transient(response.status):
                return response
            if attempt >= self.max_attempts:
                break
            delay = (
                self.retry_delays[attempt - 1]
                if attempt - 1 < len(self.retry_delays)
                else 0.0
            )
            await sleeper(delay)
        assert last is not None
        return last

    def describe(self, providers: list[AIProvider], request: ChatRequest) -> dict[str, object]:
        """Dry-run selection for the UI (no calls)."""
        strategy = request.strategy or STRATEGY_AUTO
        ordered = self._order(self._eligible(providers, request), strategy)
        return {
            "strategy": strategy,
            "order": [p.name for p in ordered],
            "skipped": [
                p.name
                for p in providers
                if p not in ordered
            ],
        }


def _category_status(category: str) -> str:
    return {
        "auth_required": STATUS_AUTH_REQUIRED,
        "rate_limited": "rate_limited",
        "region_blocked": "region_blocked",
        "timeout": STATUS_NETWORK_ERROR,
        "network_error": STATUS_NETWORK_ERROR,
    }.get(category, STATUS_NETWORK_ERROR)


__all__ = [
    "STRATEGIES",
    "STRATEGY_AUTO",
    "STRATEGY_BEST",
    "STRATEGY_CHEAPEST",
    "STRATEGY_FASTEST",
    "STRATEGY_FREE_FIRST",
    "STRATEGY_MANUAL",
    "AIRouter",
]
