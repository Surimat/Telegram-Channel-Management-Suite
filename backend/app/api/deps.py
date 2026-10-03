"""Reusable FastAPI dependencies.

Services are constructed per request from a DB session plus injectable
collaborators (e.g. the Telegram provider factory). Tests override
:func:`get_provider_factory` to run the whole stack against the fake provider.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_session
from backend.app.providers.registry import build_bot_provider
from backend.app.services.bot_service import BotService, ProviderFactory


def get_provider_factory() -> ProviderFactory:
    """Return the factory used to build Telegram bot providers."""
    return build_bot_provider


def get_bot_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> BotService:
    return BotService(session, provider_factory=provider_factory)
