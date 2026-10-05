"""Pairing credentials for the LAN mesh (pure + sealed storage).

Pairing is opt-in and never automatic: a discovered peer is untrusted until the
owner enters a short **pairing code** shown on the other computer. Only a salted
hash of the code is persisted. The secret used to authenticate peer requests is
the configured shared secret, which is never stored, logged or returned.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

#: Unambiguous alphabet (no 0/O/1/I) for hand-typed codes.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_pairing_code(length: int = 8) -> str:
    """Return a short human-typeable pairing code (not a long-lived secret)."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(max(6, length)))


def _normalise(code: str) -> str:
    return "".join((code or "").split()).upper()


def hash_pairing_code(code: str, *, salt: str) -> str:
    """Salted SHA-256 of a pairing code. The plaintext code is never stored."""
    material = f"{salt}:{_normalise(code)}".encode()
    return hashlib.sha256(material).hexdigest()


def verify_pairing_code(code: str, stored_hash: str, *, salt: str) -> bool:
    """Timing-safe verification of a pairing code against its stored hash."""
    if not stored_hash:
        return False
    candidate = hash_pairing_code(code, salt=salt)
    return hmac.compare_digest(candidate, stored_hash)


def derive_shared_secret(local_secret: str, remote_secret: str) -> str:
    """Derive a shared request secret from both sides' secrets.

    Both computers compute the same value from their own secret and the peer's,
    so it can be used to authenticate peer-to-peer requests without either side
    sending its stored secret over the network.
    """
    a = (local_secret or "").encode("utf-8")
    b = (remote_secret or "").encode("utf-8")
    first, second = sorted([a, b])
    return hashlib.sha256(b"tcms-mesh-v1|" + first + b"|" + second).hexdigest()


@dataclass(slots=True)
class PairingResult:
    node_id: str
    name: str
    shared_secret: str  # sealed before persistence; never returned by the API
    code: str


__all__ = [
    "CODE_ALPHABET",
    "PairingResult",
    "derive_shared_secret",
    "generate_pairing_code",
    "hash_pairing_code",
    "verify_pairing_code",
]
