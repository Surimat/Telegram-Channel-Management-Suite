"""Owner-auth cryptography (v1.6).

Two independent secrets are derived from what the owner types, and they are kept
separate on purpose (D-105):

* a **verifier** — a slow PBKDF2-HMAC-SHA256 hash used only to check a password
  or PIN at login. It is stored, but it can never be turned back into the
  password.
* a **config-bundle key** — derived from the password plus a non-secret
  per-owner ``sync_salt``. It is *never* stored; it is recomputed in memory when
  the owner unlocks and is used to encrypt/decrypt the config-sync bundle.

Neither value is logged, returned by the API or included in diagnostics. The
module is deliberately dependency-free (stdlib only) so the Owner Auth layer works
on a weak Windows PC with no extra install.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16
_KEY_BYTES = 32


class OwnerSecretError(ValueError):
    """Raised when an owner secret cannot be processed."""


def generate_salt() -> str:
    """Return a fresh, non-secret hex salt for bundle-key derivation."""
    return secrets.token_hex(_SALT_BYTES)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_secret(secret: str, *, iterations: int = _ITERATIONS) -> str:
    """Return a PBKDF2 verifier string for ``secret``.

    Format: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``. The secret is
    never stored; only this one-way verifier is.
    """
    if not secret:
        raise OwnerSecretError("Пустой пароль недопустим.")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_secret(secret: str, verifier: str) -> bool:
    """Constant-time check of ``secret`` against a stored verifier."""
    if not secret or not verifier:
        return False
    try:
        algo, iter_s, salt_s, hash_s = verifier.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iter_s)
        salt = _unb64(salt_s)
        expected = _unb64(hash_s)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


def derive_bundle_key(secret: str, sync_salt: str, *, iterations: int = _ITERATIONS) -> bytes:
    """Derive the 32-byte config-bundle encryption key from the owner secret.

    Not stored anywhere. The ``sync_salt`` is non-secret and stored beside the
    identity so the key can be recomputed after a password change or a restore.
    """
    if not secret:
        raise OwnerSecretError("Пустой пароль недопустим.")
    salt = (sync_salt or "").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations, dklen=_KEY_BYTES)


__all__ = [
    "OwnerSecretError",
    "derive_bundle_key",
    "generate_salt",
    "hash_secret",
    "verify_secret",
]
