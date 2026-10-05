"""Rules-first routing between the Rules Engine and the optional AI (PHASE 7).

The Router is the single place that encodes the classification policy:

```
text
  → Rules Engine
      → confidence >= rules_threshold → accept rules
  → else, if lightweight encoder available → local encoder (v1.1)
      → confidence >= ai_threshold → accept encoder
  → else, if AI available → tiny LLM (strict JSON)
      → confidence >= ai_threshold → accept AI
  → else → fallback to the rules/default result
```

Any AI/encoder failure (disabled, missing model, timeout, bad JSON) degrades to
the rules result — the Reaction Manager is never blocked (D-032).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.ai.errors import AiError
from backend.app.ai.types import (
    MODE_AI,
    MODE_AUTO,
    MODE_ENCODER,
    MODE_RULES,
    SOURCE_AI,
    SOURCE_FALLBACK,
    SOURCE_MANUAL,
    SOURCE_RULES,
    ClassificationContext,
    ClassificationResult,
    Classifier,
)
from backend.app.core.logging import get_logger
from backend.app.rules.engine import CATEGORY_TITLES, Category

logger = get_logger(__name__)


@dataclass(slots=True)
class RoutingOutcome:
    """Full, explainable outcome of one routing decision."""

    result: ClassificationResult
    mode: str
    rules_result: ClassificationResult | None = None
    ai_attempted: bool = False
    ai_used: bool = False
    ai_error: str = ""
    fallback_used: bool = False
    encoder_attempted: bool = False
    encoder_used: bool = False

    @property
    def source(self) -> str:
        return self.result.source


def _neutral_fallback() -> ClassificationResult:
    return ClassificationResult(
        category=Category.NEUTRAL,
        confidence=0.0,
        source=SOURCE_FALLBACK,
        model="fallback",
    )


class RoutingClassifier:
    """Compose a rules classifier, an optional encoder and an optional AI."""

    def __init__(
        self,
        *,
        rules: Classifier,
        ai: Classifier | None,
        rules_threshold: float,
        ai_threshold: float,
        mode: str = MODE_AUTO,
        encoder: Classifier | None = None,
    ) -> None:
        self.rules = rules
        self.ai = ai
        self.encoder = encoder
        self.rules_threshold = rules_threshold
        self.ai_threshold = ai_threshold
        self.mode = mode

    def route(
        self, text: str, context: ClassificationContext | None = None
    ) -> RoutingOutcome:
        context = context or ClassificationContext(
            known_categories=tuple(c.value for c in Category)
        )
        if not context.known_categories:
            context.known_categories = tuple(c.value for c in Category)

        if self.mode == MODE_RULES:
            rules_result = self._safe_rules(text, context)
            return RoutingOutcome(result=_finalize(rules_result), mode=self.mode,
                                  rules_result=rules_result)

        if self.mode == MODE_ENCODER:
            return self._route_encoder_only(text, context)

        if self.mode == MODE_AI:
            return self._route_ai_only(text, context)

        return self._route_auto(text, context)

    # --- modes ---------------------------------------------------------------
    def _route_auto(self, text: str, context: ClassificationContext) -> RoutingOutcome:
        rules_result = self._safe_rules(text, context)
        if rules_result.confidence >= self.rules_threshold:
            return RoutingOutcome(
                result=_finalize(rules_result),
                mode=self.mode,
                rules_result=rules_result,
            )
        # Level 1.5: the lightweight encoder (no model, weak-PC friendly).
        encoder_result, encoder_error = self._try_encoder(text, context)
        if encoder_result is not None and encoder_result.confidence >= self.ai_threshold:
            return RoutingOutcome(
                result=encoder_result,
                mode=self.mode,
                rules_result=rules_result,
                encoder_attempted=True,
                encoder_used=True,
            )
        if self.ai is None:
            return RoutingOutcome(
                result=_finalize(rules_result),
                mode=self.mode,
                rules_result=rules_result,
                encoder_attempted=encoder_result is not None,
                encoder_used=False,
                ai_error=encoder_error,
                fallback_used=rules_result.confidence < self.rules_threshold,
            )
        ai_result, ai_error = self._try_ai(text, context)
        if ai_result is not None and ai_result.confidence >= self.ai_threshold:
            return RoutingOutcome(
                result=ai_result,
                mode=self.mode,
                rules_result=rules_result,
                encoder_attempted=encoder_result is not None,
                ai_attempted=True,
                ai_used=True,
            )
        # AI unavailable, wrong or unsure → keep the rules result.
        return RoutingOutcome(
            result=_finalize(rules_result),
            mode=self.mode,
            rules_result=rules_result,
            encoder_attempted=encoder_result is not None,
            ai_attempted=True,
            ai_error=ai_error or ("AI ниже порога уверенности" if ai_result else ""),
            fallback_used=True,
        )

    def _route_encoder_only(
        self, text: str, context: ClassificationContext
    ) -> RoutingOutcome:
        encoder_result, encoder_error = self._try_encoder(text, context)
        if encoder_result is not None and encoder_result.confidence >= self.ai_threshold:
            return RoutingOutcome(
                result=encoder_result,
                mode=self.mode,
                encoder_attempted=True,
                encoder_used=True,
                ai_error=encoder_error,
            )
        rules_result = self._safe_rules(text, context)
        rules_result.source = SOURCE_FALLBACK
        return RoutingOutcome(
            result=rules_result,
            mode=self.mode,
            rules_result=rules_result,
            encoder_attempted=True,
            ai_error=encoder_error or "Уверенность распознавателя ниже порога",
            fallback_used=True,
        )

    def _route_ai_only(self, text: str, context: ClassificationContext) -> RoutingOutcome:
        ai_result, ai_error = self._try_ai(text, context)
        if ai_result is not None:
            return RoutingOutcome(
                result=ai_result,
                mode=self.mode,
                ai_attempted=True,
                ai_used=True,
            )
        rules_result = self._safe_rules(text, context)
        rules_result.source = SOURCE_FALLBACK
        return RoutingOutcome(
            result=rules_result,
            mode=self.mode,
            rules_result=rules_result,
            ai_attempted=True,
            ai_error=ai_error,
            fallback_used=True,
        )

    # --- helpers -------------------------------------------------------------
    def _safe_rules(
        self, text: str, context: ClassificationContext
    ) -> ClassificationResult:
        try:
            return self.rules.classify(text, context)
        except Exception:  # pragma: no cover - rules must never crash routing
            logger.exception("Rules classification failed")
            return _neutral_fallback()

    def _try_encoder(
        self, text: str, context: ClassificationContext
    ) -> tuple[ClassificationResult | None, str]:
        if self.encoder is None:
            return None, ""
        try:
            result = self.encoder.classify(text, context)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Encoder classification crashed: %s", type(exc).__name__)
            return None, "Ошибка лёгкого распознавателя"
        if result.error:
            return None, result.error
        return result, ""

    def _try_ai(
        self, text: str, context: ClassificationContext
    ) -> tuple[ClassificationResult | None, str]:
        if self.ai is None:
            return None, "AI выключен"
        try:
            return self.ai.classify(text, context), ""
        except AiError as exc:
            logger.warning("AI classification failed: %s", exc.code)
            return None, exc.message
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("AI classification crashed: %s", type(exc).__name__)
            return None, "Внутренняя ошибка ИИ"


def _finalize(result: ClassificationResult) -> ClassificationResult:
    """Normalize a result's source to the public vocabulary."""
    if result.source in (SOURCE_RULES, SOURCE_MANUAL, SOURCE_AI):
        return result
    if result.confidence <= 0.0:
        result.source = SOURCE_FALLBACK
    else:
        result.source = SOURCE_RULES
    return result


def category_title(category: Category | str) -> str:
    """Human title for a category id."""
    try:
        cat = category if isinstance(category, Category) else Category(str(category))
    except ValueError:
        return str(category)
    return CATEGORY_TITLES.get(cat, str(cat))


__all__ = ["RoutingClassifier", "RoutingOutcome", "category_title"]
