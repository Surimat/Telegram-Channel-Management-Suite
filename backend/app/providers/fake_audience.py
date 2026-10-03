"""Pure fake :class:`AudienceProvider` (PHASE 5).

Implements the audience interface directly (no session provider, no network) so
the scan pipeline can be tested in isolation. Reuses
:class:`~backend.app.providers.fake_session.FakeAudienceScenario` for its data so
tests share one scenario vocabulary.
"""

from __future__ import annotations

from backend.app.providers.audience_base import AudienceProvider
from backend.app.providers.fake_session import FakeAudienceScenario, make_fake_users
from backend.app.providers.types import EntityRef, ParticipantPage


class FakeAudienceProvider(AudienceProvider):
    """Deterministic in-memory audience source."""

    def __init__(self, scenario: FakeAudienceScenario | None = None) -> None:
        self.scenario = scenario or FakeAudienceScenario()
        self.resolve_calls: list[str] = []
        self.page_calls: list[int] = []

    async def resolve_entity(self, ref: str) -> EntityRef:
        self.resolve_calls.append(ref)
        if self.scenario.resolve_error is not None:
            raise self.scenario.resolve_error
        raw = (ref or "").strip().lstrip("@")
        return EntityRef(
            id=abs(hash(raw)) % 10**10,
            username=raw if not raw.lstrip("-").isdigit() else "",
            title=self.scenario.title or raw or "Источник",
            kind=self.scenario.kind,
            participants_count=len(self.scenario.participants) or None,
            participants_hidden=self.scenario.participants_hidden,
        )

    async def iter_participant_pages(
        self,
        ref: str,
        *,
        offset: int = 0,
        batch_size: int = 100,
        limit: int = 0,
    ) -> list[ParticipantPage]:
        self.page_calls.append(offset)
        if self.scenario.participants_error is not None:
            raise self.scenario.participants_error
        total = self.scenario.reported_total
        if total is None:
            total = len(self.scenario.participants) or None
        if self.scenario.participants_hidden:
            return [ParticipantPage(users=[], total=total, exhausted=True)]
        users = list(self.scenario.participants)
        page_size = max(1, min(batch_size, self.scenario.page_size))
        if limit > 0:
            users = users[:limit]
        if offset >= len(users):
            return [ParticipantPage(users=[], total=total, exhausted=True)]
        window = users[offset : offset + page_size]
        exhausted = offset + len(window) >= len(users)
        # Simulate Telegram hiding part of the list: served fewer than reported.
        truncated = bool(total and offset + len(window) < total and exhausted)
        return [
            ParticipantPage(
                users=window, total=total, exhausted=exhausted, truncated=truncated
            )
        ]


def fake_audience_provider(*, count: int = 0, **kwargs: object) -> FakeAudienceProvider:
    """Convenience builder for tests: ``fake_audience_provider(count=120)``."""
    scenario = FakeAudienceScenario(participants=make_fake_users(count), **kwargs)  # type: ignore[arg-type]
    return FakeAudienceProvider(scenario)


__all__ = ["FakeAudienceProvider", "fake_audience_provider"]
