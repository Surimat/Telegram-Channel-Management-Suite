"""Owner-auth API guard (v1.6).

Local-first security: while no owner profile exists — or protection is explicitly
turned off — the API stays open, exactly as before. Once the owner creates a
profile and leaves protection on, every API call except a small allowlist must
carry a valid, signed owner token.

The token is an HMAC-signed opaque string (never a password, never reversible to
one). It is issued by ``POST /api/v1/owner/login`` and sent by the SPA as the
``X-Owner-Token`` header. The guard never logs the token and never stores it.

This is deliberately a *middleware* rather than a per-route dependency so a new
router cannot accidentally be added unguarded: protection is default-on for
anything outside the allowlist.
"""

from __future__ import annotations

import posixpath
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.core.security import constant_time_compare, sign_value

#: Paths reachable without an owner token (login/setup/health/static/docs).
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/assets",
    "/api/v1/owner/status",
    "/api/v1/owner/setup",
    "/api/v1/owner/login",
    "/api/v1/owner/session",
    "/api/v1/owner/sync/google/callback",
    "/api/v1/system/status",
    "/api/v1/system/setup",
)

#: Header the SPA uses to present the owner token.
TOKEN_HEADER = "X-Owner-Token"

#: Token prefix so a leaked/foreign value is obviously not a password.
_TOKEN_PREFIX = "owner"


def issue_token(owner_id: str) -> str:
    """Return a signed owner token for ``owner_id`` (never a password)."""
    return f"{_TOKEN_PREFIX}.{sign_value(f'{_TOKEN_PREFIX}:{owner_id}')}"


def verify_token(token: str, owner_id: str) -> bool:
    """Constant-time check that ``token`` was issued for ``owner_id``."""
    if not token or not owner_id:
        return False
    expected = issue_token(owner_id)
    return constant_time_compare(token, expected)


def _normalize_path(path: str) -> str:
    """Collapse redundant slashes/segments so the guard sees the routed path.

    The guard compares ``request.url.path`` while the router matches the same raw
    path. A doubled slash (``//api/v1/...``) or a ``/./`` segment must not change
    which branch of the check runs: normalize first so the guard can never be
    tricked into treating an API path as a non-API one.
    """
    if "\\" in path:
        path = path.replace("\\", "/")
    # POSIX ``normpath`` keeps a leading ``//`` as a special case; collapse runs
    # of slashes first so ``//api/...`` normalizes like ``/api/...``.
    collapsed = re.sub(r"/+", "/", path)
    normalized = posixpath.normpath(collapsed)
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _matches_allowlist(path: str) -> bool:
    """Exact match or a real child path (``/health`` but not ``/healthcheck``)."""
    return any(path == prefix or path.startswith(prefix + "/") for prefix in ALLOWLIST_PREFIXES)


def is_protected(path: str) -> bool:
    """True when ``path`` requires an owner token (i.e. not allowlisted)."""
    normalized = _normalize_path(path)
    if not normalized.startswith("/api/"):
        return False
    return not _matches_allowlist(normalized)


class OwnerGuardMiddleware(BaseHTTPMiddleware):
    """Reject API calls that lack a valid owner token while protection is on.

    The owner state is read fresh on every protected API call. It is deliberately
    not cached: a stale "protected" flag would keep rejecting requests for a
    moment after the owner turns protection off, and a stale "open" flag would
    briefly let requests through right after enabling protection. Static assets
    are never queried (they are not under ``/api``).
    """

    def __init__(self, app, *, state_provider=None) -> None:
        super().__init__(app)
        self._state_provider = state_provider

    async def _owner(self) -> tuple[str, bool]:
        """Return ``(owner_id, protection_active)``."""
        try:
            if self._state_provider is not None:
                return await self._state_provider()

            from backend.app.db.repositories.owners import OwnerRepository
            from backend.app.db.session import get_session_factory

            async with get_session_factory()() as session:
                owner = await OwnerRepository(session).get_single()
                if owner is not None:
                    return owner.id, bool(owner.enabled)
        except Exception:
            # Never lock the owner out because the DB hiccuped: degrade to open.
            return "", False
        return "", False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS" or not is_protected(request.url.path):
            return await call_next(request)

        owner_id, active = await self._owner()
        if not active or not owner_id:
            return await call_next(request)

        token = request.headers.get(TOKEN_HEADER, "")
        if verify_token(token, owner_id):
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "unauthorized",
                    "message": "Для этого действия нужно войти как владелец.",
                    "hint": "Откройте раздел «Владелец» и войдите.",
                    "details": None,
                }
            },
        )


__all__ = [
    "ALLOWLIST_PREFIXES",
    "TOKEN_HEADER",
    "OwnerGuardMiddleware",
    "is_protected",
    "issue_token",
    "verify_token",
]
