"""Optional ruBERT-tiny2 encoder backend (v1.1).

Wraps the MIT-licensed ``cointegrated/rubert-tiny2`` sentence encoder behind the
:class:`~backend.app.ai.backends.encoder_base.EncoderBackend` protocol. The
runtime (``torch`` + ``transformers``) is **never** a hard dependency and is only
imported inside :meth:`RuBertEncoderBackend.load`, so a machine that does not use
the encoder pays nothing.

Everything is CPU-only, single-model, lazy and unloadable — chosen deliberately
for a weak Windows PC (D-019/D-035). A load failure is an ordinary, reported
error; it never crashes the app and the hashing encoder remains the fallback.
"""

from __future__ import annotations

import threading

from backend.app.ai.errors import AiError
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

NAME = "rubert-tiny2"


class RuBertEncoderBackend:
    """A CPU-only ``rubert-tiny2`` sentence-embedding backend.

    ``model_path`` is the directory that holds the downloaded model files
    (``config.json`` + weights + tokenizer). When empty the backend reports itself
    unavailable rather than reaching out to the network.
    """

    name = NAME

    def __init__(self, model_path: str = "", *, max_length: int = 128) -> None:
        self._model_path = (model_path or "").strip()
        self._max_length = max_length
        self._model = None
        self._tokenizer = None
        self._torch = None
        self._dimension = 0
        self._lock = threading.Lock()

    # --- availability --------------------------------------------------------
    @property
    def available(self) -> bool:
        if not self._model_path:
            return False
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except Exception:  # pragma: no cover - optional runtime
            return False
        return True

    @property
    def runtime_available(self) -> bool:
        """True when the encoder runtime is importable (ignoring the model)."""
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except Exception:  # pragma: no cover - optional runtime
            return False
        return True

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        return self._dimension

    # --- lifecycle -----------------------------------------------------------
    def load(self) -> None:
        """Load tokenizer + model into memory (idempotent, CPU-only)."""
        with self._lock:
            if self._model is not None:
                return
            if not self._model_path:
                raise AiError(
                    "Модель не выбрана.",
                    how_to_fix="Установите лёгкую модель на странице «Мини-ИИ».",
                )
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer
            except Exception as exc:  # pragma: no cover - optional runtime
                raise AiError(
                    "Не установлена библиотека для лёгкой модели.",
                    how_to_fix="Нажмите «Установить лёгкую модель» на странице «Мини-ИИ».",
                ) from exc
            try:
                self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
                model = AutoModel.from_pretrained(self._model_path)
                model.eval()
                self._model = model
                self._torch = torch
                self._dimension = int(getattr(model.config, "hidden_size", 0) or 0)
            except Exception as exc:
                self._model = None
                self._tokenizer = None
                raise AiError(
                    "Не удалось загрузить лёгкую модель.",
                    how_to_fix="Проверьте, что файлы модели скачаны полностью.",
                ) from exc

    def unload(self) -> None:
        """Release the model from memory (idempotent)."""
        with self._lock:
            self._model = None
            self._tokenizer = None
            self._dimension = 0

    # --- inference -----------------------------------------------------------
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalised ``[CLS]`` embedding per text (CPU-only)."""
        if not texts:
            return []
        self.load()
        torch = self._torch
        assert torch is not None and self._model is not None and self._tokenizer is not None
        try:
            encoded = self._tokenizer(
                list(texts),
                padding=True,
                truncation=True,
                max_length=self._max_length,
                return_tensors="pt",
            )
            with torch.no_grad():
                output = self._model(**encoded)
            hidden = output.last_hidden_state[:, 0, :]
            normalised = torch.nn.functional.normalize(hidden, p=2, dim=1)
            return [[float(x) for x in row] for row in normalised.tolist()]
        except Exception as exc:  # pragma: no cover - runtime failure
            raise AiError(
                "Ошибка лёгкой модели.",
                how_to_fix="Попробуйте выгрузить и загрузить модель заново.",
            ) from exc


__all__ = ["NAME", "RuBertEncoderBackend"]
