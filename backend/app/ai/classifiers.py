"""Concrete classifiers (PHASE 7).

Three independent :class:`~backend.app.ai.types.Classifier` implementations:

* :class:`RulesClassifier` — wraps the deterministic Rules Engine (fast path).
* :class:`LlmClassifier` — builds the safe prompt, runs the local backend and
  strictly validates the JSON contract; raises an :class:`AiError` on failure.
* :class:`FakeClassifier` — a scriptable deterministic classifier for tests.

The routing between them lives in :mod:`backend.app.ai.router`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from backend.app.ai import inference
from backend.app.ai.backends.base import LlmBackend
from backend.app.ai.errors import (
    AiError,
)
from backend.app.ai.prompt import build_messages
from backend.app.ai.schema import parse_classification
from backend.app.ai.types import (
    SOURCE_AI,
    SOURCE_RULES,
    ClassificationContext,
    ClassificationResult,
    Tone,
)
from backend.app.core.logging import get_logger
from backend.app.rules.engine import RuleMatch, RulesEngine, RuleSpec

logger = get_logger(__name__)

_MAX_PROMPT_TOKENS = 256


@dataclass(slots=True)
class LlmRun:
    """Raw outcome of a backend call plus timing, before schema validation."""

    raw: str
    latency_ms: int


def result_from_rule_match(match: RuleMatch) -> ClassificationResult:
    """Adapt a Rules Engine match to the common classification result."""
    return ClassificationResult(
        category=match.category,
        confidence=match.confidence,
        source=match.source,
        tone=Tone.NEUTRAL,
        model="rules",
        processing_time_ms=0,
        matched_terms=list(match.matched_terms),
    )


class RulesClassifier:
    """Deterministic classifier backed by the Rules Engine."""

    name = "rules"

    def __init__(self, rules: list[RuleSpec]) -> None:
        self._engine = RulesEngine(rules)

    def classify(
        self, text: str, context: ClassificationContext | None = None
    ) -> ClassificationResult:
        match = self._engine.classify(text)
        result = result_from_rule_match(match)
        # Normalize the engine's "default" source to the public vocabulary.
        if result.source not in (SOURCE_RULES, "manual"):
            result.source = SOURCE_RULES if result.confidence > 0 else "default"
        return result


class LlmClassifier:
    """Classifier that runs a local :class:`LlmBackend` with strict validation.

    ``run`` (a :func:`backend.app.ai.inference.run_bounded`-compatible callable)
    is injectable so tests can exercise the timeout path without threads.
    """

    name = SOURCE_AI

    def __init__(
        self,
        backend: LlmBackend,
        *,
        model_label: str = "",
        timeout: float = 30.0,
        max_tokens: int = _MAX_PROMPT_TOKENS,
        run: object | None = None,
    ) -> None:
        self.backend = backend
        self.model_label = model_label or backend.name
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._run = run or inference.run_bounded

    def classify(
        self, text: str, context: ClassificationContext | None = None
    ) -> ClassificationResult:
        """Classify via the backend. Raises :class:`AiError` on any failure."""
        messages = build_messages(
            text,
            language=context.language if context else "",
            known_categories=context.known_categories if context else (),
        )
        started = time.monotonic()
        raw = self._invoke(messages)
        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            validated = parse_classification(raw)
        except AiError as exc:
            # Attach timing so metrics still see the work that happened.
            exc_message = exc.message
            raise _with_latency(exc, latency_ms, exc_message) from exc
        return ClassificationResult(
            category=validated.category,
            confidence=validated.confidence,
            source=SOURCE_AI,
            tone=validated.tone,
            model=self.model_label,
            processing_time_ms=latency_ms,
        )

    def _invoke(self, messages: list[dict[str, str]]) -> str:
        result = self._run(
            lambda: self.backend.complete(messages, max_tokens=self.max_tokens),
            self.timeout,
        )
        if isinstance(result, LlmRun):
            return result.raw
        return str(result)


def _with_latency(exc: AiError, latency_ms: int, message: str) -> AiError:
    # Record the latency on the exception for callers that care; harmless here.
    exc.processing_time_ms = latency_ms
    return exc


class FakeClassifier:
    """Deterministic, scriptable classifier for tests.

    Either returns a fixed result or delegates to a callable, so tests can
    simulate valid AI output, invalid output, timeouts and unavailability without
    a real model.
    """

    name = "fake"

    def __init__(
        self,
        *,
        result: ClassificationResult | None = None,
        handler: object | None = None,
    ) -> None:
        self._result = result
        self._handler = handler

    def classify(
        self, text: str, context: ClassificationContext | None = None
    ) -> ClassificationResult:
        handler = self._handler
        if callable(handler):
            return handler(text, context)  # type: ignore[no-any-return]
        if self._result is not None:
            return self._result
        raise AiError("fake classifier has no result configured")


__all__ = [
    "FakeClassifier",
    "LlmClassifier",
    "LlmRun",
    "RulesClassifier",
    "result_from_rule_match",
]
