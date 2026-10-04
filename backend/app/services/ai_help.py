"""Plain-language AI help copy and formatting (PHASE 7, RU-first).

Keeping the "what it does / why / large-value effect / safe default" text here
means the Web UI never hardcodes explanations and stays consistent across the AI
page, setup wizard and dashboard.
"""

from __future__ import annotations

from backend.app.services.ai_service import AI_SETTING_SPECS

#: Per-setting explanation: (what_it_does, why, large_value_effect, safe_default)
_SETTING_HELP: dict[str, tuple[str, str, str, str]] = {
    "ai_enabled": (
        "Главный выключатель мини-ИИ.",
        "ИИ помогает определить категорию, когда обычные правила не уверены.",
        "Ничего — это переключатель.",
        "Выключено: система полностью работает на правилах.",
    ),
    "ai_backend": (
        "Какой локальный движок ИИ использовать.",
        "Позволяет выбрать реальный движок или упрощённый для проверки.",
        "Чем мощнее движок, тем больше ресурсов он требует.",
        "llama_cpp — реальный локальный движок.",
    ),
    "ai_model_path": (
        "Путь к файлу локальной модели .gguf.",
        "Без выбранной модели ИИ не используется — это безопасно.",
        "Чем больше модель, тем точнее, но тяжелее для слабого компьютера.",
        "Маленькая модель ~0.5–1B параметров.",
    ),
    "ai_model_threads": (
        "Сколько потоков процессора отдать ИИ.",
        "Больше потоков — быстрее анализ, но сильнее нагрузка на компьютер.",
        "Слишком большое значение перегружает слабый процессор.",
        "2 потока — безопасно для слабого ПК.",
    ),
    "ai_context_size": (
        "Размер контекста модели в токенах.",
        "Определяет, сколько текста модель может увидеть за раз.",
        "Большой контекст сильно увеличивает потребление памяти.",
        "2048 — достаточно для постов канала.",
    ),
    "ai_temperature": (
        "Насколько «творчески» отвечает модель.",
        "Для классификации нужен предсказуемый ответ, а не творчество.",
        "Высокая температура делает ответы менее стабильными.",
        "0.1 — почти детерминированный ответ.",
    ),
    "ai_max_tokens": (
        "Максимальная длина ответа модели.",
        "Ответ ИИ — это короткий JSON, длинных ответов не нужно.",
        "Слишком большое значение тратит время впустую.",
        "128 токенов.",
    ),
    "ai_timeout_seconds": (
        "Максимальное время одного анализа.",
        "Если модель не успела ответить за это время, система"
        " автоматически использует обычные правила.",
        "Слишком большое значение заставит ждать ответа очень долго.",
        "30 секунд для слабого компьютера.",
    ),
    "ai_keep_loaded": (
        "Держать модель в памяти между запросами.",
        "Ускоряет повторные анализы, но занимает оперативную память.",
        "При включении модель постоянно занимает память компьютера.",
        "Выключено — модель выгружается после анализа.",
    ),
    "ai_rules_threshold": (
        "Порог уверенности обычных правил.",
        "Если правила уверены сильнее этого порога, ИИ не вызывается вообще.",
        "Слишком высокий порог заставляет ИИ срабатывать чаще.",
        "0.55.",
    ),
    "ai_confidence_threshold": (
        "Порог уверенности ИИ.",
        "ИИ-ответ принимается, только если он уверен сильнее этого порога.",
        "Слишком высокий порог означает, что ИИ редко применяется.",
        "0.6.",
    ),
    "ai_history_limit": (
        "Сколько последних записей ИИ хранить.",
        "Нужно только для диагностики; большая история не требуется.",
        "Слишком большое значение увеличивает размер базы данных.",
        "200 записей.",
    ),
    "ai_encoder_enabled": (
        "Лёгкий распознаватель категорий без скачивания модели.",
        "Помогает, когда обычные правила не уверены, но тяжёлую модель"
        " ставить не хочется — особенно на слабом компьютере.",
        "Ничего: распознаватель очень лёгкий и не скачивает файлы.",
        "Включено.",
    ),
}


def setting_help(key: str, value: object, default: object) -> dict[str, object]:
    """Build the help payload for one AI setting."""
    title, value_type, _attr = AI_SETTING_SPECS[key]
    what, why, large, safe = _SETTING_HELP.get(key, ("", "", "", ""))
    return {
        "key": key,
        "title": title,
        "value_type": value_type,
        "value": _as_text(value),
        "default_value": _as_text(default),
        "what_it_does": what,
        "why": why,
        "large_value_effect": large,
        "safe_default": safe,
    }


def _as_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def human_size(num_bytes: int) -> str:
    """Human-readable file size (RU-friendly, ASCII units)."""
    size = float(num_bytes or 0)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            if unit == "Б":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"


__all__ = ["human_size", "setting_help"]
