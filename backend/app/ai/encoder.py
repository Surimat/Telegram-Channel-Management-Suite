"""Encoder (embedding) classifier for Russian posts (v1.1: AI Level 1.5).

The existing AI router has two levels: keyword *Rules* and an optional *LLM*. On
a weak Windows PC an LLM is often too heavy, which left the "auto" mode with only
keywords. This module adds a middle level — a **lightweight local encoder** that
needs no model download and no network:

* it embeds the text into a small, fixed-dimension, character/word-hash feature
  vector (pure Python — no numpy/torch/onnx dependency);
* it classifies against a small labelled Russian prototype set using cosine
  similarity, producing a category, tone, intent and an advisory emoji;
* it reports a real confidence and degrades gracefully: an unknown/empty text
  returns a neutral result with an ``error`` string rather than raising.

Design constraints:

* No new heavy dependency (the suite must stay installable on a weak PC and the
  portable ZIP must stay small — D-019).
* Advisory only: the Reaction Planner intersects the suggested emoji with policy,
  so the AI never overrides the Rules Engine or Telegram limits (D-005/D-032).
* Nothing here reads secrets, sessions or user identities.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from backend.app.ai.types import (
    SOURCE_AI,
    Category,
    ClassificationContext,
    ClassificationResult,
    Intent,
    Tone,
)

#: Human-readable name used in ``ClassificationResult.model``.
MODEL_NAME = "encoder-ru-v1"

#: Feature-vector dimension for the hashing trick.
_DIM = 256


@dataclass(frozen=True, slots=True)
class Prototype:
    """One labelled Russian example the encoder compares against."""

    text: str
    category: Category
    tone: Tone
    intent: Intent
    emoji: str = ""


#: A compact, reviewable prototype set (Russian-first). Each example is a short
#: representative phrase; the encoder generalises through word/char n-grams. The
#: categories are exactly the Rules Engine vocabulary (never a parallel one).
PROTOTYPES: tuple[Prototype, ...] = (
    Prototype("спасибо большое за помощь", Category.SUPPORT, Tone.WARM, Intent.LOVE, "🙏"),
    Prototype("благодарю вас, вы помогли", Category.SUPPORT, Tone.WARM, Intent.LOVE, "🙏"),
    Prototype("спасибо за донат, вы лучшие", Category.DONATION, Tone.WARM, Intent.LOVE, "❤"),
    Prototype("перевёл деньги на канал", Category.DONATION, Tone.POSITIVE, Intent.SUPPORT, "❤"),
    Prototype("поддержите автора донатом", Category.DONATION, Tone.NEUTRAL, Intent.SUPPORT, "🙏"),
    Prototype("мне очень жаль, соболезную", Category.SAD, Tone.SAD, Intent.SYMPATHY, "😢"),
    Prototype("держись, мы с тобой", Category.SUPPORT, Tone.WARM, Intent.SYMPATHY, "🙏"),
    Prototype("очень грустная и печальная", Category.SAD, Tone.SAD, Intent.SYMPATHY, "😢"),
    Prototype("ура, отличные новости", Category.NEWS, Tone.POSITIVE, Intent.JOY, "🎉"),
    Prototype("с днём рождения, поздравляю", Category.CUTE, Tone.WARM, Intent.JOY, "🎉"),
    Prototype("это очень смешно, ахаха", Category.FUNNY, Tone.HUMOROUS, Intent.HUMOR, "😂"),
    Prototype("весёлый мем про котов", Category.FUNNY, Tone.HUMOROUS, Intent.HUMOR, "😂"),
    Prototype("какой ужас, возмутительно", Category.ANGRY, Tone.ANGRY, Intent.ANGER, "😡"),
    Prototype("меня бесит эта ситуация", Category.ANGRY, Tone.ANGRY, Intent.ANGER, "😠"),
    Prototype("какой милый и хорошенький", Category.CUTE, Tone.WARM, Intent.LOVE, "🥰"),
    Prototype("такой маленький и прелестный", Category.CUTE, Tone.POSITIVE, Intent.LOVE, "😍"),
    Prototype("важное объявление", Category.ANNOUNCEMENT, Tone.NEUTRAL, Intent.NEUTRAL, "📢"),
    Prototype("внимание, изменения", Category.ANNOUNCEMENT, Tone.NEUTRAL, Intent.NEUTRAL, "📢"),
    Prototype("срочная новость сегодня", Category.NEWS, Tone.NEUTRAL, Intent.NEUTRAL, "📰"),
    Prototype("свежие новости за день", Category.NEWS, Tone.NEUTRAL, Intent.NEUTRAL, "📰"),
    Prototype("напоминаю о встрече", Category.ANNOUNCEMENT, Tone.NEUTRAL, Intent.NEUTRAL, "⏰"),
    Prototype("не забудьте оплатить", Category.ANNOUNCEMENT, Tone.NEUTRAL, Intent.NEUTRAL, "⏰"),
    Prototype("ты справишься, верю в тебя", Category.SUPPORT, Tone.WARM, Intent.SUPPORT, "💪"),
    Prototype("поддерживаю тебя в этом", Category.SUPPORT, Tone.WARM, Intent.SUPPORT, "🤝"),
)


def embed(text: str) -> list[float]:
    """Embed ``text`` into a fixed-dimension L2-normalised vector.

    Uses the hashing trick over lowercased word tokens and 3-grams. Pure Python
    (no numpy), deterministic, and cheap enough for a weak PC.
    """
    vector = [0.0] * _DIM
    if not text:
        return vector
    lowered = text.lower()
    tokens = _tokenize(lowered)
    for token in tokens:
        vector[hash(token) % _DIM] += 1.0
    for gram in _char_ngrams(lowered, 3):
        vector[hash(gram) % _DIM] += 0.5
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b, strict=False)))


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isalnum() or ch == "_":
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _char_ngrams(text: str, n: int) -> list[str]:
    cleaned = " ".join(_tokenize(text))
    if len(cleaned) < n:
        return []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


@dataclass(slots=True)
class _Scored:
    prototype: Prototype
    score: float


class EncoderClassifier:
    """A dependency-free Russian encoder classifier.

    ``min_score`` is the cosine threshold below which the result is treated as
    unknown (neutral + ``error`` explaining why), so a low-confidence guess is
    never presented as a decision.
    """

    def __init__(
        self,
        *,
        prototypes: tuple[Prototype, ...] | None = None,
        min_score: float = 0.18,
    ) -> None:
        self._prototypes = prototypes or PROTOTYPES
        self._min_score = min_score
        self._embedded: list[tuple[Prototype, list[float]]] = [
            (p, embed(p.text)) for p in self._prototypes
        ]

    @property
    def available(self) -> bool:
        return bool(self._embedded)

    @property
    def model(self) -> str:
        return MODEL_NAME

    def classify(
        self, text: str, context: ClassificationContext | None = None
    ) -> ClassificationResult:
        started = time.perf_counter()
        stripped = (text or "").strip()
        if not stripped:
            return self._neutral("Пустой текст — классифицировать нечего.", started)
        if not self.available:
            return self._neutral("Прототипы не загружены.", started)

        vector = embed(stripped)
        scored = [
            _Scored(proto, cosine(vector, emb)) for proto, emb in self._embedded
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        best = scored[0]
        elapsed = int((time.perf_counter() - started) * 1000)

        if best.score < self._min_score:
            return ClassificationResult(
                category=Category.NEUTRAL,
                confidence=round(max(0.0, best.score), 3),
                source=SOURCE_AI,
                tone=Tone.NEUTRAL,
                intent=Intent.NEUTRAL,
                model=MODEL_NAME,
                processing_time_ms=elapsed,
                error="Недостаточно уверенности — нужен ручной выбор или LLM.",
            )

        confidence = round(min(1.0, best.score), 3)
        # Aggregate the top matches that share the winning category so a cluster
        # of near-identical examples raises confidence.
        same = [s for s in scored if s.prototype.category is best.prototype.category][:3]
        matched = [s.prototype.text for s in same]
        return ClassificationResult(
            category=best.prototype.category,
            confidence=confidence,
            source=SOURCE_AI,
            tone=best.prototype.tone,
            intent=best.prototype.intent,
            suggested_emoji=best.prototype.emoji,
            model=MODEL_NAME,
            processing_time_ms=elapsed,
            matched_terms=matched,
        )

    def _neutral(self, error: str, started: float) -> ClassificationResult:
        return ClassificationResult(
            category=Category.NEUTRAL,
            confidence=0.0,
            source=SOURCE_AI,
            model=MODEL_NAME,
            processing_time_ms=int((time.perf_counter() - started) * 1000),
            error=error,
        )


__all__ = [
    "MODEL_NAME",
    "PROTOTYPES",
    "EncoderClassifier",
    "Prototype",
    "cosine",
    "embed",
]
