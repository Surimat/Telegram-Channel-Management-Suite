"""Content source provider abstraction (v1.2: Content Studio grabber).

Business logic depends only on this interface; concrete providers (Telegram,
RSS, Atom, manual URL) live behind it, so new sources can be added without
touching the Content Service. No Telegram library type ever leaves a provider
(D-001), and providers never bypass a source's protection (D-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class FetchedItem:
    """One item returned by a content provider.

    ``entities`` is a list of Telegram-style entity dicts
    (``{"type": "bold", "offset": 0, "length": 4}``). ``media_urls`` lists media
    the provider found but did not download (downloading is a separate, opt-in
    step). ``protected`` is set when the source forbids reuse.
    """

    title: str = ""
    text: str = ""
    source_url: str = ""
    source_message_id: int | None = None
    source_channel: str = ""
    source_author: str = ""
    published_at: str = ""
    entities: list[dict[str, object]] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)
    protected: bool = False
    #: Provider-specific extra metadata (kept minimal, never secret).
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class FetchResult:
    """Outcome of one fetch call."""

    ok: bool
    items: list[FetchedItem] = field(default_factory=list)
    message: str = ""
    how_to_fix: str = ""
    #: True when the source is protected and cannot be auto-copied.
    protected: bool = False
    #: Conditional-GET state to persist (so the next run is incremental).
    etag: str = ""
    last_modified: str = ""
    #: The newest item's stable id (for ``last_seen_item``).
    last_seen_item: str = ""


@dataclass(slots=True)
class ContentQuery:
    """Parameters for a manual/public discovery fetch."""

    reference: str = ""          # URL or @username
    limit: int = 20
    since: str = ""              # ISO date; only newer items
    account_id: str = ""         # a user account for Telegram sources


@runtime_checkable
class ContentSourceProvider(Protocol):
    """Fetch content items from one kind of source."""

    @property
    def kind(self) -> str:
        """Provider id (``telegram``/``rss``/``atom``/``manual``)."""
        ...

    @property
    def title(self) -> str:
        """Human-readable provider title (safe to display)."""
        ...

    async def fetch(self, query: ContentQuery, *, state: dict[str, str]) -> FetchResult:
        """Fetch items.

        ``state`` carries the persisted ``etag``/``last_modified``/``last_seen_item``
        so the provider can be incremental. Implementations must never raise for
        an ordinary network/source problem — return ``ok=False`` with a friendly
        message instead, and must never bypass a source's protection.
        """
        ...

    def available(self) -> tuple[bool, str]:
        """Return ``(available, reason)`` for the provider (honest status)."""
        ...


__all__ = [
    "ContentQuery",
    "ContentSourceProvider",
    "FetchResult",
    "FetchedItem",
]
