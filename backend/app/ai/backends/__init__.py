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
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

#: Backend name for the deterministic test/offline backend.
BACKEND_FAKE = "fake"
#: Backend name for the local llama.cpp runtime (the real one).
BACKEND_LLAMA_CPP = "llama_cpp"

#: The only environments in which the deterministic fake backend may be used.
#: Everywhere else it is refused outright, because a stub that silently answers
#: instead of the model is a lie the owner cannot see.
FAKE_ENVIRONMENTS = {"demo", "test"}

__all__ = [
    "BACKEND_FAKE",
    "BACKEND_LLAMA_CPP",
    "FAKE_ENVIRONMENTS",
    "FakeLlmBackend",
    "LlamaCppBackend",
    "LlmBackend",
    "build_backend",
    "reject_fake_outside_allowed_envs",
]


def reject_fake_outside_allowed_envs(settings: Settings) -> None:
    """Refuse the deterministic fake backend outside demo/test.

    Tests and the offline demo need the fake, so ``app_env`` ``demo``/``test``
    are allowed. Any other environment — including ``production`` and a bare
    default ``development`` — is refused: an owner-set ``ai_backend=fake`` would
    otherwise make the panel report "available" while producing fixed replies.
    """
    env = (settings.app_env or "").strip().lower()
    if env in FAKE_ENVIRONMENTS:
        return
    logger.warning(
        "Запрошен движок ИИ «эмуляция» (fake) в окружении %r — отказ: "
        "заглушка недопустима вне режимов «demo»/«test».",
        env,
    )
    raise AiError(
        "Движок ИИ «эмуляция» (fake) доступен только в режимах «demo» и «test».",
        how_to_fix=(
            "Укажите настоящий движок (llama_cpp) или запустите приложение в "
            "режиме «demo»/«test»."
        ),
    )


def build_backend(
    settings: Settings | None = None,
    *,
    name: str = "",
) -> LlmBackend:
    """Build an inference backend.

    ``name`` defaults to the configured backend, or the fake backend when the app
    runs in offline mode. The real llama.cpp backend is imported lazily so the
    runtime dependency stays optional. The fake backend is refused outside
    ``app_env`` ``demo``/``test``.
    """
    settings = settings or get_settings()
    chosen = (name or getattr(settings, "ai_backend", "") or "").strip().lower()
    if not chosen:
        chosen = BACKEND_FAKE if settings.offline_mode else BACKEND_LLAMA_CPP
    if chosen == BACKEND_FAKE:
        reject_fake_outside_allowed_envs(settings)
        return FakeLlmBackend()
    if chosen == BACKEND_LLAMA_CPP:
        return LlamaCppBackend(settings)
    raise AiError(
        "Неизвестный движок ИИ.",
        how_to_fix="Проверьте настройку движка ИИ (llama_cpp или fake).",
    )
