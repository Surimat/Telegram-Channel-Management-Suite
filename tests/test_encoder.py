"""v1.1 lightweight encoder classifier tests (pure Python, no model, no network).

The encoder is the AI "Level 1.5" between deterministic rules and the optional
LLM. Tests assert it is advisory, deterministic and degrades gracefully.
"""

from __future__ import annotations

from backend.app.ai.encoder import MODEL_NAME, EncoderClassifier, cosine, embed
from backend.app.ai.types import SOURCE_AI, Category, ClassificationContext, Intent
from backend.app.rules.engine import Category as RulesCategory


def test_embed_is_normalised_and_deterministic() -> None:
    v1 = embed("спасибо большое за помощь")
    v2 = embed("спасибо большое за помощь")
    assert v1 == v2
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6
    assert abs(cosine(v1, v2) - 1.0) < 1e-9


def test_empty_text_is_neutral_with_error() -> None:
    result = EncoderClassifier().classify("")
    assert result.category is Category.NEUTRAL
    assert result.confidence == 0.0
    assert result.error
    assert result.source == SOURCE_AI


def test_unknown_text_below_threshold_is_neutral() -> None:
    # With an explicit confidence floor, an unrelated string is reported as
    # neutral with an error instead of being forced into a category.
    result = EncoderClassifier(min_score=0.5).classify("qwerty zxcvbn asdfgh")
    assert result.category is Category.NEUTRAL
    assert result.error
    assert result.confidence < 0.5


def test_gratitude_classifies_as_support() -> None:
    result = EncoderClassifier().classify("спасибо большое за помощь")
    assert result.category is Category.SUPPORT
    assert result.confidence > 0.3
    assert result.intent is Intent.LOVE
    assert result.model == MODEL_NAME
    assert result.matched_terms


def test_humor_classifies_as_funny() -> None:
    result = EncoderClassifier().classify("это очень смешно, ахаха")
    assert result.category is Category.FUNNY
    assert result.intent is Intent.HUMOR


def test_anger_classifies_as_angry() -> None:
    result = EncoderClassifier().classify("какой ужас, возмутительно")
    assert result.category is Category.ANGRY
    assert result.intent is Intent.ANGER


def test_sadness_classifies_as_sad() -> None:
    result = EncoderClassifier().classify("очень грустная и печальная новость")
    assert result.category is Category.SAD


def test_suggested_emoji_is_advisory_not_authoritative() -> None:
    result = EncoderClassifier().classify("с днём рождения, поздравляю")
    # The encoder may suggest an emoji, but the category is what matters; the
    # reaction planner intersects the emoji with policy afterwards.
    assert result.category in {Category.CUTE, Category.NEWS}
    assert isinstance(result.suggested_emoji, str)


def test_categories_match_rules_engine_vocabulary() -> None:
    # The encoder must not invent a parallel category vocabulary.
    for proto in EncoderClassifier()._prototypes:
        assert isinstance(proto.category, RulesCategory)


def test_context_is_accepted_and_ignored_safely() -> None:
    context = ClassificationContext(known_categories=("support",))
    result = EncoderClassifier().classify("спасибо за помощь", context)
    assert result.category is Category.SUPPORT
