"""Invite campaigns + donor analytics router (product slice).

* ``/campaigns`` — invite-link promotion that works **without a user session**.
* ``/donors``    — explainable source-quality indicators for scanned audience
  sources. Reports a probability band and confidence, never an invented number.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_campaign_service, get_donor_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.campaigns import (
    CampaignCreate,
    CampaignDetailOut,
    CampaignLinkIn,
    CampaignLinkOut,
    CampaignListOut,
    CampaignOut,
    CampaignStatusIn,
    DonorListOut,
    DonorMetricOut,
)
from backend.app.db.models.campaign import CampaignStatus
from backend.app.services.campaign_service import (
    RISK_MODE_TITLES,
    CampaignService,
    CampaignServiceError,
    CampaignSummary,
    LinkView,
)
from backend.app.services.donor_service import DonorService, metrics_to_dict

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _raise(exc: CampaignServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _summary_out(summary: CampaignSummary) -> CampaignOut:
    return CampaignOut(
        id=summary.id,
        name=summary.name,
        status=summary.status,
        channel_id=summary.channel_id,
        target_title=summary.target_title,
        risk_mode=summary.risk_mode,
        links_count=summary.links_count,
        joins_count=summary.joins_count,
        requests_count=summary.requests_count,
        conversion=summary.conversion,
        summary=summary.summary,
    )


def _link_out(link: LinkView) -> CampaignLinkOut:
    return CampaignLinkOut(
        id=link.id,
        label=link.label,
        link=link.link,
        status=link.status,
        join_request=link.join_request,
        member_limit=link.member_limit,
        joins_count=link.joins_count,
        requests_count=link.requests_count,
        last_error=link.last_error,
    )


def _parse_status(value: str) -> CampaignStatus:
    try:
        return CampaignStatus(value)
    except ValueError as exc:
        raise ApiError(
            422,
            "Неизвестное состояние кампании.",
            "Допустимо: draft, active, paused, completed, disabled.",
        ) from exc


@router.get("", response_model=CampaignListOut)
async def list_campaigns(
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignListOut:
    items = await service.list_campaigns()
    return CampaignListOut(
        items=[_summary_out(c) for c in items],
        total=len(items),
        risk_modes=dict(RISK_MODE_TITLES),
    )


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignOut:
    try:
        campaign = await service.create(
            payload.name,
            channel_id=payload.channel_id,
            target=payload.target,
            risk_mode=payload.risk_mode,
            requires_approval=payload.requires_approval,
            note=payload.note,
        )
    except CampaignServiceError as exc:
        _raise(exc)
        raise
    detail = await service.get_detail(campaign.id)
    return _summary_out(detail.campaign)


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def get_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignDetailOut:
    try:
        detail = await service.get_detail(campaign_id)
    except CampaignServiceError as exc:
        _raise(exc)
        raise
    return CampaignDetailOut(
        campaign=_summary_out(detail.campaign),
        links=[_link_out(link) for link in detail.links],
        requests_pending=detail.requests_pending,
        requests_approved=detail.requests_approved,
    )


@router.post("/{campaign_id}/status", response_model=CampaignOut)
async def set_campaign_status(
    campaign_id: str,
    payload: CampaignStatusIn,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignOut:
    try:
        await service.set_status(campaign_id, _parse_status(payload.status))
        detail = await service.get_detail(campaign_id)
    except CampaignServiceError as exc:
        _raise(exc)
        raise
    return _summary_out(detail.campaign)


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> dict[str, bool]:
    try:
        await service.delete(campaign_id)
    except CampaignServiceError as exc:
        _raise(exc)
        raise
    return {"deleted": True}


@router.post("/{campaign_id}/links", response_model=CampaignLinkOut, status_code=201)
async def add_link(
    campaign_id: str,
    payload: CampaignLinkIn,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignLinkOut:
    try:
        link = await service.add_link(
            campaign_id,
            label=payload.label,
            join_request=payload.join_request,
            member_limit=payload.member_limit,
        )
    except CampaignServiceError as exc:
        _raise(exc)
        raise
    detail = await service.get_detail(campaign_id)
    created = next((link_view for link_view in detail.links if link_view.id == link.id), None)
    return _link_out(created) if created else CampaignLinkOut(
        id=link.id, label=link.label, link=link.link, status=str(link.status)
    )


@router.post("/{campaign_id}/links/{link_id}/revoke", response_model=CampaignLinkOut)
async def revoke_link(
    campaign_id: str,
    link_id: str,
    service: CampaignService = Depends(get_campaign_service),
) -> CampaignLinkOut:
    try:
        link = await service.revoke_link(campaign_id, link_id)
    except CampaignServiceError as exc:
        _raise(exc)
        raise
    return CampaignLinkOut(
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


donors_router = APIRouter(prefix="/donors", tags=["donors"])


@donors_router.get("", response_model=DonorListOut)
async def list_donors(
    service: DonorService = Depends(get_donor_service),
) -> DonorListOut:
    rows = await service.list_metrics()
    return DonorListOut(
        items=[DonorMetricOut(**metrics_to_dict(row)) for row in rows],
        total=len(rows),
        note=(
            "Оценка основана на доступных данных. Если аккаунт не подключён, "
            "доля ботов не измеряется — показывается только уверенность."
        ),
    )


@donors_router.post("/analyze/{source_id}", response_model=DonorMetricOut)
async def analyze_donor(
    source_id: str,
    service: DonorService = Depends(get_donor_service),
) -> DonorMetricOut:
    try:
        row = await service.analyze(source_id)
    except ValueError as exc:
        raise ApiError(404, str(exc), "Выберите источник из списка.") from exc
    return DonorMetricOut(**metrics_to_dict(row))


@donors_router.post("/analyze", response_model=DonorListOut)
async def analyze_all_donors(
    service: DonorService = Depends(get_donor_service),
) -> DonorListOut:
    rows = await service.analyze_all()
    return DonorListOut(
        items=[DonorMetricOut(**metrics_to_dict(row)) for row in rows],
        total=len(rows),
    )
