"""llama.cpp inference backend (PHASE 7).

The **only** module that imports ``llama_cpp``. It is optional and imported
lazily so the application runs perfectly well without it. The backend is
model-agnostic: any decoder-only GGUF chat model works, and the model file is a
user runtime asset (never committed, never downloaded automatically).

Resource strategy for weak Windows PCs (D-035):

* models are loaded lazily on first use;
* a single :class:`threading.Lock` serializes inference — at most one generation
  runs at a time, so CPU/RAM stay bounded;
* with ``keep_loaded=False`` the model is released after every call so it does not
  occupy memory while idle.
"""

from __future__ import annotations

import threading
import time

from backend.app.ai.backends.base import LlmBackend
from backend.app.ai.errors import (
    InferenceTimeoutError,
    ModelLoadError,
    ModelNotFoundError,
    RuntimeUnavailableError,
)
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class LlamaCppBackend(LlmBackend):
    """Serve a local GGUF model through the optional ``llama_cpp`` runtime."""

    name = "llama_cpp"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._llm: object | None = None
        self._lock = threading.Lock()

    # --- availability / model ------------------------------------------------
    @property
    def available(self) -> bool:
        try:
            import llama_cpp  # noqa: F401
        except Exception:  # pragma: no cover - environment dependent
            return False
        return True

    def _model_path(self) -> str:
        return (self.settings.ai_model_path or "").strip()

    def resolve_model_file(self) -> str:
        """Return the configured model path, verifying it exists and is readable."""
        from pathlib import Path

        path_str = self._model_path()
        if not path_str:
            raise ModelNotFoundError("(путь не задан)")
        path = Path(path_str)
        if not path.is_file():
            raise ModelNotFoundError(path_str)
        try:
            with path.open("rb"):
                pass
        except OSError as exc:  # pragma: no cover - permission dependent
            raise ModelNotFoundError(path_str) from exc
        return str(path)

    @property
    def loaded(self) -> bool:
        return self._llm is not None

    def model_info(self) -> dict[str, object]:
        """Non-secret model metadata for the UI (path, size, presence)."""
        from pathlib import Path

        path_str = self._model_path()
        info: dict[str, object] = {"path": path_str, "exists": False, "size_bytes": 0}
        if not path_str:
            return info
        path = Path(path_str)
        try:
            if path.is_file():
                info["exists"] = True
                info["size_bytes"] = path.stat().st_size
        except OSError:
            pass
        return info

    # --- lifecycle -----------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            if self._llm is not None:
                return
            try:
                from llama_cpp import Llama
            except Exception as exc:  # pragma: no cover - environment dependent
                raise RuntimeUnavailableError() from exc
            model_path = self.resolve_model_file()
            try:
                self._llm = Llama(
                    model_path=model_path,
                    n_ctx=int(self.settings.ai_context_size),
                    n_threads=int(self.settings.ai_model_threads),
                    verbose=False,
                    chat_format=None,
                )
            except Exception as exc:  # pragma: no cover - model dependent
                self._llm = None
                logger.warning("AI model load failed: %s", type(exc).__name__)
                raise ModelLoadError(type(exc).__name__) from exc

    def unload(self) -> None:
        with self._lock:
            self._llm = None

    # --- inference -----------------------------------------------------------
    def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> str:
        started = time.monotonic()
        self.load()
        llm = self._llm
        if llm is None:  # pragma: no cover - defensive
            raise ModelLoadError("model not loaded")
        try:
            result = llm.create_chat_completion(  # type: ignore[attr-defined]
                messages=messages,
                max_tokens=max_tokens,
                temperature=float(self.settings.ai_temperature),
                top_p=0.9,
            )
        except Exception as exc:  # pragma: no cover - model dependent
            raise ModelLoadError(type(exc).__name__) from exc
        finally:
            elapsed = time.monotonic() - started
            if elapsed > float(self.settings.ai_timeout_seconds):
                # Timeout is detected after the blocking call returns/crashes.
                logger.warning("AI inference exceeded timeout (%.1fs)", elapsed)
            if not self.settings.ai_keep_loaded:
                self.unload()

        try:
            choices = result.get("choices") or []
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
        except Exception:  # pragma: no cover - defensive
            content = ""
        if not content and elapsed > float(self.settings.ai_timeout_seconds):
            raise InferenceTimeoutError()
        return str(content)


__all__ = ["LlamaCppBackend"]
