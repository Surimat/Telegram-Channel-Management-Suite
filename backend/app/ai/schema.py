"""Strict validation of the AI's JSON contract (PHASE 7).

The model is told to return exactly ``{"category", "tone", "confidence"}``. We do
not trust it: any invalid JSON, unknown category/tone, out-of-range or non-numeric
confidence is rejected and turned into an :class:`InvalidModelOutputError`, which
the caller converts into a fallback classification.

The parser is deliberately tolerant about *framing* (models love markdown fences
and stray prose) but strict about the *values*.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from backend.app.ai.errors import InvalidModelOutputError
from backend.app.ai.types import ALLOWED_CATEGORIES, ALLOWED_TONES, Tone
from backend.app.rules.engine import Category

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)


@dataclass(slots=True)
class ValidatedClassification:
    category: Category
    tone: Tone
    confidence: float


def _extract_json(raw: str) -> dict[str, object]:
    if not raw or not raw.strip():
        raise InvalidModelOutputError()
    text = _FENCE_RE.sub("", raw).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if match is None:
            raise InvalidModelOutputError() from None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise InvalidModelOutputError() from None
    if not isinstance(parsed, dict):
        raise InvalidModelOutputError()
    return parsed


def parse_classification(raw: str) -> ValidatedClassification:
    """Parse and strictly validate a model response.

    Raises :class:`InvalidModelOutputError` on anything that is not a valid,
    in-vocabulary category/tone with a numeric confidence in ``[0, 1]``.
    """
    data = _extract_json(raw)

    category_raw = data.get("category")
    if not isinstance(category_raw, str):
        raise InvalidModelOutputError()
    category_str = category_raw.strip().lower()
    if category_str not in ALLOWED_CATEGORIES:
        raise InvalidModelOutputError()

    tone_raw = data.get("tone", Tone.NEUTRAL.value)
    if not isinstance(tone_raw, str):
        raise InvalidModelOutputError()
    tone_str = tone_raw.strip().lower()
    if tone_str not in ALLOWED_TONES:
        raise InvalidModelOutputError()

    confidence_raw = data.get("confidence")
    if isinstance(confidence_raw, bool) or not isinstance(confidence_raw, (int, float, str)):
        raise InvalidModelOutputError()
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        raise InvalidModelOutputError() from None
    if confidence != confidence or confidence in (float("inf"), float("-inf")):
        raise InvalidModelOutputError()
    if not (0.0 <= confidence <= 1.0):
        raise InvalidModelOutputError()

    return ValidatedClassification(
        category=Category(category_str),
        tone=Tone(tone_str),
        confidence=round(confidence, 4),
    )


__all__ = ["ValidatedClassification", "parse_classification"]
