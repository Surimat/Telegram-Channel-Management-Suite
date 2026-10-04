"""Minimal JSON/HTTP helper for remote backup destinations.

Uses only the standard library (``urllib``) so no new runtime dependency is
added for optional cloud backups. The transport is injectable so the request
logic can be tested without network access.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None


#: A transport performs one HTTP request and returns a response.
Transport = Callable[[str, str, dict[str, str], bytes | None], HttpResponse]


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> HttpResponse:
    """Default transport backed by ``urllib.request``."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return HttpResponse(
                status=int(response.status),
                body=response.read(),
                headers={k.lower(): v for k, v in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            status=int(exc.code),
            body=exc.read() if exc.fp is not None else b"",
            headers={k.lower(): v for k, v in (exc.headers or {}).items()},
        )


def request_json(
    transport: Transport,
    method: str,
    url: str,
    *,
    token: str = "",
    payload: dict[str, Any] | None = None,
    raw: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[HttpResponse, Any]:
    """Perform a request and decode a JSON body when possible."""
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = raw
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = content_type
    response = transport(method, url, headers, body)
    return response, response.json()


__all__ = ["HttpResponse", "Transport", "request_json", "urllib_transport"]
