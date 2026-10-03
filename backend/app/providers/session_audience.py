"""Real :class:`AudienceProvider` backed by the PHASE 4 session provider.

Delegates every call to a :class:`~backend.app.providers.session_base.SessionProvider`
so all MTProto access stays behind a single interface. No Telethon import here.
"""

from __future__ import annotations

from backend.app.providers.audience_base import AudienceProvider
from backend.app.providers.session_base import SessionProvider
from backend.app.providers.types import EntityRef, ParticipantPage


class SessionAudienceProvider(AudienceProvider):
    """Adapter: :class:`AudienceProvider` → :class:`SessionProvider`."""

    def __init__(self, session_provider: SessionProvider) -> None:
        self._session = session_provider

    async def resolve_entity(self, ref: str) -> EntityRef:
        raw = (ref or "").strip()
        # Accept a plain numeric id as an int so entities can be resolved by id.
        target: str | int = int(raw) if raw.lstrip("-").isdigit() else raw
        return await self._session.resolve_entity(target)

    async def iter_participant_pages(
        self,
        ref: str,
        *,
        offset: int = 0,
        batch_size: int = 100,
        limit: int = 0,
    ) -> list[ParticipantPage]:
        raw = (ref or "").strip()
        target: str | int = int(raw) if raw.lstrip("-").isdigit() else raw
        return await self._session.iter_participant_pages(
            target, batch_size=batch_size, offset=offset, limit=limit
        )


__all__ = ["SessionAudienceProvider"]
