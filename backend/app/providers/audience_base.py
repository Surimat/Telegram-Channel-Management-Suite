"""Audience-source provider abstraction (PHASE 5).

Business logic (``AudienceService``) depends only on this interface, never on
Telethon or on a concrete account provider (decision D-001/D-026). The real
implementation (:class:`~backend.app.providers.session_audience.SessionAudienceProvider`)
delegates to the existing PHASE 4 :class:`SessionProvider`, so there is a single
place that talks MTProto. A pure fake lets the whole scan pipeline be tested
without a Telegram account or network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.providers.types import EntityRef, ParticipantPage


@runtime_checkable
class AudienceProvider(Protocol):
    """Read-only access to a Telegram source's members.

    Implementations MUST translate library errors into
    :mod:`backend.app.providers.errors` and MUST NOT bypass FloodWait / privacy
    / admin restrictions (D-006).
    """

    async def resolve_entity(self, ref: str) -> EntityRef:
        """Resolve a username, link or id to a channel/group/entity."""

    async def iter_participant_pages(
        self,
        ref: str,
        *,
        offset: int = 0,
        batch_size: int = 100,
        limit: int = 0,
    ) -> list[ParticipantPage]:
        """Return a bounded page of participants starting at ``offset``.

        The scanner drives this one page at a time so the member list is never
        fully buffered in memory (weak-machine friendly).
        """


__all__ = ["AudienceProvider"]
