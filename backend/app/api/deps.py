"""Reusable FastAPI dependencies.

Services are constructed per request from a DB session plus injectable
collaborators (e.g. the Telegram provider factory). Tests override
:func:`get_provider_factory` to run the whole stack against the fake provider.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.db.session import get_session
from backend.app.manager.service import ManagerBotService
from backend.app.mesh.service import MeshService
from backend.app.miniapp.service import MiniAppService
from backend.app.providers.registry import build_bot_provider, build_session_provider
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.audience_service import AudienceService
from backend.app.services.backup_service import BackupService
from backend.app.services.binding_service import BindingService
from backend.app.services.bot_factory import BotFactoryService
from backend.app.services.bot_service import BotService, ProviderFactory
from backend.app.services.campaign_service import CampaignService
from backend.app.services.capability_service import CapabilityService
from backend.app.services.channel_service import ChannelService
from backend.app.services.consistency import ConsistencyAuditor
from backend.app.services.content_service import ContentError, ContentService
from backend.app.services.destination_service import DestinationService
from backend.app.services.diagnostics_service import DiagnosticsService
from backend.app.services.donor_service import DonorService
from backend.app.services.editorial_service import EditorialService
from backend.app.services.invite_service import InviteService
from backend.app.services.notification_service import NotificationCenterService
from backend.app.services.permission_service import PermissionService
from backend.app.services.posting_service import PostingService
from backend.app.services.promotion_service import PromotionService
from backend.app.services.reaction_service import ReactionService
from backend.app.services.session_service import SessionProviderFactory, SessionService
from backend.app.services.settings_service import SettingsService
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


def get_bot_factory_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
    session_provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> BotFactoryService:
    """Bot Factory wired to bot + user-session provider factories.

    The internal Bot/Binding services reuse the overridable factories so tests
    run the whole creation flow against the deterministic fakes (D-001).
    """
    return BotFactoryService(
        session,
        session_provider_factory=session_provider_factory,
        bot_service=BotService(session, provider_factory=provider_factory),
        binding_service=BindingService(session, provider_factory=provider_factory),
    )


def get_mesh_service(
    session: AsyncSession = Depends(get_session),
) -> MeshService:
    """LAN Mesh service. Tests may override to inject an in-memory transport."""
    return MeshService(session)


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


async def get_editorial_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> EditorialService:
    """Editorial Workspace wired to the bot provider and the Content Studio.

    Publishing an approved item reuses the existing posting service: the handler
    resolves the item's planned publication (or plans one) and publishes it, so
    the editorial queue and Content Studio never diverge.
    """
    from backend.app.services.posting_service import PostingService, TargetSpec

    async def _publish(content_item_id: str, channel_id: str) -> tuple[bool, str]:
        if not content_item_id:
            return False, "Материал не связан с контентом."
        posting = PostingService(session)
        pubs = await posting.publications.list_for_item(content_item_id)
        target = next((p for p in pubs if not channel_id or p.channel_id == channel_id), None)
        if target is None:
            if not channel_id:
                return False, "Не выбран канал для публикации."
            created = await posting.plan(
                content_item_id, [TargetSpec(channel_id=channel_id)]
            )
            target = created[0] if created else None
        if target is None:
            return False, "Не удалось создать публикацию."
        outcome = await posting.publish(target.id)
        return outcome.ok, outcome.message

    return EditorialService(
        session, provider_factory=provider_factory, publish_handler=_publish
    )


async def get_notification_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
) -> NotificationCenterService:
    """Notification Center wired to the manager (or a dedicated) notification bot.

    The owner DM and the notification group reuse the manager bot by default; a
    dedicated notification bot can be selected via the ``notification_bot_id``
    setting. Both paths share the same bus and the same service.
    """
    from backend.app.core.security import open_secret
    from backend.app.db.repositories.bots import BotRepository

    async def _provider_for_bot():  # type: ignore[no-untyped-def]
        settings = get_settings()
        bots = BotRepository(session)
        bot = None
        chosen = await SettingsService(session).get_typed("notification_bot_id", "")
        if chosen:
            bot = await bots.get(str(chosen))
        if bot is None or not bot.has_token:
            bot = await bots.get_manager()
        if bot is None or not bot.enabled or not bot.token_encrypted:
            return None
        try:
            token = open_secret(bot.token_encrypted, settings)
        except ValueError:
            return None
        return provider_factory(token, provider_name=bot.provider_name, settings=settings)

    return NotificationCenterService(
        session,
        resolve_owner_provider=_provider_for_bot,
        resolve_group_provider=_provider_for_bot,
    )


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


async def get_posting_service(
    session: AsyncSession = Depends(get_session),
    provider_factory: ProviderFactory = Depends(get_provider_factory),
    session_provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> PostingService:
    """Posting service wired to bot + user posting providers.

    Bot posting prefers a binding Telegram verified for the ``posting``
    function; it falls back to the channel's enabled bots (legacy channels) and,
    only if the caller asks, to a user account (expanded mode).
    """
    from backend.app.providers.posting import BotPostingProvider, UserPostingProvider

    async def _resolve_bot(channel_id: str):  # type: ignore[no-untyped-def]
        bot_service = BotService(session, provider_factory=provider_factory)
        binding_service = BindingService(session, provider_factory=provider_factory)
        bot = None
        bindings = await binding_service.list_bindings(channel_id=channel_id)
        ready = [
            b
            for b in bindings
            if str(getattr(b.status, "value", b.status)) == "ready"
            and b.function in ("posting", "reactions")
        ]
        note = "Публикация через проверенного бота канала."
        if ready:
            bot = await bot_service.get(ready[0].bot_id)
        if bot is None or not bot.has_token:
            bots = await bot_service.list_bots(enabled=True)
            bot = next((b for b in bots if b.has_token), None)
            note = "Публикация через бота (проверьте права в канале)."
        if bot is None:
            return None, ""
        return BotPostingProvider(bot_service.provider_for(bot)), note

    async def _resolve_user(channel_id: str):  # type: ignore[no-untyped-def]
        service = SessionService(session, provider_factory=session_provider_factory)
        accounts = await service.list_accounts(enabled=True)
        account = accounts[0] if accounts else None
        if account is None:
            return None, ""
        provider = await service.provider_for_with_proxy(account)
        return UserPostingProvider(provider), account.id

    return PostingService(
        session,
        resolve_bot_provider=_resolve_bot,
        resolve_user_provider=_resolve_user,
    )


def get_consistency_auditor(
    session: AsyncSession = Depends(get_session),
) -> ConsistencyAuditor:
    """Consistency Auditor for the "Проверка целостности" panel."""
    return ConsistencyAuditor(session)
