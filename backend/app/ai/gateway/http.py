"""A tiny HTTP transport used by API providers (v1.8).

Providers never call ``httpx`` directly: they go through :class:`HttpTransport`.
That keeps them testable with a fake transport (no network in CI) and keeps the
dependency in one place. The real transport is imported lazily so importing the
gateway package never requires ``httpx`` at import time.
"""

from __future__ import annotations

import asyncio
import json as _json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class HttpResponse:
    status: int = 0
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    #: Populated by the transport when the request never reached the server.
    error: str = ""
    timed_out: bool = False

    def json(self) -> Any:
        try:
            return _json.loads(self.text)
        except (ValueError, TypeError):
            return None


@runtime_checkable
class HttpTransport(Protocol):
    """Minimal POST/GET interface (JSON-oriented)."""

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> HttpResponse:
        ...

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        ...


class HttpxTransport:
    """Real transport backed by ``httpx`` (lazy import)."""

    def __init__(self) -> None:
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient()
        return self._client

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> HttpResponse:
        client = self._get_client()
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
            return HttpResponse(
                status=resp.status_code,
                text=resp.text,
                headers=dict(resp.headers),
            )
        except Exception as exc:
            timed_out = isinstance(exc, asyncio.TimeoutError) or (
                "timeout" in type(exc).__name__.lower()
            )
            return HttpResponse(error=f"{type(exc).__name__}", timed_out=timed_out)

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        client = self._get_client()
        try:
            resp = await client.get(url, headers=headers, timeout=timeout)
            return HttpResponse(
                status=resp.status_code,
                text=resp.text,
                headers=dict(resp.headers),
            )
        except Exception as exc:
            timed_out = isinstance(exc, asyncio.TimeoutError) or (
                "timeout" in type(exc).__name__.lower()
            )
            return HttpResponse(error=f"{type(exc).__name__}", timed_out=timed_out)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None


class FakeHttpTransport:
    """Deterministic transport for tests: routes URL substrings to canned replies."""

    def __init__(self, routes: dict[str, HttpResponse] | None = None) -> None:
        self.routes = routes or {}
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def _resolve(self, url: str) -> HttpResponse:
        for fragment, reply in self.routes.items():
            if fragment in url:
                return reply
        return HttpResponse(status=404, text='{"error":"no route"}')

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> HttpResponse:
        self.requests.append(("POST", url, payload))
        return self._resolve(url)

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        self.requests.append(("GET", url, {}))
        return self._resolve(url)

    async def close(self) -> None:
        return None


__all__ = [
    "FakeHttpTransport",
    "HttpResponse",
    "HttpTransport",
    "HttpxTransport",
]
