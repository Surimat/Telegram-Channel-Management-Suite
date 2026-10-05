"""Reusable FastAPI dependencies.

Services are constructed per request from a DB session plus injectable
collaborators (e.g. the Telegram provider factory). Tests override
:func:`get_provider_factory` to run the whole stack against the fake provider.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_session
from backend.app.manager.service import ManagerBotService
from backend.app.miniapp.service import MiniAppService
from backend.app.providers.registry import build_bot_provider, build_session_provider
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.audience_service import AudienceService
from backend.app.services.backup_service import BackupService
from backend.app.services.binding_service import BindingService
from backend.app.services.bot_service import BotService, ProviderFactory
from backend.app.services.campaign_service import CampaignService
from backend.app.services.capability_service import CapabilityService
from backend.app.services.channel_service import ChannelService
from backend.app.services.content_service import ContentError, ContentService
from backend.app.services.destination_service import DestinationService
from backend.app.services.diagnostics_service import DiagnosticsService
from backend.app.services.donor_service import DonorService
from backend.app.services.invite_service import InviteService
from backend.app.services.permission_service import PermissionService
from backend.app.services.promotion_service import PromotionService
from backend.app.services.reaction_service import ReactionService
from backend.app.services.session_service import SessionProviderFactory, SessionService
from backend.app.services.update_service import UpdateService


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


def get_miniapp_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> MiniAppService:
    return MiniAppService(session, provider_factory=provider_factory)


def get_backup_service(session: AsyncSession = Depends(get_session)) -> BackupService:
    return BackupService(session)


def get_permission_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> PermissionService:
    return PermissionService(session, session_provider_factory=provider_factory)


def get_manager_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> ManagerBotService:
    return ManagerBotService(session, provider_factory=provider_factory)


def get_channel_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> ChannelService:
    return ChannelService(session, session_provider_factory=provider_factory)


def get_diagnostics_service(
    session: AsyncSession = Depends(get_session),
) -> DiagnosticsService:
    return DiagnosticsService(session)


def get_binding_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> BindingService:
    return BindingService(session, provider_factory=provider_factory)


def get_capability_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> CapabilityService:
    return CapabilityService(session, provider_factory=provider_factory)


def get_campaign_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> CampaignService:
    return CampaignService(session, provider_factory=provider_factory)


def get_donor_service(session: AsyncSession = Depends(get_session)) -> DonorService:
    return DonorService(session)


def get_destination_service(session: AsyncSession = Depends(get_session)) -> DestinationService:
    return DestinationService(session)


def get_promotion_service(session: AsyncSession = Depends(get_session)) -> PromotionService:
    return PromotionService(session)


def get_update_service(
    session: AsyncSession = Depends(get_session),
) -> UpdateService:
    return UpdateService(session)


async def get_content_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> ContentService:
    """Content Studio service wired to the account provider factory.

    The resolver builds a :class:`SessionProvider` for the account a source names
    (or the first enabled account), keeping Telethon out of the Content Service.
    """

    async def _resolve(account_id: str = ""):  # type: ignore[no-untyped-def]
        service = SessionService(session, provider_factory=provider_factory)
        account = await service.get(account_id) if account_id else None
        if account is None:
            accounts = await service.list_accounts(enabled=True)
            account = accounts[0] if accounts else None
        if account is None:
            raise ContentError(
                "Для этого источника нужен подключённый аккаунт Telegram.",
                how_to_fix="Добавьте аккаунт в разделе «Аккаунты».",
            )
        return await service.provider_for_with_proxy(account)

    return ContentService(session, resolve_provider=_resolve)
