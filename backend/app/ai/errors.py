"""Friendly AI errors (PHASE 7).

Every error carries a plain-language ``message`` and ``how_to_fix`` hint so the
UI/log center can explain what happened without exposing internal detail. These
are never raised into the reaction pipeline: the AI layer converts them into a
fallback classification and records an event instead.
"""

from __future__ import annotations


class AiError(Exception):
    """Base class for AI-layer errors."""

    code = "ai_error"

    def __init__(self, message: str, *, how_to_fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix


class AiDisabledError(AiError):
    """AI is turned off in settings."""

    code = "ai_disabled"

    def __init__(self) -> None:
        super().__init__(
            "Мини-ИИ выключен.",
            how_to_fix="Включите ИИ в разделе «AI», если хотите использовать модель.",
        )


class ModelNotConfiguredError(AiError):
    """No model path is set."""

    code = "model_not_configured"

    def __init__(self) -> None:
        super().__init__(
            "Путь к модели ИИ не указан.",
            how_to_fix="Укажите путь к файлу модели .gguf в разделе «AI».",
        )


class ModelNotFoundError(AiError):
    """The configured model file does not exist or is not readable."""

    code = "model_not_found"

    def __init__(self, path: str) -> None:
        super().__init__(
            "Файл модели ИИ не найден.",
            how_to_fix=f"Проверьте путь к модели: {path}",
        )


class RuntimeUnavailableError(AiError):
    """The llama.cpp runtime is not installed in this environment."""

    code = "runtime_unavailable"

    def __init__(self) -> None:
        super().__init__(
            "Локальный движок ИИ (llama.cpp) недоступен.",
            how_to_fix=(
                "Установите пакет llama-cpp-python или выключите ИИ — "
                "система продолжит работать на обычных правилах."
            ),
        )


class InferenceTimeoutError(AiError):
    """The model did not answer within the configured timeout."""

    code = "inference_timeout"

    def __init__(self) -> None:
        super().__init__(
            "Модель не успела ответить за отведённое время.",
            how_to_fix=(
                "Увеличьте «Максимальное время анализа» в разделе «AI» или "
                "выберите модель поменьше."
            ),
        )


class InvalidModelOutputError(AiError):
    """The model returned something that is not valid classification JSON."""

    code = "invalid_output"

    def __init__(self) -> None:
        super().__init__(
            "Модель вернула некорректный результат.",
            how_to_fix="Будет использована классификация по правилам. Попробуйте другую модель.",
        )


class ModelLoadError(AiError):
    """The model could not be loaded into memory."""

    code = "model_load_failed"

    def __init__(self, detail: str = "") -> None:
        message = "Не удалось загрузить модель ИИ в память."
        super().__init__(
            message,
            how_to_fix=(
                "Проверьте, что это совместимый файл .gguf и что хватает "
                "оперативной памяти. Система продолжит работать на правилах."
            ),
        )
        self.detail = detail


__all__ = [
    "AiDisabledError",
    "AiError",
    "InferenceTimeoutError",
    "InvalidModelOutputError",
    "ModelLoadError",
    "ModelNotConfiguredError",
    "ModelNotFoundError",
    "RuntimeUnavailableError",
]
