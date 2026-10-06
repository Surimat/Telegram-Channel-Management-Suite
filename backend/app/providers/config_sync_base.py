"""Config-sync provider protocol (v1.6).

A provider moves an **opaque, already-encrypted** bundle between this install and
some storage. It never sees plaintext configuration: the bundle is encrypted with
the owner-derived key before it reaches a provider, so a provider only handles
ciphertext (D-106).

The interface is deliberately tiny so a Local folder, Google Drive app-data, or a
test fake are interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ConfigSyncError(Exception):
    """A friendly, secret-free provider error."""

    def __init__(self, message: str, *, how_to_fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix


@dataclass(slots=True)
class RemoteBundle:
    """Metadata about a stored bundle (never its plaintext)."""

    revision: int
    device_id: str
    device_name: str
    updated_at: str
    size: int = 0
    #: Provider-specific opaque handle (Drive file id, local path, …).
    reference: str = ""


@runtime_checkable
class ConfigSyncProvider(Protocol):
    """Moves an encrypted config bundle to and from storage."""

    kind: str

    def available(self) -> bool:
        """True when the provider is configured enough to be used."""
        ...

    async def upload(self, data: bytes, *, revision: int) -> RemoteBundle:
        """Store ``data`` (ciphertext) and return its metadata."""
        ...

    async def download(self) -> tuple[bytes, RemoteBundle] | None:
        """Return the stored bundle and metadata, or ``None`` when absent."""
        ...

    async def delete(self) -> None:
        """Remove the stored bundle (disconnect)."""
        ...


__all__ = ["ConfigSyncError", "ConfigSyncProvider", "RemoteBundle"]
