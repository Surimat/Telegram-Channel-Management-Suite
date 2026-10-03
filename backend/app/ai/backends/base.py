"""Inference backends for the Tiny AI (PHASE 7).

A backend is the *only* place that touches a concrete runtime (llama.cpp). It
receives already-built chat messages and returns raw model text. It is
deliberately dumb: no prompt construction, no schema validation, no routing —
those live in :mod:`backend.app.ai.prompt`, :mod:`backend.app.ai.schema` and the
service layer. This keeps the runtime swappable.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmBackend(Protocol):
    """A local text-completion backend (llama.cpp and future equivalents)."""

    @property
    def name(self) -> str:
        """Human-readable backend name (safe to log/show)."""
        ...

    @property
    def available(self) -> bool:
        """True when the runtime is importable and a model can be served."""
        ...

    def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> str:
        """Return the model's raw text for ``messages``.

        May raise :class:`backend.app.ai.errors.AiError` subclasses for ordinary
        failures (timeout, missing runtime, load failure); the caller handles
        them and falls back to rules.
        """
        ...

    def load(self) -> None:
        """Load the model into memory (idempotent)."""
        ...

    def unload(self) -> None:
        """Release the model from memory (idempotent)."""
        ...

    @property
    def loaded(self) -> bool:
        """True when a model is currently loaded in memory."""
        ...


__all__ = ["LlmBackend"]
