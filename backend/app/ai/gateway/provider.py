"""The ``AIProvider`` protocol — one interface for every AI source (v1.8).

Implementations report what they are (:attr:`AIProvider.info`), whether they can
run right now (:meth:`AIProvider.availability`), and how to actually call them
(:meth:`AIProvider.chat`). API adapters, local models and Web UI wrappers all
satisfy it, so the router never needs to know which kind it is driving.

A provider never invents a result: an unsupported modality or an auth gap is a
reported failure, not a silent downgrade. Nothing here exposes secrets.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.ai.gateway.types import (
    Availability,
    ChatRequest,
    ChatResponse,
    ProviderInfo,
)


@runtime_checkable
class AIProvider(Protocol):
    """A source of AI answers (API, local model or Web UI wrapper)."""

    @property
    def name(self) -> str:
        """Stable identifier (matches :attr:`ProviderInfo.provider`)."""
        ...

    @property
    def info(self) -> ProviderInfo:
        """Static description: source, capabilities, auth, cost."""
        ...

    def availability(self) -> Availability:
        """Best-effort live state (no network unless the provider can afford it)."""
        ...

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Run one request. Raise a :class:`GatewayError` on failure."""
        ...

    async def close(self) -> None:
        """Release resources (browser, HTTP client). Safe to call twice."""
        ...


@runtime_checkable
class StreamingAIProvider(Protocol):
    """Optional capability: yield text chunks as they arrive."""

    async def stream(self, request: ChatRequest):
        ...


__all__ = ["AIProvider", "StreamingAIProvider"]
