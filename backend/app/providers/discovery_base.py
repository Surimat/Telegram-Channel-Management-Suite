"""Donor discovery providers (v1.1: automated donor search).

The existing :class:`~backend.app.services.donor_service.DonorService` analyses
sources the owner already added. This module adds a *discovery* layer that
suggests **candidate** channels/groups the owner might use as donors:

* :class:`TelegramDiscoveryProvider` — uses the official Telegram search methods
  (``messages.searchGlobal`` / ``channels.getChannelRecommendations``) through a
  connected user account. It only uses capabilities the installed Telethon
  version actually exposes; otherwise it reports itself unavailable.
* :class:`WebDiscoveryProvider` — an **extension point** for public web search.
  The default implementation is inert (no network, no hard dependency on any
  search engine). A concrete engine can be plugged in later.
* :class:`ManualDiscoveryProvider` — always available; lets the owner type a
  reference directly.

Nothing here searches for or downloads other people's sessions, registers bulk
accounts, or bypasses Telegram limits (D-006, D-065). Discovery only *proposes*
candidates; the owner confirms before anything is added to sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class DiscoveryQuery:
    """Filters for a donor search (all optional)."""

    topic: str = ""
    keywords: list[str] = field(default_factory=list)
    language: str = ""
    min_subscribers: int = 0
    max_subscribers: int = 0
    active_only: bool = False
    period_days: int = 0
    #: Optional reference of a channel already in the registry. When set, the
    #: Telegram provider also asks for Telegram's official recommendations for
    #: that channel (channels.getChannelRecommendations) and merges them in.
    seed_channel: str = ""

    def text(self) -> str:
        parts = [self.topic, *self.keywords]
        return " ".join(p for p in parts if p).strip()


@dataclass(slots=True)
class DiscoveredChannel:
    """One candidate channel as observed by a provider (never invented)."""

    username: str = ""
    title: str = ""
    telegram_id: int | None = None
    kind: str = "channel"
    subscribers: int = 0
    avg_views: float = 0.0
    activity: float = 0.0
    language: str = ""
    provider: str = ""
    note: str = ""
    #: True when the provider could not read some fields (honest limitation).
    partial: bool = False


@dataclass(slots=True)
class DiscoveryResult:
    """Outcome of one discovery call."""

    provider: str
    ok: bool
    candidates: list[DiscoveredChannel] = field(default_factory=list)
    message: str = ""
    how_to_fix: str = ""
    available: bool = True


@runtime_checkable
class DonorDiscoveryProvider(Protocol):
    """A source of donor *candidates* (never an automatic addition)."""

    @property
    def name(self) -> str:
        ...

    @property
    def available(self) -> bool:
        """False when the provider cannot run (missing session/engine)."""
        ...

    async def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        """Return candidate channels for ``query`` (may be empty)."""
        ...


# ---------------------------------------------------------------------------
# Manual (always available)
# ---------------------------------------------------------------------------
class ManualDiscoveryProvider:
    """Turns a typed reference into a single candidate (no network)."""

    @property
    def name(self) -> str:
        return "manual"

    @property
    def available(self) -> bool:
        return True

    async def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        text = query.text()
        if not text:
            return DiscoveryResult(
                provider=self.name,
                ok=False,
                message="Укажите канал или ссылку.",
                how_to_fix="Например: @durov или https://t.me/durov.",
            )
        username = text.strip().rstrip("/").split("/")[-1].lstrip("@")
        return DiscoveryResult(
            provider=self.name,
            ok=True,
            candidates=[
                DiscoveredChannel(
                    username=username,
                    title=username,
                    provider="manual",
                    note="Введено вручную — проверьте перед добавлением.",
                    partial=True,
                )
            ],
            message="Кандидат добавлен из ручного ввода.",
        )


# ---------------------------------------------------------------------------
# Web (extension point; inert by default)
# ---------------------------------------------------------------------------
class WebDiscoveryProvider:
    """Extension point for public web search (no engine by default).

    ``engine`` is an optional async callable ``(query) -> list[DiscoveredChannel]``.
    With no engine the provider reports itself unavailable rather than pretending.
    """

    def __init__(self, engine: object | None = None) -> None:
        self._engine = engine

    @property
    def name(self) -> str:
        return "web"

    @property
    def available(self) -> bool:
        return callable(self._engine)

    async def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        if not self.available:
            return DiscoveryResult(
                provider=self.name,
                ok=False,
                available=False,
                message="Веб-поиск не настроен.",
                how_to_fix=(
                    "Веб-поиск — дополнительный источник. Используйте поиск Telegram "
                    "или ручной ввод."
                ),
            )
        try:
            found = await self._engine(query)  # type: ignore[misc]
        except Exception:
            # Engine failures are ordinary; the provider reports them honestly.
            return DiscoveryResult(
                provider=self.name,
                ok=False,
                message="Веб-поиск не ответил.",
                how_to_fix="Повторите позже или используйте поиск Telegram.",
            )
        return DiscoveryResult(
            provider=self.name,
            ok=True,
            candidates=list(found or []),
            message="Результаты веб-поиска получены.",
        )


__all__ = [
    "DiscoveredChannel",
    "DiscoveryQuery",
    "DiscoveryResult",
    "DonorDiscoveryProvider",
    "ManualDiscoveryProvider",
    "WebDiscoveryProvider",
]
