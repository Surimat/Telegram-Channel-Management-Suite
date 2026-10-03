"""Tiny AI classifier core (PHASE 7).

A fully optional, local-only post classifier used as a *fallback* after the
deterministic Rules Engine. Nothing in this package imports Telegram or FastAPI:
the AI is a pure domain concern reachable only through the :class:`Classifier`
protocol (D-001 pattern).

Design highlights (see ``agent/DECISIONS.md`` D-031…D-035):

* The Rules Engine is the primary classifier; AI is additive and never a single
  point of failure for the Reaction Manager.
* The official ``llama.cpp`` runtime is optional and model-agnostic; business
  logic only ever sees :class:`ClassificationResult`.
* Post text is untrusted input: it is passed to the model as DATA inside an
  explicit delimitation, never as instructions (prompt-injection safety).
"""

from __future__ import annotations

from backend.app.ai.types import (
    MODE_AI,
    MODE_AUTO,
    MODE_RULES,
    SOURCE_AI,
    SOURCE_DEFAULT,
    SOURCE_FALLBACK,
    SOURCE_MANUAL,
    SOURCE_RULES,
    VALID_MODES,
    VALID_SOURCES,
    ClassificationContext,
    ClassificationResult,
    Classifier,
    Tone,
)

__all__ = [
    "MODE_AI",
    "MODE_AUTO",
    "MODE_RULES",
    "SOURCE_AI",
    "SOURCE_DEFAULT",
    "SOURCE_FALLBACK",
    "SOURCE_MANUAL",
    "SOURCE_RULES",
    "VALID_MODES",
    "VALID_SOURCES",
    "ClassificationContext",
    "ClassificationResult",
    "Classifier",
    "Tone",
]
