"""PHASE 7 unit tests: schema, classifiers, routing and inference bounds.

These exercise the AI layer with the deterministic fake backend only — no model,
no network (D-001).
"""

from __future__ import annotations

import pytest

from backend.app.ai.backends import FakeLlmBackend
from backend.app.ai.classifiers import FakeClassifier, LlmClassifier, RulesClassifier
from backend.app.ai.errors import InvalidModelOutputError, RuntimeUnavailableError
from backend.app.ai.inference import run_bounded
from backend.app.ai.router import RoutingClassifier, category_title
from backend.app.ai.schema import parse_classification
from backend.app.ai.types import (
    MODE_AI,
    MODE_AUTO,
    MODE_RULES,
    SOURCE_AI,
    SOURCE_FALLBACK,
    SOURCE_RULES,
    ClassificationResult,
)
from backend.app.rules.defaults import default_rule_specs
from backend.app.rules.engine import Category


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
def test_schema_accepts_plain_json() -> None:
    out = parse_classification('{"category": "donation", "tone": "warm", "confidence": 0.94}')
    assert out.category is Category.DONATION
    assert out.confidence == 0.94
    assert str(out.tone) == "warm"


def test_schema_accepts_fenced_json_with_prose() -> None:
    raw = 'Sure!\n```json\n{"category":"news","tone":"neutral","confidence":0.5}\n```'
    assert parse_classification(raw).category is Category.NEWS


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json at all",
        '{"category": "unknown", "tone": "neutral", "confidence": 0.5}',
        '{"category": "news", "tone": "confused", "confidence": 0.5}',
        '{"category": "news", "tone": "neutral"}',
        '{"category": "news", "tone": "neutral", "confidence": 1.5}',
        '{"category": "news", "tone": "neutral", "confidence": "high"}',
        '{"category": "news", "tone": "neutral", "confidence": true}',
    ],
)
def test_schema_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidModelOutputError):
        parse_classification(raw)


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------
def test_rules_classifier_donation() -> None:
    result = RulesClassifier(default_rule_specs()).classify("Спасибо за донат, друзья!")
    assert result.category is Category.DONATION
    assert result.source == SOURCE_RULES
    assert result.confidence > 0.5


def test_rules_classifier_default_is_fallback() -> None:
    result = RulesClassifier(default_rule_specs()).classify("ааааа непонятный текст")
    assert result.category is Category.NEUTRAL
    assert result.source == "default"


def test_llm_classifier_valid_output() -> None:
    backend = FakeLlmBackend(response='{"category":"funny","tone":"humorous","confidence":0.8}')
    result = LlmClassifier(backend).classify("шутка")
    assert result.category is Category.FUNNY
    assert result.source == SOURCE_AI
    assert result.confidence == 0.8


def test_llm_classifier_invalid_output_raises() -> None:
    backend = FakeLlmBackend(response="I cannot help with that")
    with pytest.raises(InvalidModelOutputError):
        LlmClassifier(backend).classify("текст")


def test_llm_classifier_timeout_is_reported() -> None:
    from backend.app.ai.errors import InferenceTimeoutError

    def _boom(_fn, _timeout):
        raise InferenceTimeoutError()

    backend = FakeLlmBackend(response='{"category":"news","tone":"neutral","confidence":0.9}')
    with pytest.raises(InferenceTimeoutError):
        LlmClassifier(backend, run=_boom).classify("текст")


def test_fake_backend_ignores_prompt_metadata() -> None:
    """A prompt-injection attempt in the header must not steer the classifer."""
    backend = FakeLlmBackend()
    # The trusted header always mentions every category name; the fake must only
    # read the delimited data block, so a truly neutral body stays neutral.
    result = LlmClassifier(backend).classify("какой-то непонятный текст без ключевых слов")
    assert result.category is Category.NEUTRAL
    assert result.confidence == 0.4


# ---------------------------------------------------------------------------
# Routing policy
# ---------------------------------------------------------------------------
def _router(*, ai, rules_threshold=0.55, ai_threshold=0.6, mode=MODE_AUTO, encoder=None):
    return RoutingClassifier(
        rules=RulesClassifier(default_rule_specs()),
        ai=ai,
        encoder=encoder,
        rules_threshold=rules_threshold,
        ai_threshold=ai_threshold,
        mode=mode,
    )


def test_router_rules_fast_path_skips_ai() -> None:
    called = {"n": 0}

    def _handler(text, ctx):
        called["n"] += 1
        return ClassificationResult(Category.FUNNY, 0.9, SOURCE_AI)

    outcome = _router(ai=FakeClassifier(handler=_handler)).route("Спасибо за донат!")
    assert outcome.result.category is Category.DONATION
    assert outcome.result.source == SOURCE_RULES
    assert outcome.ai_attempted is False
    assert called["n"] == 0


def test_router_uses_ai_when_rules_unsure() -> None:
    ai = FakeClassifier(
        result=ClassificationResult(Category.SUPPORT, 0.9, SOURCE_AI, model="fake")
    )
    outcome = _router(ai=ai).route("непонятный текст без правил")
    assert outcome.ai_attempted is True
    assert outcome.ai_used is True
    assert outcome.result.source == SOURCE_AI
    assert outcome.result.category is Category.SUPPORT


def test_router_ai_below_threshold_keeps_rules_fallback() -> None:
    ai = FakeClassifier(result=ClassificationResult(Category.SUPPORT, 0.2, SOURCE_AI))
    outcome = _router(ai=ai).route("непонятный текст без правил")
    assert outcome.ai_used is False
    assert outcome.fallback_used is True
    assert outcome.result.source == SOURCE_FALLBACK


def test_router_ai_error_falls_back_gracefully() -> None:
    from backend.app.ai.errors import AiError

    def _handler(text, ctx):
        raise AiError("model broke")

    outcome = _router(ai=FakeClassifier(handler=_handler)).route("непонятный текст без правил")
    assert outcome.ai_attempted is True
    assert outcome.ai_used is False
    assert outcome.result.source == SOURCE_FALLBACK
    assert outcome.ai_error


def test_router_mode_rules_never_calls_ai() -> None:
    ai = FakeClassifier(result=ClassificationResult(Category.SUPPORT, 1.0, SOURCE_AI))
    outcome = _router(ai=ai, mode=MODE_RULES).route("непонятный текст без правил")
    assert outcome.ai_attempted is False
    assert outcome.result.source != SOURCE_AI


def test_router_mode_ai_only_falls_back_when_unavailable() -> None:
    outcome = _router(ai=None, mode=MODE_AI).route("Спасибо за донат!")
    assert outcome.ai_attempted is True
    assert outcome.fallback_used is True
    assert outcome.result.source == SOURCE_FALLBACK


def test_router_uses_encoder_between_rules_and_ai() -> None:
    from backend.app.ai.encoder import EncoderClassifier
    from backend.app.ai.types import MODE_ENCODER

    # Text with no rule keywords, but a strong encoder match.
    outcome = _router(
        ai=None, encoder=EncoderClassifier(), mode=MODE_ENCODER
    ).route("это очень смешно, ахаха")
    assert outcome.encoder_attempted is True
    assert outcome.encoder_used is True
    assert outcome.result.category is Category.FUNNY
    assert outcome.ai_attempted is False


def test_router_encoder_only_falls_back_below_threshold() -> None:
    from backend.app.ai.encoder import EncoderClassifier
    from backend.app.ai.types import MODE_ENCODER

    outcome = _router(
        ai=None, encoder=EncoderClassifier(), mode=MODE_ENCODER
    ).route("совершенно непонятный текст без категории")
    assert outcome.encoder_attempted is True
    assert outcome.encoder_used is False
    assert outcome.fallback_used is True
    assert outcome.ai_error


def test_router_auto_prefers_encoder_over_llm_when_confident() -> None:
    from backend.app.ai.encoder import EncoderClassifier

    called = {"n": 0}

    def _handler(text, ctx):
        called["n"] += 1
        return ClassificationResult(Category.SUPPORT, 0.9, SOURCE_AI)

    outcome = _router(
        ai=FakeClassifier(handler=_handler),
        encoder=EncoderClassifier(),
    ).route("важное объявление")
    assert outcome.encoder_used is True
    assert outcome.result.category is Category.ANNOUNCEMENT
    # The heavier LLM is never invoked when the light encoder is confident.
    assert called["n"] == 0


def test_router_encoder_failure_degrades_to_rules() -> None:
    from backend.app.ai.types import MODE_ENCODER

    class _Broken:
        model = "broken"

        def classify(self, text, context=None):
            raise RuntimeError("boom")

    outcome = _router(ai=None, encoder=_Broken(), mode=MODE_ENCODER).route("текст")
    assert outcome.encoder_used is False
    assert outcome.fallback_used is True
    assert outcome.result.source == SOURCE_FALLBACK


def test_category_title_human_readable() -> None:
    assert category_title("donation") == "Донат / поддержка"
    assert category_title(Category.NEWS) == "Новость"


# ---------------------------------------------------------------------------
# Inference bounds
# ---------------------------------------------------------------------------
def test_run_bounded_returns_value() -> None:
    assert run_bounded(lambda: 42, timeout=5) == 42


def test_run_bounded_times_out() -> None:
    import time

    from backend.app.ai.errors import InferenceTimeoutError

    def _slow() -> int:
        time.sleep(1.0)
        return 1

    with pytest.raises(InferenceTimeoutError):
        run_bounded(_slow, timeout=0.05)
    # Drain the still-running worker so it cannot leak into later tests.
    time.sleep(1.1)


def test_llama_backend_unavailable_is_safe() -> None:
    """Real backend reports unavailability without crashing the app."""
    from backend.app.ai.backends import LlamaCppBackend
    from backend.app.core.config import get_settings

    backend = LlamaCppBackend(get_settings())
    assert backend.loaded is False
    assert isinstance(backend.available, bool)
    if not backend.available:
        # No runtime installed: loading must raise a friendly AiError, not crash.
        with pytest.raises(RuntimeUnavailableError):
            backend.load()
