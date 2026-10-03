"""Reusable FastAPI dependencies.

Services are constructed per request from a DB session plus injectable
collaborators (e.g. the Telegram provider factory). Tests override
:func:`get_provider_factory` to run the whole stack against the fake provider.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_session
from backend.app.miniapp.service import MiniAppService
from backend.app.providers.registry import build_bot_provider, build_session_provider
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.audience_service import AudienceService
from backend.app.services.bot_service import BotService, ProviderFactory
from backend.app.services.invite_service import InviteService
from backend.app.services.reaction_service import ReactionService
from backend.app.services.session_service import SessionProviderFactory, SessionService


def get_provider_factory() -> ProviderFactory:
    """Return the factory used to build Telegram bot providers."""
    return build_bot_provider


def get_session_provider_factory() -> SessionProviderFactory:
    """Return the factory used to build MTProto user-account providers."""
    return build_session_provider


def get_bot_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> BotService:
    return BotService(session, provider_factory=provider_factory)


def get_reaction_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> ReactionService:
    return ReactionService(session, provider_factory=provider_factory)


def get_session_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> SessionService:
    return SessionService(session, provider_factory=provider_factory)


def get_audience_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> AudienceService:
    return AudienceService(session, session_provider_factory=provider_factory)


def get_invite_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> InviteService:
    return InviteService(session, session_provider_factory=provider_factory)


def get_analytics_service(session: AsyncSession = Depends(get_session)) -> AnalyticsService:
    return AnalyticsService(session)


def get_miniapp_service(session: AsyncSession = Depends(get_session)) -> MiniAppService:
    return MiniAppService(session)
