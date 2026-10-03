"""Deterministic fake LLM backend (PHASE 7).

Used in tests and in offline mode so the entire AI pipeline (prompt → backend →
schema validation → routing) can be exercised without any real model. It is a
tiny keyword heuristic that returns the **same JSON contract** a real model
would, plus a scripted-response mode for tests that need malformed output,
timeouts or load failures.
"""

from __future__ import annotations

import threading
import time

from backend.app.ai.errors import ModelLoadError
from backend.app.rules.engine import Category

#: Ordered keyword → category hints. Deterministic and dependency-free.
_KEYWORD_HINTS: tuple[tuple[str, Category], ...] = (
    ("донат", Category.DONATION),
    ("donate", Category.DONATION),
    ("поддерж", Category.SUPPORT),
    ("support", Category.SUPPORT),
    ("новост", Category.NEWS),
    ("news", Category.NEWS),
    ("объявлен", Category.ANNOUNCEMENT),
    ("announce", Category.ANNOUNCEMENT),
    ("смешн", Category.FUNNY),
    ("шутк", Category.FUNNY),
    ("funny", Category.FUNNY),
    ("груст", Category.SAD),
    ("sad", Category.SAD),
    ("зл", Category.ANGRY),
    ("angry", Category.ANGRY),
    ("мил", Category.CUTE),
    ("cute", Category.CUTE),
)


class FakeLlmBackend:
    """A scriptable, deterministic :class:`LlmBackend` implementation."""

    name = "fake"

    def __init__(
        self,
        *,
        response: str | None = None,
        fail_load: bool = False,
        delay: float = 0.0,
        available: bool = True,
        auto_load: bool = True,
    ) -> None:
        self._scripted = response
        self._fail_load = fail_load
        self._delay = delay
        self._available = available
        self._auto_load = auto_load
        self._loaded = False
        self._lock = threading.Lock()
        self.load_calls = 0
        self.complete_calls = 0

    @property
    def available(self) -> bool:
        return self._available

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        with self._lock:
            self.load_calls += 1
            if self._fail_load:
                raise ModelLoadError("scripted fake load failure")
            self._loaded = True

    def unload(self) -> None:
        with self._lock:
            self._loaded = False

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> str:
        if self._delay:
            time.sleep(self._delay)
        if self._scripted is not None:
            return self._scripted
        if self._auto_load and not self._loaded:
            self.load()
        self.complete_calls += 1
        text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                text = message.get("content", "")
                break
        # Only inspect the delimited DATA block, not the trusted metadata.
        data = text
        begin = text.find("BEGIN_")
        end = text.find("END_")
        if begin != -1 and end != -1 and end > begin:
            newline = text.find("\n", begin)
            if newline != -1:
                data = text[newline + 1 : end]
        lowered = data.lower()
        for keyword, category in _KEYWORD_HINTS:
            if keyword in lowered:
                return f'{{"category": "{category.value}", "tone": "neutral", "confidence": 0.86}}'
        return '{"category": "neutral", "tone": "neutral", "confidence": 0.4}'


__all__ = ["FakeLlmBackend"]
