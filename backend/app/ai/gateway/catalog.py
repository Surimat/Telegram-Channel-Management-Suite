"""Model-level capability catalog for the AI Gateway (v2.0).

A :class:`ProviderInfo` describes a *provider*; this module describes concrete
**models and operations**, because "text works" does not mean "vision works".
Each :class:`ModelCapability` states, per model:

* which operations it can serve (``text``, ``image_understanding``, ``pdf``,
  ``file``, ``structured``, ``translate``, ``image_generation``);
* how it authenticates (``none`` / ``api_key`` / ``browser_session``);
* its observed availability and an honest ``verified`` flag.

``verified`` is **False** for anything that was not actually exercised end to end
in this repository's environment. The only entry marked verified is the keyless
Pollinations text endpoint, which was probed on 2026-10-08 (see
``docs/AI_PROVIDERS.md``). Everything else is a declared capability the owner
must enable and probe; a README or a reachable URL is never treated as proof.

Nothing here performs network calls — it is the *matrix* the router and the UI
consult. Real enforcement lives in :class:`ProviderInfo.capabilities` and the
router's capability filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Operation identifiers (a model answers "can you do X?" for each).
OP_TEXT = "text"
OP_IMAGE = "image_understanding"
OP_PDF = "pdf"
OP_FILE = "file"
OP_STRUCTURED = "structured"
OP_TRANSLATE = "translate"
OP_IMAGE_GEN = "image_generation"

OPERATIONS: tuple[str, ...] = (
    OP_TEXT,
    OP_IMAGE,
    OP_PDF,
    OP_FILE,
    OP_STRUCTURED,
    OP_TRANSLATE,
    OP_IMAGE_GEN,
)

#: Operation → RU title for the UI.
OPERATION_TITLES: dict[str, str] = {
    OP_TEXT: "Текст",
    OP_IMAGE: "Понимание изображений",
    OP_PDF: "PDF-документы",
    OP_FILE: "Прочие файлы",
    OP_STRUCTURED: "Структурированный ответ (JSON)",
    OP_TRANSLATE: "Перевод",
    OP_IMAGE_GEN: "Генерация изображений",
}

#: Auth modes reused from the gateway types (kept as plain strings here).
AUTH_NONE = "no_auth"
AUTH_API_KEY = "api_key"
AUTH_BROWSER = "browser_session"

#: Availability of a catalog entry.
AVAIL_READY = "ready"  # needs nothing extra to try
AVAIL_NEEDS_KEY = "needs_key"
AVAIL_NEEDS_BROWSER = "needs_browser"
AVAIL_LOCAL = "local"  # runs on this machine (Ollama)
AVAIL_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """One model's honest capability record."""

    provider: str
    model: str
    kind: str
    source: str  # local | api | web
    operations: tuple[str, ...]
    auth: str = AUTH_API_KEY
    availability: str = AVAIL_UNKNOWN
    cost: str = "standard"
    #: True only when this exact operation was exercised in this environment.
    verified: bool = False
    verified_operations: tuple[str, ...] = ()
    note: str = ""
    params: dict[str, object] = field(default_factory=dict)

    def supports(self, operation: str) -> bool:
        return operation in self.operations

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "kind": self.kind,
            "source": self.source,
            "operations": list(self.operations),
            "auth": self.auth,
            "availability": self.availability,
            "cost": self.cost,
            "verified": self.verified,
            "verified_operations": list(self.verified_operations),
            "note": self.note,
            "params": dict(self.params),
        }


#: The shipped matrix. Ordered free-first, then by capability.
#:
#: IMPORTANT: only the Pollinations entry carries ``verified=True`` and only for
#: the operations actually probed. Do not set ``verified=True`` for a model that
#: merely compiles or whose homepage is reachable.
MODEL_CATALOG: tuple[ModelCapability, ...] = (
    ModelCapability(
        provider="pollinations",
        model="openai-fast",
        kind="pollinations",
        source="api",
        operations=(OP_TEXT, OP_STRUCTURED, OP_TRANSLATE),
        auth=AUTH_NONE,
        availability=AVAIL_READY,
        cost="free",
        verified=True,
        verified_operations=(OP_TEXT, OP_STRUCTURED),
        note=(
            "Бесплатный ключ-не-нужен текстовый эндпоинт (Pollinations). "
            "Проверено фактическим запросом 2026-10-08. Изображения/файлы НЕ "
            "поддерживаются — запрос с картинкой отклоняется сервисом."
        ),
        params={"base_url": "https://text.pollinations.ai/openai"},
    ),
    ModelCapability(
        provider="ollama",
        model="llama3.2 (или любая локальная)",
        kind="ollama",
        source="local",
        operations=(OP_TEXT, OP_STRUCTURED, OP_TRANSLATE),
        auth=AUTH_NONE,
        availability=AVAIL_LOCAL,
        cost="free",
        note=(
            "Локальный сервер на этом компьютере: данные не покидают его. "
            "Доступность зависит от запущенного Ollama, поэтому не помечена "
            "как проверенная здесь."
        ),
    ),
    ModelCapability(
        provider="openrouter",
        model="openrouter/auto",
        kind="openrouter",
        source="api",
        operations=(OP_TEXT, OP_IMAGE, OP_STRUCTURED, OP_TRANSLATE),
        auth=AUTH_API_KEY,
        availability=AVAIL_NEEDS_KEY,
        cost="cheap",
        note="Агрегатор; для vision нужна модель с поддержкой изображений.",
    ),
    ModelCapability(
        provider="google",
        model="gemini-2.0-flash",
        kind="google",
        source="api",
        operations=(OP_TEXT, OP_IMAGE, OP_PDF, OP_STRUCTURED, OP_TRANSLATE),
        auth=AUTH_API_KEY,
        availability=AVAIL_NEEDS_KEY,
        cost="cheap",
        note="Gemini поддерживает изображения и PDF; нужен ключ.",
    ),
    ModelCapability(
        provider="anthropic",
        model="claude-3-5-haiku-latest",
        kind="anthropic",
        source="api",
        operations=(OP_TEXT, OP_IMAGE, OP_PDF, OP_STRUCTURED, OP_TRANSLATE),
        auth=AUTH_API_KEY,
        availability=AVAIL_NEEDS_KEY,
        cost="premium",
        note="Claude поддерживает изображения и PDF; нужен ключ.",
    ),
    ModelCapability(
        provider="deepseek",
        model="deepseek-chat",
        kind="deepseek",
        source="api",
        operations=(OP_TEXT, OP_STRUCTURED, OP_TRANSLATE),
        auth=AUTH_API_KEY,
        availability=AVAIL_NEEDS_KEY,
        cost="cheap",
        note="Текстовая модель; без vision.",
    ),
    ModelCapability(
        provider="web:duckai",
        model="Duck.ai (web UI)",
        kind="web",
        source="web",
        operations=(OP_TEXT,),
        auth=AUTH_BROWSER,
        availability=AVAIL_NEEDS_BROWSER,
        cost="free",
        note=(
            "Ключ не нужен, но вход выполняет владелец в своей браузерной сессии. "
            "Бэкенд защищён анти-бот проверкой — она НЕ обходится."
        ),
    ),
    ModelCapability(
        provider="web:chatgpt",
        model="ChatGPT (web UI)",
        kind="web",
        source="web",
        operations=(OP_TEXT, OP_IMAGE, OP_FILE),
        auth=AUTH_BROWSER,
        availability=AVAIL_NEEDS_BROWSER,
        cost="free",
        note="Через вашу браузерную сессию ChatGPT; селекторы могут меняться.",
    ),
    ModelCapability(
        provider="web:gemini",
        model="Google Gemini (web UI)",
        kind="web",
        source="web",
        operations=(OP_TEXT, OP_IMAGE, OP_FILE),
        auth=AUTH_BROWSER,
        availability=AVAIL_NEEDS_BROWSER,
        cost="free",
        note="Через вашу браузерную сессию Google; требуется вход владельца.",
    ),
    ModelCapability(
        provider="web:copilot",
        model="Microsoft Copilot (web UI)",
        kind="web",
        source="web",
        operations=(OP_TEXT, OP_IMAGE),
        auth=AUTH_BROWSER,
        availability=AVAIL_NEEDS_BROWSER,
        cost="free",
        note="Через вашу браузерную сессию Copilot; требуется вход владельца.",
    ),
)


def models_supporting(operation: str) -> list[ModelCapability]:
    """Every catalog model that declares ``operation``."""
    return [m for m in MODEL_CATALOG if m.supports(operation)]


def verified_models(operation: str) -> list[ModelCapability]:
    """Models whose support for ``operation`` was actually exercised here."""
    return [
        m
        for m in MODEL_CATALOG
        if m.verified and operation in m.verified_operations
    ]


def matrix() -> list[dict[str, object]]:
    """The full matrix as plain dicts (API/UI friendly)."""
    return [m.as_dict() for m in MODEL_CATALOG]


def operation_titles() -> dict[str, str]:
    return dict(OPERATION_TITLES)


__all__ = [
    "AUTH_API_KEY",
    "AUTH_BROWSER",
    "AUTH_NONE",
    "AVAIL_LOCAL",
    "AVAIL_NEEDS_BROWSER",
    "AVAIL_NEEDS_KEY",
    "AVAIL_READY",
    "AVAIL_UNKNOWN",
    "MODEL_CATALOG",
    "OPERATIONS",
    "OPERATION_TITLES",
    "ModelCapability",
    "matrix",
    "models_supporting",
    "operation_titles",
    "verified_models",
]
