"""Audience provider tests (PHASE 5): the abstraction and its adapters.

Verifies that the real adapter (``SessionAudienceProvider``) only depends on the
``SessionProvider`` interface and translates Telegram errors, and that the fake
provider is a faithful, offline stand-in for business-logic tests.
"""

from __future__ import annotations

import pytest

from backend.app.providers.errors import (
    ChatAdminRequiredError,
    EntityNotFoundError,
    FloodWaitError,
    PrivacyRestrictedError,
)
from backend.app.providers.fake_audience import FakeAudienceProvider, fake_audience_provider
from backend.app.providers.fake_session import (
    FakeAudienceScenario,
    FakeAuthScenario,
    FakeSessionProvider,
    make_fake_users,
)
from backend.app.providers.session_audience import SessionAudienceProvider


async def test_fake_provider_pages_and_limit() -> None:
    provider = fake_audience_provider(count=120, page_size=50)
    pages = await provider.iter_participant_pages("@s", offset=0, batch_size=50)
    assert len(pages) == 1
    assert len(pages[0].users) == 50
    assert pages[0].total == 120
    assert pages[0].truncated is False


async def test_fake_provider_truncates_at_limit() -> None:
    provider = fake_audience_provider(count=120, page_size=50)
    pages = await provider.iter_participant_pages("@s", offset=100, batch_size=50, limit=110)
    # Only 10 users remain within the limit.
    assert len(pages[0].users) == 10
    assert pages[0].truncated is True


async def test_fake_provider_reports_hidden_participants() -> None:
    provider = FakeAudienceProvider(
        FakeAudienceScenario(participants=[], participants_hidden=True, reported_total=50)
    )
    entity = await provider.resolve_entity("@closed")
    assert entity.participants_hidden is True
    assert entity.participants_count is None


async def test_fake_provider_errors() -> None:
    provider = FakeAudienceProvider(
        FakeAudienceScenario(participants_error=FloodWaitError(30))
    )
    with pytest.raises(FloodWaitError):
        await provider.iter_participant_pages("@s", offset=0, batch_size=10)


async def test_session_audience_wraps_session_provider() -> None:
    """The adapter must work purely through the SessionProvider interface."""
    from backend.app.providers.fake_session import FakeSessionProvider

    session_provider = FakeSessionProvider(
        scenario=FakeAuthScenario(),
        audience=FakeAudienceScenario(participants=make_fake_users(30), page_size=10),
    )
    provider = SessionAudienceProvider(session_provider)
    assert isinstance(provider, SessionAudienceProvider)

    entity = await provider.resolve_entity("@s")
    assert entity.id
    pages = await provider.iter_participant_pages("@s", offset=0, batch_size=10)
    assert len(pages[0].users) == 10


async def test_session_audience_accepts_numeric_id() -> None:
    session_provider = FakeSessionProvider(
        scenario=FakeAuthScenario(),
        audience=FakeAudienceScenario(participants=make_fake_users(5)),
    )
    provider = SessionAudienceProvider(session_provider)
    # A numeric reference must be passed through as an int without raising.
    entity = await provider.resolve_entity("123456789")
    assert entity.id


async def test_error_translation_is_friendly() -> None:
    """Every audience error carries a human message and a fix hint (D-016)."""
    for error in (
        FloodWaitError(15),
        PrivacyRestrictedError(),
        ChatAdminRequiredError(),
        EntityNotFoundError("@missing"),
    ):
        assert error.message
        assert error.how_to_fix


async def test_registry_builds_audience_provider() -> None:
    from backend.app.providers.registry import build_audience_provider

    session_provider = FakeSessionProvider(
        scenario=FakeAuthScenario(),
        audience=FakeAudienceScenario(participants=make_fake_users(3)),
    )
    provider = build_audience_provider(session_provider)
    assert provider is not None
    pages = await provider.iter_participant_pages("@s", offset=0, batch_size=10)
    assert len(pages[0].users) == 3
