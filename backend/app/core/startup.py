"""Startup readiness helpers.

The portable launcher waits for the server to answer ``/health`` before opening
a browser (no fixed sleep). The same wait is needed by the auto-updater, which
must confirm a newly installed version is healthy before declaring success and
roll back otherwise. Keeping one implementation avoids two subtly different
"is it up yet?" loops.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 0.4


@dataclass
class ReadinessResult:
    """Outcome of waiting for a server to become ready."""

    ready: bool
    attempts: int
    waited_seconds: float
    last_error: str = ""


def _probe(url: str, timeout: float) -> tuple[bool, str]:
    """Return ``(ok, error)`` for a single ``/health`` request."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if 200 <= getattr(resp, "status", 200) < 300:
                return True, ""
            return False, f"HTTP {getattr(resp, 'status', '?')}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, str(exc)


def wait_for_health(
    base_url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    request_timeout: float = 2.0,
) -> ReadinessResult:
    """Poll ``base_url`` + ``/health`` until it answers or ``timeout`` elapses.

    Never raises: a failure is reported as ``ready=False`` with the last error,
    so callers can show a friendly message instead of a traceback.
    """
    health_url = base_url.rstrip("/") + "/health"
    deadline = time.monotonic() + max(timeout, 0.0)
    attempts = 0
    last_error = ""
    while True:
        attempts += 1
        ok, error = _probe(health_url, request_timeout)
        if ok:
            return ReadinessResult(ready=True, attempts=attempts, waited_seconds=0.0)
        last_error = error
        if time.monotonic() >= deadline:
            return ReadinessResult(
                ready=False,
                attempts=attempts,
                waited_seconds=max(timeout, 0.0),
                last_error=last_error,
            )
        time.sleep(max(poll_interval, 0.01))


__all__ = ["DEFAULT_POLL_INTERVAL", "DEFAULT_TIMEOUT", "ReadinessResult", "wait_for_health"]
