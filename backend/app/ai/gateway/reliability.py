"""Reliability primitives for the AI Gateway (v1.8, requirement 10).

Small, dependency-free building blocks so one broken provider can never block
the rest:

* :class:`CircuitBreaker` — per-provider open/half-open/closed state.
* :class:`HealthStore` — live availability, latency, failure counts, cooldown.
* :func:`backoff_delays` / :func:`with_retry` — retry with exponential backoff
  and jitter, never sleeping longer than the caller's budget.
* :class:`ConcurrencyLimiter` — a bounded semaphore per provider.
* :func:`new_correlation_id` — request correlation ids.

Time is read through an injectable ``clock`` so tests are deterministic.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from backend.app.ai.gateway.types import (
    STATUS_AVAILABLE,
    STATUS_NETWORK_ERROR,
    STATUS_RATE_LIMITED,
    STATUS_REGION_BLOCKED,
    STATUS_UNAVAILABLE,
    Availability,
    ProviderStatus,
)

Clock = Callable[[], float]


def _default_clock() -> float:
    return time.monotonic()


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def backoff_delays(
    attempts: int,
    *,
    base: float = 0.5,
    factor: float = 2.0,
    max_delay: float = 8.0,
    jitter: float = 0.0,
    rng: random.Random | None = None,
) -> list[float]:
    """Return the delay before each retry (``attempts - 1`` values)."""
    rng = rng or random.Random(0)
    delays: list[float] = []
    for i in range(max(0, attempts - 1)):
        raw = min(max_delay, base * (factor**i))
        if jitter:
            raw += rng.uniform(0.0, jitter)
        delays.append(raw)
    return delays


async def with_retry(
    fn: Callable[[], Awaitable[object]],
    *,
    max_attempts: int = 3,
    delays: list[float] | None = None,
    on_error: Callable[[int, BaseException], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> object:
    """Call ``fn`` up to ``max_attempts`` times, sleeping ``delays`` between.

    Only used for *transient* failures; callers decide which errors are retried.
    The last exception is re-raised so the caller can fall back to another
    provider.
    """
    sleeper = sleep or asyncio.sleep
    wait = delays if delays is not None else backoff_delays(max_attempts)
    last: BaseException | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return await fn()
        except BaseException as exc:
            last = exc
            if on_error is not None:
                on_error(attempt, exc)
            if attempt >= max(1, max_attempts):
                break
            await sleeper(wait[attempt - 1] if attempt - 1 < len(wait) else 0.0)
    assert last is not None
    raise last


@dataclass
class CircuitBreaker:
    """A per-provider breaker.

    ``threshold`` consecutive failures open the breaker; after ``cooldown``
    seconds it moves to half-open and lets a single probe through.
    """

    threshold: int = 3
    cooldown: float = 30.0
    clock: Clock = _default_clock
    failures: int = 0
    opened_at: float = 0.0
    state: str = "closed"  # closed | open | half_open

    def _trip(self) -> None:
        self.state = "open"
        self.opened_at = self.clock()

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"
        self.opened_at = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.state == "half_open" or self.failures >= self.threshold:
            self._trip()

    def allows(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.clock() - self.opened_at >= self.cooldown:
                self.state = "half_open"
                return True
            return False
        # half_open: a single probe is allowed.
        return True

    @property
    def retry_after(self) -> float:
        if self.state != "open":
            return 0.0
        return max(0.0, self.cooldown - (self.clock() - self.opened_at))


@dataclass
class HealthStore:
    """Process-wide live health of every provider, keyed by provider name."""

    clock: Clock = _default_clock
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    statuses: dict[str, ProviderStatus] = field(default_factory=dict)
    #: Extra cooldown set by a rate-limit response.
    _rate_limited_until: dict[str, float] = field(default_factory=dict)

    def breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self.breakers:
            self.breakers[provider] = CircuitBreaker(clock=self.clock)
        return self.breakers[provider]

    def status(self, provider: str) -> ProviderStatus:
        if provider not in self.statuses:
            self.statuses[provider] = ProviderStatus(provider=provider)
        return self.statuses[provider]

    def rate_limited(self, provider: str) -> bool:
        return self.clock() < self._rate_limited_until.get(provider, 0.0)

    def cooldown(self, provider: str, seconds: float) -> None:
        self._rate_limited_until[provider] = self.clock() + max(0.0, seconds)
        self.status(provider).cooldown_until = self._rate_limited_until[provider]

    def record_success(
        self, provider: str, *, latency_ms: int = 0, when: str = ""
    ) -> None:
        self.breaker(provider).record_success()
        st = self.status(provider)
        st.availability = Availability(status=STATUS_AVAILABLE)
        st.latency_ms = latency_ms
        st.last_error = ""
        if when:
            st.last_success = when

    def record_failure(
        self, provider: str, *, status: str = STATUS_NETWORK_ERROR, error: str = ""
    ) -> None:
        self.breaker(provider).record_failure()
        st = self.status(provider)
        st.availability = Availability(status=status, detail=error)
        st.last_error = error
        st.failure_count += 1
        if status == STATUS_RATE_LIMITED:
            self.cooldown(provider, 60.0)

    def set_status(self, provider: str, availability: Availability) -> None:
        self.status(provider).availability = availability

    def reset(self) -> None:
        self.breakers.clear()
        self.statuses.clear()
        self._rate_limited_until.clear()


#: Statuses that justify trying a *different* provider instead of the same one
#: again.
_TRANSIENT = frozenset(
    {STATUS_UNAVAILABLE, STATUS_NETWORK_ERROR, STATUS_RATE_LIMITED, STATUS_REGION_BLOCKED}
)


def is_transient(status: str) -> bool:
    return status in _TRANSIENT


class ConcurrencyLimiter:
    """A bounded per-provider concurrency guard (no request stampede)."""

    def __init__(self, limit: int = 2) -> None:
        self.limit = max(1, limit)
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def _sem(self, key: str) -> asyncio.Semaphore:
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(self.limit)
        return self._semaphores[key]

    async def run(self, key: str, fn: Callable[[], Awaitable[object]]) -> object:
        sem = self._sem(key)
        async with sem:
            return await fn()


__all__ = [
    "CircuitBreaker",
    "ConcurrencyLimiter",
    "HealthStore",
    "backoff_delays",
    "is_transient",
    "new_correlation_id",
    "with_retry",
]
