"""Signed Mini App session tokens.

After ``initData`` is verified once, the client is given a short, HMAC-signed
token (not a JWT dependency) so later requests can be authenticated without
re-sending ``initData``. Tokens are bound to the Telegram user id and an expiry
and signed with a key derived from ``APP_SECRET_KEY`` (D-010/D-012).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import derive_key


class MiniAppSessionError(Exception):
    """Raised when a session token is missing, tampered, or expired."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or "Сессия недействительна.")
        self.reason = reason
        self.message = message or "Сессия недействительна."


@dataclass(frozen=True)
class MiniAppSession:
    telegram_id: int
    expires_at: int
    is_admin: bool = False


def _signing_key(settings: Settings | None = None) -> bytes:
    return derive_key("miniapp-session", settings)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_session(
    telegram_id: int,
    *,
    is_admin: bool = False,
    ttl: int | None = None,
    settings: Settings | None = None,
    now: float | None = None,
) -> str:
    """Create a signed session token for a verified Telegram user."""
    cfg = settings or get_settings()
    lifetime = cfg.miniapp_session_ttl if ttl is None else ttl
    current = int(time.time() if now is None else now)
    payload = {"sub": int(telegram_id), "exp": current + int(lifetime), "adm": bool(is_admin)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_signing_key(cfg), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def verify_session(
    token: str,
    *,
    settings: Settings | None = None,
    now: float | None = None,
) -> MiniAppSession:
    """Validate a session token and return its claims.

    Raises :class:`MiniAppSessionError` on any tampering or expiry.
    """
    cfg = settings or get_settings()
    if not token or "." not in token:
        raise MiniAppSessionError("missing", "Требуется вход через Telegram.")
    body, _, signature = token.partition(".")
    expected = hmac.new(_signing_key(cfg), body.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _unb64(signature)
    except (ValueError, TypeError):
        raise MiniAppSessionError("bad_signature") from None
    if not hmac.compare_digest(expected, provided):
        raise MiniAppSessionError("bad_signature")

    try:
        payload = json.loads(_unb64(body))
        telegram_id = int(payload["sub"])
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError):
        raise MiniAppSessionError("malformed") from None

    current = int(time.time() if now is None else now)
    if expires_at <= current:
        raise MiniAppSessionError("expired", "Сессия истекла, войдите заново.")
    return MiniAppSession(
        telegram_id=telegram_id,
        expires_at=expires_at,
        is_admin=bool(payload.get("adm", False)),
    )
