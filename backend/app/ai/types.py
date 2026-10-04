"""Classifier abstraction and result types (PHASE 7).

The interface is deliberately tiny and free of any LLM/runtime detail so the
Reaction Manager depends only on the concept of "given text, return a category".
Swapping in a different backend (another GGUF runtime, a remote API classifier,
an embeddings-based one) is a wiring concern, never a business-logic change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from backend.app.rules.engine import Category

#: Classification sources exposed to the UI (D-034).
SOURCE_RULES = "rules"
SOURCE_DEFAULT = "default"
SOURCE_MANUAL = "manual"
SOURCE_AI = "llm"
SOURCE_FALLBACK = "fallback"

VALID_SOURCES = frozenset(
    {SOURCE_RULES, SOURCE_DEFAULT, SOURCE_MANUAL, SOURCE_AI, SOURCE_FALLBACK}
)

#: Classification modes for simulation / forced classification (D-033).
MODE_AUTO = "auto"        # rules-first, AI fallback when rules are unsure
MODE_RULES = "rules"      # rules only, never touch the AI
MODE_AI = "ai"            # AI only, fall back to rules when unavailable
#: Lightweight local encoder only (v1.1) — no model download, weak-PC friendly.
MODE_ENCODER = "encoder"

VALID_MODES = frozenset({MODE_AUTO, MODE_RULES, MODE_AI, MODE_ENCODER})


class Tone(StrEnum):
    """Allowed tone values returned by the AI (strictly validated)."""

    NEUTRAL = "neutral"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    WARM = "warm"
    ANGRY = "angry"
    SAD = "sad"
    HUMOROUS = "humorous"


class Intent(StrEnum):
    """Communicative intent of a post (v1.1, Russian-first).

    A small, fixed vocabulary an encoder classifier can map onto. Intent is
    *advisory*: it narrows the reaction set but never picks an emoji directly
    (the Reaction Planner and Rules Engine remain authoritative — D-005/D-032).
    """

    SUPPORT = "support"
    SYMPATHY = "sympathy"
    JOY = "joy"
    HUMOR = "humor"
    ANGER = "anger"
    SURPRISE = "surprise"
    LOVE = "love"
    NEUTRAL = "neutral"


#: Fixed set of categories the AI may return (must match the Rules Engine).
ALLOWED_CATEGORIES: frozenset[str] = frozenset(c.value for c in Category)

#: Fixed set of tones the AI may return.
ALLOWED_TONES: frozenset[str] = frozenset(t.value for t in Tone)

#: Fixed set of intents the AI may return.
ALLOWED_INTENTS: frozenset[str] = frozenset(i.value for i in Intent)


@dataclass(slots=True)
class ClassificationContext:
    """Optional, non-sensitive hints passed alongside the text.

    Kept intentionally small: nothing here may contain secrets, session data or
    Telegram identifiers. ``known_categories`` lets a backend be model-agnostic
    about the category vocabulary.
    """

    source: str = ""
    language: str = ""
    known_categories: tuple[str, ...] = ()


@dataclass(slots=True)
class ClassificationResult:
    """The single shape every classifier returns.

    ``source`` is one of ``rules`` / ``llm`` / ``manual`` / ``fallback``.
    ``error`` is a short, human-readable reason when the classifier failed — it
    is never a stack trace and never contains the post text.
    """

    category: Category
    confidence: float
    source: str
    tone: Tone = Tone.NEUTRAL
    #: Advisory communicative intent (v1.1). Defaults to neutral.
    intent: Intent = Intent.NEUTRAL
    #: Emoji the encoder backend suggests (advisory only; may be empty). The
    #: Reaction Planner intersects this with policy — the AI never decides alone.
    suggested_emoji: str = ""
    model: str = ""
    processing_time_ms: int = 0
    error: str = ""
    matched_terms: list[str] = field(default_factory=list)

    @property
    def is_neutral(self) -> bool:
        return self.category is Category.NEUTRAL

    @property
    def failed(self) -> bool:
        return bool(self.error)


@runtime_checkable
class Classifier(Protocol):
    """Independent classifier interface (rules, AI, or a router combining both).

    Implementations must be safe to call even when the underlying runtime is
    unavailable: they should return a valid :class:`ClassificationResult`
    (usually a neutral/fallback one) rather than raising for ordinary failures.
    """

    def classify(
        self, text: str, context: ClassificationContext | None = None
    ) -> ClassificationResult:
        """Classify ``text`` and return a result."""
        ...


__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_INTENTS",
    "ALLOWED_TONES",
    "MODE_AI",
    "MODE_AUTO",
    "MODE_ENCODER",
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
    "Intent",
    "Tone",
]
