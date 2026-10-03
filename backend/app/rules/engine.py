"""Rules Engine (PHASE 3).

A fully deterministic, LLM-free classifier. It maps a post's text to one of the
fixed categories and to the reaction policy (allowed / preferred / forbidden
emoji) for that category.

Design goals (see ``agent/DECISIONS.md`` D-005, D-020):

* No Telegram and no AI dependency — pure, unit-testable logic.
* Deterministic: identical input → identical output.
* Editable from the UI: rules are plain data (``RuleSpec``), loaded from the DB.
* An explicit extension point for a future tiny classifier (PHASE 7): the engine
  exposes :class:`TextClassifier`; an AI classifier can be composed *after* it.

The AI is intentionally **not** implemented here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Category(StrEnum):
    """Fixed set of post categories (minimum required by the specification)."""

    DONATION = "donation"
    NEWS = "news"
    FUNNY = "funny"
    SAD = "sad"
    ANGRY = "angry"
    CUTE = "cute"
    SUPPORT = "support"
    ANNOUNCEMENT = "announcement"
    NEUTRAL = "neutral"


#: Sensible default reaction policy per category (allowed, preferred).
DEFAULT_CATEGORY_REACTIONS: dict[Category, tuple[list[str], list[str]]] = {
    Category.DONATION: (["❤️", "🙏", "👍"], ["❤️", "🙏"]),
    Category.NEWS: (["👍", "🔥", "🎉"], ["👍"]),
    Category.FUNNY: (["😂", "🤣", "😁"], ["😂"]),
    Category.SAD: (["😢", "😭", "❤️"], ["❤️"]),
    Category.ANGRY: (["😡", "👎", "🤬"], ["👎"]),
    Category.CUTE: (["🥰", "😍", "❤️"], ["❤️"]),
    Category.SUPPORT: (["🙏", "❤️", "👍"], ["🙏", "❤️"]),
    Category.ANNOUNCEMENT: (["👍", "🔥", "🎉"], ["👍"]),
    Category.NEUTRAL: (["👍", "❤️", "🔥"], []),
}

CATEGORY_TITLES: dict[Category, str] = {
    Category.DONATION: "Донат / поддержка",
    Category.NEWS: "Новость",
    Category.FUNNY: "Смешное",
    Category.SAD: "Грустное",
    Category.ANGRY: "Злое / возмущение",
    Category.CUTE: "Милое",
    Category.SUPPORT: "Поддержка",
    Category.ANNOUNCEMENT: "Анонс",
    Category.NEUTRAL: "Обычное",
}


@dataclass(slots=True)
class RuleSpec:
    """A single, editable classification rule.

    All matching is done on a lowercased copy of the text. ``keywords`` are
    single words, ``phrases`` are multi-word substrings, ``regexes`` are optional
    patterns. Any ``exclusions`` present disable the rule for that text.
    """

    category: Category
    id: str = ""
    name: str = ""
    keywords: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    regexes: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    allowed_reactions: list[str] = field(default_factory=list)
    preferred_reactions: list[str] = field(default_factory=list)
    forbidden_reactions: list[str] = field(default_factory=list)
    min_confidence: float = 0.3
    # A forced rule wins over higher scores (manual override), e.g. an admin
    # pins a specific post to a category.
    manual_override: bool = False
    # Optional language gate ("ru", "en", "any"). Empty means any language.
    language: str = ""


@dataclass(slots=True)
class RuleMatch:
    """Result of classifying a text."""

    category: Category
    confidence: float
    source: str = "rules"  # "rules" | "default" | "manual" | "ai"
    rule_id: str = ""
    matched_terms: list[str] = field(default_factory=list)
    allowed_reactions: list[str] = field(default_factory=list)
    preferred_reactions: list[str] = field(default_factory=list)
    forbidden_reactions: list[str] = field(default_factory=list)

    @property
    def is_neutral(self) -> bool:
        return self.category is Category.NEUTRAL


@runtime_checkable
class TextClassifier(Protocol):
    """Extension point for classifiers (Rules now, tiny AI later)."""

    def classify(self, text: str) -> RuleMatch:
        """Return the best category match for ``text``."""


# Relative weight of each match type. Phrases are more specific than single
# keywords, regexes are the most deliberate, so they score higher.
_KEYWORD_WEIGHT = 1
_PHRASE_WEIGHT = 2
_REGEX_WEIGHT = 3


def detect_language(text: str) -> str:
    """Very small heuristic: Cyrillic present → "ru", else "en"."""
    for ch in text:
        if "\u0400" <= ch <= "\u04ff":
            return "ru"
    return "en"


class RulesEngine:
    """Deterministic rule-based classifier.

    Usage::

        engine = RulesEngine(rules)
        match = engine.classify("Спасибо за донат!")
        match.category  # Category.DONATION
    """

    def __init__(self, rules: list[RuleSpec] | None = None) -> None:
        self._rules = [r for r in (rules or []) if r.enabled]

    @property
    def rules(self) -> list[RuleSpec]:
        return list(self._rules)

    def classify(self, text: str) -> RuleMatch:
        text = text or ""
        lowered = text.lower()
        language = detect_language(text)

        scored: list[tuple[float, int, int, RuleSpec, list[str]]] = []
        for index, rule in enumerate(self._rules):
            if rule.language and rule.language != "any" and rule.language != language:
                continue
            if self._is_excluded(lowered, rule):
                continue
            score, terms = self._score(lowered, rule)
            if score <= 0:
                continue
            scored.append((score, rule.priority, -index, rule, terms))

        if not scored:
            return self._neutral()

        # Manual overrides win regardless of score; otherwise highest score,
        # then highest priority, then definition order (deterministic).
        overrides = [s for s in scored if s[3].manual_override]
        pool = overrides or scored
        pool.sort(key=lambda s: (s[0], s[1], s[2]), reverse=True)
        score, _priority, _order, rule, terms = pool[0]

        confidence = self._confidence(score)
        if confidence < rule.min_confidence:
            return self._neutral()

        allowed, preferred = self._reaction_policy(rule)
        return RuleMatch(
            category=rule.category,
            confidence=round(confidence, 4),
            source="manual" if rule.manual_override else "rules",
            rule_id=rule.id,
            matched_terms=terms[:20],
            allowed_reactions=allowed,
            preferred_reactions=preferred,
            forbidden_reactions=list(rule.forbidden_reactions),
        )

    # --- internals -----------------------------------------------------------
    @staticmethod
    def _is_excluded(lowered: str, rule: RuleSpec) -> bool:
        return any(excl.lower() in lowered for excl in rule.exclusions if excl)

    @staticmethod
    def _score(lowered: str, rule: RuleSpec) -> tuple[float, list[str]]:
        score = 0.0
        terms: list[str] = []
        for kw in rule.keywords:
            token = kw.lower().strip()
            if token and token in lowered:
                score += _KEYWORD_WEIGHT
                terms.append(token)
        for phrase in rule.phrases:
            token = phrase.lower().strip()
            if token and token in lowered:
                score += _PHRASE_WEIGHT
                terms.append(token)
        for pattern in rule.regexes:
            if not pattern:
                continue
            try:
                if re.search(pattern, lowered):
                    score += _REGEX_WEIGHT
                    terms.append(pattern)
            except re.error:
                # A broken regex never crashes classification; it just scores 0.
                continue
        return score, terms

    @staticmethod
    def _confidence(score: float) -> float:
        # Monotonic, bounded, deterministic: score 1 → 0.57, 3 → 0.84, 6 → ~0.97.
        return min(0.99, score / (score + 1.5) + 0.17)

    @staticmethod
    def _reaction_policy(rule: RuleSpec) -> tuple[list[str], list[str]]:
        default_allowed, default_preferred = DEFAULT_CATEGORY_REACTIONS[rule.category]
        allowed = rule.allowed_reactions or list(default_allowed)
        preferred = rule.preferred_reactions or list(default_preferred)
        forbidden = set(rule.forbidden_reactions)
        allowed = [e for e in allowed if e not in forbidden]
        preferred = [e for e in preferred if e not in forbidden and e in allowed]
        return allowed, preferred

    @staticmethod
    def _neutral() -> RuleMatch:
        allowed, preferred = DEFAULT_CATEGORY_REACTIONS[Category.NEUTRAL]
        return RuleMatch(
            category=Category.NEUTRAL,
            confidence=0.0,
            source="default",
            allowed_reactions=list(allowed),
            preferred_reactions=list(preferred),
            forbidden_reactions=[],
        )


__all__ = [
    "CATEGORY_TITLES",
    "DEFAULT_CATEGORY_REACTIONS",
    "Category",
    "RuleMatch",
    "RuleSpec",
    "RulesEngine",
    "TextClassifier",
    "detect_language",
]
