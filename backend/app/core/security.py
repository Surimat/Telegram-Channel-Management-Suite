"""Security helpers: secret key validation and derived encryption material.

Local sessions are signed and at-rest secrets are encrypted with keys derived
from ``APP_SECRET_KEY``. Session files themselves are managed by Telethon and
stored outside git (see ``docs/SECURITY.md``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from backend.app.core.config import Settings, get_settings

_MIN_SECRET_BYTES = 16


class SecretKeyError(RuntimeError):
    """Raised when the configured secret key is unusable."""


def validate_secret_key(settings: Settings | None = None) -> None:
    """Ensure ``APP_SECRET_KEY`` is present and long enough for production use."""
    settings = settings or get_settings()
    key = settings.app_secret_key.get_secret_value()
    if settings.is_production and len(key.encode("utf-8")) < _MIN_SECRET_BYTES:
        raise SecretKeyError(
            "APP_SECRET_KEY must be set to a long random value in production. "
            'Generate one with: python -c "import secrets; '
            'print(secrets.token_urlsafe(48))"'
        )


def derive_key(context: str, settings: Settings | None = None) -> bytes:
    """Derive a 32-byte key for ``context`` from the app secret key.

    Used for encryption of at-rest secrets. Never log or return the result.
    """
    settings = settings or get_settings()
    base = settings.app_secret_key.get_secret_value().encode("utf-8")
    return hashlib.sha256(base + b"|" + context.encode("utf-8")).digest()


def generate_secret_key() -> str:
    """Generate a suitable random secret key."""
    return secrets.token_urlsafe(48)


def constant_time_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def sign_value(value: str, settings: Settings | None = None) -> str:
    """Return an HMAC signature for ``value`` (used for signed local cookies)."""
    key = derive_key("signing", settings)
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
