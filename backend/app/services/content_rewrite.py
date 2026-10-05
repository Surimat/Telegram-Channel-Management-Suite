"""Content rewrite via the existing generative LLM backend (v1.2).

Only a *generative* local model can rewrite text. The lightweight ruBERT
encoder is an embedding model and is deliberately **not** used here (D-068):
if no generative backend is available the rewrite honestly reports
"Рерайт недоступен" and the pipeline continues with the original text.

Modes (mirrors the product brief):

* ``none`` — no rewrite
* ``fix`` — fix spelling/punctuation
* ``shorten`` — shorten
* ``rephrase`` — rephrase
* ``adapt`` — adapt to the target channel's style

Resource strategy: lazy, CPU-only, single inference, unloaded when unused — the
same guarantees the classifier honours (D-035).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from backend.app.ai.backends import build_backend
from backend.app.ai.errors import AiError
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

MODE_NONE = "none"
MODE_FIX = "fix"
MODE_SHORTEN = "shorten"
MODE_REPHRASE = "rephrase"
MODE_ADAPT = "adapt"

VALID_REWRITE_MODES = frozenset({MODE_NONE, MODE_FIX, MODE_SHORTEN, MODE_REPHRASE, MODE_ADAPT})

MODE_TITLES = {
    MODE_NONE: "Без рерайта",
    MODE_FIX: "Исправить ошибки",
    MODE_SHORTEN: "Сократить",
    MODE_REPHRASE: "Переформулировать",
    MODE_ADAPT: "Адаптировать под канал",
}

UNAVAILABLE_MESSAGE = (
    "Рерайт недоступен. Установите локальную generative model."
)

_SYSTEM_PROMPTS = {
    MODE_FIX: "Исправь орфографию и пунктуацию. Сохрани смысл и язык текста.",
    MODE_SHORTEN: "Сократи текст, сохранив главный смысл. Не добавляй ничего нового.",
    MODE_REPHRASE: "Переформулируй текст другими словами, сохранив смысл.",
    MODE_ADAPT: "Адаптируй текст под стиль Telegram-канала: живо и понятно.",
}


@dataclass(slots=True)
class RewriteResult:
    ok: bool
    text: str
    mode: str
    message: str = ""
    how_to_fix: str = ""
    used_model: str = ""


class ContentRewriteService:
    """Rewrite content through the configured generative backend."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def status(self) -> tuple[bool, str, str]:
        """Return ``(available, message, how_to_fix)`` for the rewrite feature."""
        try:
            backend = build_backend(self.settings)
        except AiError as exc:
            return False, exc.message, exc.how_to_fix
        if not backend.available:
            return (
                False,
                UNAVAILABLE_MESSAGE,
                "Установите llama-cpp-python и укажите модель .gguf в разделе «Мини-ИИ».",
            )
        return True, "", ""

    def rewrite(self, text: str, *, mode: str = MODE_REPHRASE) -> RewriteResult:
        """Rewrite ``text`` in ``mode``; never raises (returns ``ok=False``)."""
        if mode == MODE_NONE or not (text or "").strip():
            return RewriteResult(ok=True, text=text, mode=MODE_NONE)
        if mode not in VALID_REWRITE_MODES:
            return RewriteResult(
                ok=False,
                text=text,
                mode=mode,
                message="Неизвестный режим рерайта.",
                how_to_fix="Выберите один из доступных режимов.",
            )
        try:
            backend = build_backend(self.settings)
        except AiError as exc:
            return RewriteResult(
                ok=False, text=text, mode=mode, message=exc.message, how_to_fix=exc.how_to_fix
            )
        if not backend.available:
            return RewriteResult(
                ok=False,
                text=text,
                mode=mode,
                message=UNAVAILABLE_MESSAGE,
                how_to_fix=(
                    "Установите llama-cpp-python и укажите модель .gguf "
                    "в разделе «Мини-ИИ»."
                ),
            )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPTS[mode]},
            {"role": "user", "content": text},
        ]
        try:
            raw = backend.complete(messages, max_tokens=max(256, len(text) // 2))
        except AiError as exc:
            logger.info("Rewrite failed: %s", exc.code)
            return RewriteResult(
                ok=False, text=text, mode=mode, message=exc.message, how_to_fix=exc.how_to_fix
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Rewrite crashed: %s", type(exc).__name__)
            return RewriteResult(
                ok=False, text=text, mode=mode, message="Не удалось выполнить рерайт."
            )
        finally:
            if not self.settings.ai_keep_loaded:
                with contextlib.suppress(Exception):
                    backend.unload()
        result_text = (raw or "").strip() or text
        return RewriteResult(
            ok=True,
            text=result_text,
            mode=mode,
            used_model=getattr(backend, "name", ""),
        )


__all__ = [
    "MODE_ADAPT",
    "MODE_FIX",
    "MODE_NONE",
    "MODE_REPHRASE",
    "MODE_SHORTEN",
    "MODE_TITLES",
    "UNAVAILABLE_MESSAGE",
    "VALID_REWRITE_MODES",
    "ContentRewriteService",
    "RewriteResult",
]
