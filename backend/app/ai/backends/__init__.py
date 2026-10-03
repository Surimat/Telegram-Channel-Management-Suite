"""Inference backend protocols and the registry factory (PHASE 7).

The registry is the single switchboard for building a backend by name. Adding a
future backend (another GGUF runtime, a remote API classifier) means registering
a new name here and nothing else.
"""

from __future__ import annotations

from backend.app.ai.backends.base import LlmBackend
from backend.app.ai.backends.fake import FakeLlmBackend
from backend.app.ai.backends.llama_cpp import LlamaCppBackend
from backend.app.ai.errors import AiError
from backend.app.core.config import Settings, get_settings

#: Backend name for the deterministic test/offline backend.
BACKEND_FAKE = "fake"
#: Backend name for the local llama.cpp runtime (the real one).
BACKEND_LLAMA_CPP = "llama_cpp"

__all__ = [
    "BACKEND_FAKE",
    "BACKEND_LLAMA_CPP",
    "FakeLlmBackend",
    "LlamaCppBackend",
    "LlmBackend",
    "build_backend",
]


def build_backend(
    settings: Settings | None = None,
    *,
    name: str = "",
) -> LlmBackend:
    """Build an inference backend.

    ``name`` defaults to the configured backend, or the fake backend when the app
    runs in offline mode. The real llama.cpp backend is imported lazily so the
    runtime dependency stays optional.
    """
    settings = settings or get_settings()
    chosen = (name or getattr(settings, "ai_backend", "") or "").strip().lower()
    if not chosen:
        chosen = BACKEND_FAKE if settings.offline_mode else BACKEND_LLAMA_CPP
    if chosen == BACKEND_FAKE:
        return FakeLlmBackend()
    if chosen == BACKEND_LLAMA_CPP:
        return LlamaCppBackend(settings)
    raise AiError(
        "Неизвестный движок ИИ.",
        how_to_fix="Проверьте настройку движка ИИ (llama_cpp или fake).",
    )
