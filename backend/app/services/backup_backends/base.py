"""Backup destination providers (product slice: pluggable backups).

A provider is the *only* place that knows how to deliver a backup to one kind of
destination (local disk, Google Drive, Yandex Disk, Telegram). The service layer
builds a provider by name and calls a tiny, uniform interface — so adding a new
destination means registering a name here and nothing else.

Remote providers are optional and off by default. They never log or return
credentials, and they surface ordinary failures as friendly messages rather than
raising out of the backup flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class ProviderStatus:
    """Result of a provider availability/connectivity check."""

    configured: bool
    reachable: bool
    message: str
    account_label: str = ""
    available_space: int | None = None


@dataclass(slots=True)
class UploadResult:
    """Result of delivering one backup file."""

    ok: bool
    message: str = ""
    location: str = ""  # display-safe destination (folder name / remote path)
    how_to_fix: str = ""


@runtime_checkable
class BackupProvider(Protocol):
    """A destination a backup can be written to."""

    @property
    def name(self) -> str:
        """Stable provider id (matches DestinationKind)."""
        ...

    @property
    def title(self) -> str:
        """Human-readable destination title (safe to display)."""
        ...

    def check(self) -> ProviderStatus:
        """Report whether this destination is configured and reachable."""
        ...

    def upload(self, filename: str, content: bytes, *, caption: str = "") -> UploadResult:
        """Deliver ``content`` under ``filename``.

        Must not raise for ordinary failures; returns ``UploadResult(ok=False)``
        with a friendly message instead.
        """
        ...


@dataclass(slots=True)
class ProviderInfo:
    """Static description of a provider for the UI."""

    name: str
    title: str
    requires_credentials: bool = False
    config_fields: list[str] = field(default_factory=list)
    help: str = ""


__all__ = [
    "BackupProvider",
    "ProviderInfo",
    "ProviderStatus",
    "UploadResult",
]
