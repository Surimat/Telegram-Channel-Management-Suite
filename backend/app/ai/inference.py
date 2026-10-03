"""Single-concurrency, timeout-bounded inference (PHASE 7).

Critical for weak Windows PCs (D-035): at most **one** inference runs at a time,
and every call is bounded by a timeout. A module-level single-worker executor
provides both guarantees:

* serialization — submissions queue behind the one worker;
* timeout — ``future.result(timeout=...)`` raises after the limit without
  spawning extra generations.

A timed-out generation keeps the worker busy until it finishes on its own, which
is exactly the "no parallel inference" behaviour we want.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import TypeVar

from backend.app.ai.errors import InferenceTimeoutError

T = TypeVar("T")

#: Process-wide single-worker pool. One inference at a time, never more.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-inference")


def run_bounded(fn: Callable[[], T], timeout: float) -> T:
    """Run ``fn`` on the shared single-worker executor, bounded by ``timeout``."""
    future = _EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError as exc:
        raise InferenceTimeoutError() from exc


def shutdown_executor() -> None:
    """Shut the executor down (used by tests for a clean process exit)."""
    _EXECUTOR.shutdown(wait=False, cancel_futures=True)


__all__ = ["run_bounded", "shutdown_executor"]
