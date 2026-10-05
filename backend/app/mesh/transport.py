"""Peer-to-peer transport for the LAN mesh.

The service depends on the :class:`MeshTransport` protocol, not on a concrete
HTTP client, so tests can inject an in-memory transport and no network is needed.
The default :class:`HttpMeshTransport` speaks JSON over the peer's HTTP port using
only the standard library (no extra dependency), authenticating each request with
the shared secret derived during pairing. It never sends a stored secret itself.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


class MeshTransportError(RuntimeError):
    """Raised when a peer request fails (unreachable, timeout, rejected)."""

    def __init__(self, message: str, *, reason: str = "error") -> None:
        super().__init__(message)
        self.message = message
        #: "ok" | "timeout" | "unauthorized" | "error"
        self.reason = reason


@dataclass(slots=True)
class PeerAddress:
    host: str
    port: int


class MeshTransport(Protocol):
    """Sends authenticated JSON requests to a peer node."""

    async def request(
        self, peer: PeerAddress, path: str, payload: dict, *, secret: str
    ) -> dict:
        ...


@dataclass
class HttpMeshTransport:
    """Default transport: JSON over HTTP with a shared-secret header."""

    timeout: float = 5.0

    async def request(
        self, peer: PeerAddress, path: str, payload: dict, *, secret: str
    ) -> dict:
        return await asyncio.to_thread(self._request_sync, peer, path, payload, secret)

    def _request_sync(
        self, peer: PeerAddress, path: str, payload: dict, secret: str
    ) -> dict:
        url = f"http://{peer.host}:{peer.port}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        # The shared secret authenticates the request; it is never stored in logs.
        req.add_header("X-Mesh-Secret", secret or "")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise MeshTransportError("Пир отклонил запрос.", reason="unauthorized") from exc
            raise MeshTransportError(
                f"Пир вернул ошибку {exc.code}.", reason="error"
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise MeshTransportError("Пир недоступен.", reason="timeout") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise MeshTransportError("Некорректный ответ пира.", reason="error") from exc
        if not isinstance(data, dict):
            raise MeshTransportError("Некорректный ответ пира.", reason="error")
        return data


@dataclass
class RecordingTransport:
    """In-memory transport for tests: scripts responses and records requests."""

    responses: dict[str, dict] = field(default_factory=dict)
    requests: list[tuple[str, str, dict]] = field(default_factory=list)
    fail_with: MeshTransportError | None = None

    async def request(
        self, peer: PeerAddress, path: str, payload: dict, *, secret: str
    ) -> dict:
        self.requests.append((f"{peer.host}:{peer.port}", path, payload))
        if self.fail_with is not None:
            raise self.fail_with
        return dict(self.responses.get(path, {"ok": True}))


__all__ = [
    "HttpMeshTransport",
    "MeshTransport",
    "MeshTransportError",
    "PeerAddress",
    "RecordingTransport",
]
