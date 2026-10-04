"""Invite-link campaign service (product slice: no-session promotion).

When the owner has no user account, the Invite Manager still works through
**promotion via invite links** — all through the official Bot API. This service:

* creates named invite links (optionally join-request links) with a bound bot;
* pauses/revokes links;
* records join requests and reports conversion honestly (joins/requests, never
  invented "clicks");
* applies a conservative pacing *preference* per risk mode — never a bypass of
  Telegram's own limits.

The direct (account-based) invite path stays in :mod:`invite_service`; this is
the additive, no-session companion.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.models.binding import FUNCTION_REACTIONS
from backend.app.db.models.bot import Bot, BotKind
from backend.app.db.models.campaign import (
    CampaignStatus,
    InviteCampaign,
    InviteLink,
    JoinRequest,
    JoinRequestStatus,
    LinkStatus,
)
from backend.app.db.repositories.bindings import BindingRepository
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.campaigns import CampaignRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.events_service import EventsService

ProviderFactory = Callable[..., TelegramBotProvider]

#: Risk modes are *pacing preferences*, not permission bypasses.
RISK_MODES = ("conservative", "standard", "manual")

RISK_MODE_TITLES = {
    "conservative": "Осторожный (минимум ссылок, максимум пауз)",
    "standard": "Обычный",
    "manual": "Ручной (ссылки создаются по одной)",
}


class CampaignServiceError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class CampaignSummary:
    id: str
    name: str
    status: str
    channel_id: str
    target_title: str
    risk_mode: str
    links_count: int
    joins_count: int
    requests_count: int
    conversion: float | None
    summary: str = ""


@dataclass(slots=True)
class LinkView:
    id: str
    label: str
    link: str
    status: str
    join_request: bool
    member_limit: int
    joins_count: int
    requests_count: int
    last_error: str = ""


@dataclass(slots=True)
class CampaignDetail:
    campaign: CampaignSummary
    links: list[LinkView] = field(default_factory=list)
    requests_pending: int = 0
    requests_approved: int = 0


class CampaignService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = CampaignRepository(session)
        self.bindings = BindingRepository(session)
        self.bots = BotRepository(session)
        self.channels = ChannelRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory

    # --- inventory -----------------------------------------------------------
    async def list_campaigns(self) -> list[CampaignSummary]:
        rows, _ = await self.repo.list()
        return [self._summary(c) for c in rows]

    async def get_detail(self, campaign_id: str) -> CampaignDetail:
        campaign = await self._require(campaign_id)
        links = await self.repo.list_links(campaign_id)
        counts = await self.repo.count_requests(campaign_id)
        return CampaignDetail(
            campaign=self._summary(campaign),
            links=[self._link_view(link) for link in links],
            requests_pending=counts.get(JoinRequestStatus.PENDING.value, 0),
            requests_approved=counts.get(JoinRequestStatus.APPROVED.value, 0),
        )

    # --- create / update -----------------------------------------------------
    async def create(
        self,
        name: str,
        *,
        channel_id: str = "",
        target: str = "",
        risk_mode: str = "standard",
        requires_approval: bool = False,
        note: str = "",
    ) -> InviteCampaign:
        name = (name or "").strip()
        if not name:
            raise CampaignServiceError(
                "Укажите название кампании.",
                how_to_fix="Например: «Приглашения из обсуждений».",
            )
        channel = await self.channels.get(channel_id) if channel_id else None
        if channel_id and channel is None:
            raise CampaignServiceError("Канал не найден.", status_code=404)
        campaign = InviteCampaign(
            name=name,
            channel_id=channel_id,
            target=(channel.reference if channel else target.strip()),
            target_title=(channel.title if channel else ""),
            status=CampaignStatus.DRAFT,
            risk_mode=risk_mode if risk_mode in RISK_MODES else "standard",
            requires_approval=requires_approval,
            note=note.strip(),
        )
        await self.repo.add(campaign)
        await self.events.info(
            "campaigns",
            f"Кампания приглашений создана: {name}.",
            explanation="Теперь создайте ссылку-приглашение.",
            operation="campaign.create",
            status="ok",
        )
        await self.session.commit()
        return campaign

    async def set_status(self, campaign_id: str, status: CampaignStatus) -> InviteCampaign:
        campaign = await self._require(campaign_id)
        campaign.status = status
        await self.session.flush()
        await self.session.commit()
        return campaign

    async def delete(self, campaign_id: str) -> None:
        campaign = await self._require(campaign_id)
        await self.repo.delete(campaign)
        await self.session.commit()

    # --- links ---------------------------------------------------------------
    async def add_link(
        self,
        campaign_id: str,
        *,
        label: str = "",
        join_request: bool = False,
        member_limit: int = 0,
    ) -> InviteLink:
        campaign = await self._require(campaign_id)
        if not campaign.channel_id:
            raise CampaignServiceError(
                "У кампании не выбран канал.",
                how_to_fix="Выберите канал из реестра, чтобы создать ссылку.",
            )
        provider, bot = await self._link_provider(campaign.channel_id)
        if provider is None:
            raise CampaignServiceError(
                "Нет бота, который может создать ссылку.",
                how_to_fix=(
                    "Подключите бота к каналу (раздел «Боты» → «Подключить бота к каналу») "
                    "или настройте управляющего бота."
                ),
            )
        target: int | str = campaign.channel_id
        channel = await self.channels.get(campaign.channel_id)
        if channel is not None:
            target = channel.telegram_id or channel.reference or campaign.channel_id
        try:
            result = await provider.create_invite_link(
                target,
                name=label or campaign.name,
                join_request=join_request or campaign.requires_approval,
                member_limit=member_limit,
            )
        except TelegramProviderError as exc:
            raise CampaignServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.close()
        if not result.ok:
            raise CampaignServiceError(result.message, how_to_fix=result.how_to_fix)

        link = InviteLink(
            campaign_id=campaign_id,
            label=(label or campaign.name).strip(),
            link=result.link,
            status=LinkStatus.ACTIVE,
            join_request=result.join_request,
            member_limit=result.member_limit,
        )
        await self.repo.add_link(link)
        campaign.links_count = await self.repo.count_links(campaign_id)
        if campaign.status is CampaignStatus.DRAFT:
            campaign.status = CampaignStatus.ACTIVE
        await self.session.flush()
        await self.events.info(
            "campaigns",
            "Ссылка-приглашение создана.",
            operation="campaign.add_link",
            status="ok",
            details=f"campaign={campaign_id}; bot=@{bot.username}" if bot else "",
        )
        await self.session.commit()
        return link

    async def revoke_link(self, campaign_id: str, link_id: str) -> InviteLink:
        campaign = await self._require(campaign_id)
        link = await self.repo.get_link(link_id)
        if link is None or link.campaign_id != campaign_id:
            raise CampaignServiceError("Ссылка не найдена.", status_code=404)
        provider, _bot = await self._link_provider(campaign.channel_id)
        if provider is not None:
            target: int | str = campaign.channel_id
            channel = await self.channels.get(campaign.channel_id)
            if channel is not None:
                target = channel.telegram_id or channel.reference or campaign.channel_id
            try:
                await provider.revoke_invite_link(target, link.link)
            except TelegramProviderError:
                # Best-effort: mark it revoked locally anyway; Telegram may have
                # already expired it. The user is told the local state changed.
                pass
            finally:
                await provider.close()
        link.status = LinkStatus.REVOKED
        await self.session.flush()
        await self.session.commit()
        return link

    # --- join requests -------------------------------------------------------
    async def record_join_request(
        self, campaign_id: str, request: JoinRequest
    ) -> JoinRequest:
        """Store a join request observed by the manager bot runtime."""
        await self.repo.add_request(request)
        campaign = await self.repo.get(campaign_id)
        if campaign is not None:
            campaign.requests_count += 1
        await self.session.flush()
        return request

    async def resolve_join_request(
        self, request_id: str, status: JoinRequestStatus
    ) -> JoinRequest:
        request = await self.session.get(JoinRequest, request_id)
        if request is None:
            raise CampaignServiceError("Заявка не найдена.", status_code=404)
        from backend.app.db.base import utcnow

        request.status = status
        request.resolved_at = utcnow()
        await self.session.flush()
        await self.session.commit()
        return request

    # --- provider helpers ----------------------------------------------------
    async def _link_provider(
        self, channel_id: str
    ) -> tuple[TelegramBotProvider | None, Bot | None]:
        """Return a bot provider able to create links for the channel."""
        for binding in await self.bindings.list_for_channel(
            channel_id, function=FUNCTION_REACTIONS
        ):
            bot = await self.bots.get(binding.bot_id)
            provider = self._provider_or_none(bot)
            if provider is not None:
                return provider, bot
        # Fall back to the manager bot (it can manage links in channels it admins).
        manager = await self.bots.get_manager()
        provider = self._provider_or_none(manager)
        if provider is not None:
            return provider, manager
        return None, None

    def _provider_or_none(self, bot: Bot | None) -> TelegramBotProvider | None:
        if bot is None or not bot.token_encrypted:
            return None
        try:
            token = open_secret(bot.token_encrypted, self.settings)
        except ValueError:
            return None
        return self._provider_factory(
            token, provider_name=bot.provider_name, settings=self.settings
        )

    # --- helpers -------------------------------------------------------------
    async def _require(self, campaign_id: str) -> InviteCampaign:
        campaign = await self.repo.get(campaign_id)
        if campaign is None:
            raise CampaignServiceError("Кампания не найдена.", status_code=404)
        return campaign

    def _summary(self, campaign: InviteCampaign) -> CampaignSummary:
        joins = campaign.joins_count
        requests = campaign.requests_count
        conversion = None
        if requests:
            conversion = round(joins / requests, 4)
        return CampaignSummary(
            id=campaign.id,
            name=campaign.name,
            status=str(campaign.status),
            channel_id=campaign.channel_id,
            target_title=campaign.target_title or campaign.target,
            risk_mode=campaign.risk_mode,
            links_count=campaign.links_count,
            joins_count=joins,
            requests_count=requests,
            conversion=conversion,
            summary=self._summary_text(campaign),
        )

    @staticmethod
    def _summary_text(campaign: InviteCampaign) -> str:
        if campaign.links_count == 0:
            return "Ссылок пока нет. Создайте ссылку-приглашение."
        parts = [f"Ссылок: {campaign.links_count}."]
        if campaign.joins_count:
            parts.append(f"Присоединились: {campaign.joins_count}.")
        if campaign.requests_count:
            parts.append(f"Заявок на вступление: {campaign.requests_count}.")
        if campaign.requests_count and campaign.joins_count:
            percent = round(campaign.joins_count / campaign.requests_count * 100)
            parts.append(f"Одобрено примерно {percent}%.")
        if campaign.joins_count == 0 and campaign.requests_count == 0:
            parts.append("Присоединений пока не зафиксировано.")
        return " ".join(parts)

    def _link_view(self, link: InviteLink) -> LinkView:
        return LinkView(
            id=link.id,
            label=link.label,
            link=link.link,
            status=str(link.status),
            join_request=link.join_request,
            member_limit=link.member_limit,
            joins_count=link.joins_count,
            requests_count=link.requests_count,
            last_error=link.last_error,
        )


def manager_bot_is_set(bot: Bot | None) -> bool:
    return bot is not None and bot.kind is BotKind.MANAGER


__all__ = [
    "RISK_MODES",
    "RISK_MODE_TITLES",
    "CampaignDetail",
    "CampaignService",
    "CampaignServiceError",
    "CampaignSummary",
    "LinkView",
]
