"""Encoder backends for the lightweight AI (v1.1: ruBERT-tiny2 level).

The dependency-free hashing encoder in :mod:`backend.app.ai.encoder` is the
default and always works. This module adds a *swappable* embedding backend so a
real Russian encoder (``cointegrated/rubert-tiny2``, MIT) can be used when the
user installs it — without making it a hard dependency.

A backend only turns text into vectors; the prototype/KNN classification lives in
:class:`backend.app.ai.encoder.EncoderClassifier`. That separation keeps the
heavy runtime (``torch``/``transformers``) fully optional and lazy.

Design constraints (weak Windows PC, D-019/D-035):

* no heavy dependency is imported at module import time;
* ``load()`` is idempotent and CPU-only; ``unload()`` frees memory;
* ``available`` is honest: it is False when the runtime is missing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EncoderBackend(Protocol):
    """Turns text into fixed-dimension embeddings (a lightweight encoder)."""

    @property
    def name(self) -> str:
        """Human-readable backend name (safe to log/show)."""
        ...

    @property
    def available(self) -> bool:
        """True when the runtime is importable and a model can be served."""
        ...

    @property
    def loaded(self) -> bool:
        """True when the model is currently loaded in memory."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimension (0 when unknown until loaded)."""
        ...

    def load(self) -> None:
        """Load the model into memory (idempotent)."""
        ...

    def unload(self) -> None:
        """Release the model from memory (idempotent)."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalised vector per text (may raise ``AiError``)."""
        ...


__all__ = ["EncoderBackend"]
