"""Repository for invite-link campaigns, links and join requests."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.campaign import (
    InviteCampaign,
    InviteLink,
    JoinRequest,
    JoinRequestStatus,
)


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- campaigns -----------------------------------------------------------
    async def add(self, campaign: InviteCampaign) -> InviteCampaign:
        self.session.add(campaign)
        await self.session.flush()
        return campaign

    async def get(self, campaign_id: str) -> InviteCampaign | None:
        return await self.session.get(InviteCampaign, campaign_id)

    async def list(
        self, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[InviteCampaign], int]:
        stmt = (
            select(InviteCampaign)
            .order_by(InviteCampaign.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count = select(func.count()).select_from(InviteCampaign)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count)).scalar_one())
        return rows, total

    async def delete(self, campaign: InviteCampaign) -> None:
        # Remove dependent links and requests first (no FK cascade in SQLite).
        for link in await self.list_links(campaign.id):
            await self.session.delete(link)
        for request in await self.list_requests(campaign.id):
            await self.session.delete(request)
        await self.session.delete(campaign)
        await self.session.flush()

    # --- links ---------------------------------------------------------------
    async def add_link(self, link: InviteLink) -> InviteLink:
        self.session.add(link)
        await self.session.flush()
        return link

    async def get_link(self, link_id: str) -> InviteLink | None:
        return await self.session.get(InviteLink, link_id)

    async def list_links(self, campaign_id: str) -> list[InviteLink]:
        stmt = (
            select(InviteLink)
            .where(InviteLink.campaign_id == campaign_id)
            .order_by(InviteLink.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_links(self, campaign_id: str) -> int:
        stmt = select(func.count()).select_from(InviteLink).where(
            InviteLink.campaign_id == campaign_id
        )
        return int((await self.session.execute(stmt)).scalar_one())

    # --- join requests -------------------------------------------------------
    async def add_request(self, request: JoinRequest) -> JoinRequest:
        self.session.add(request)
        await self.session.flush()
        return request

    async def list_requests(
        self, campaign_id: str, *, status: JoinRequestStatus | None = None
    ) -> list[JoinRequest]:
        stmt = select(JoinRequest).where(JoinRequest.campaign_id == campaign_id)
        if status is not None:
            stmt = stmt.where(JoinRequest.status == status)
        stmt = stmt.order_by(JoinRequest.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_requests(self, campaign_id: str) -> dict[str, int]:
        stmt = (
            select(JoinRequest.status, func.count())
            .where(JoinRequest.campaign_id == campaign_id)
            .group_by(JoinRequest.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}
