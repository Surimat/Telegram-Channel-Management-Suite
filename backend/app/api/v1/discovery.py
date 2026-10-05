"""Donor discovery router (v1.1: automated donor search).

Search, list, compare and explicitly add candidates to audience sources. Nothing
is added automatically; nothing bypasses Telegram limits.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_session_provider_factory
from backend.app.api.errors import ApiError
from backend.app.api.schemas.discovery import (
    AddToSourcesOut,
    CandidateListOut,
    CompareIn,
    CompareOut,
    DiscoverQueryIn,
    DiscoveryResultOut,
    DonorCandidateOut,
)
from backend.app.db.session import get_session
from backend.app.providers.discovery_base import DiscoveryQuery
from backend.app.services.donor_discovery_service import (
    DonorDiscoveryService,
    candidate_to_dict,
)
from backend.app.services.session_service import SessionProviderFactory

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _service(
    session: AsyncSession,
    provider_factory: SessionProviderFactory,
) -> DonorDiscoveryService:
    return DonorDiscoveryService(session, session_provider_factory=provider_factory)


def _candidate(data: dict[str, object]) -> DonorCandidateOut:
    return DonorCandidateOut(**data)  # type: ignore[arg-type]


@router.get("/providers")
async def provider_status(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
):
    service = _service(session, provider_factory)
    return service.provider_status()


@router.post("/search", response_model=DiscoveryResultOut)
async def search(
    payload: DiscoverQueryIn,
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> DiscoveryResultOut:
    query = DiscoveryQuery(
        topic=payload.topic,
        keywords=payload.keywords,
        language=payload.language,
        min_subscribers=payload.min_subscribers,
        max_subscribers=payload.max_subscribers,
        active_only=payload.active_only,
        period_days=payload.period_days,
        seed_channel=payload.seed_channel,
    )
    if not query.text() and not query.seed_channel:
        raise ApiError(
            400,
            "Укажите тему или ключевые слова.",
            "Например: «новости». Можно также выбрать свой канал для рекомендаций.",
        )
    service = _service(session, provider_factory)
    result = await service.discover(
        query, providers=payload.providers or None, account_id=payload.account_id or None
    )
    return DiscoveryResultOut(
        query=str(result["query"]),
        stored=int(result["stored"]),  # type: ignore[arg-type]
        providers=result["providers"],  # type: ignore[arg-type]
        candidates=[_candidate(c) for c in result["candidates"]],  # type: ignore[arg-type]
    )


@router.get("/candidates", response_model=CandidateListOut)
async def list_candidates(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> CandidateListOut:
    service = _service(session, provider_factory)
    rows = await service.list_candidates()
    return CandidateListOut(
        items=[_candidate(candidate_to_dict(r)) for r in rows],
        providers=service.provider_status(),  # type: ignore[arg-type]
    )


@router.post("/compare", response_model=CompareOut)
async def compare(
    payload: CompareIn,
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> CompareOut:
    service = _service(session, provider_factory)
    try:
        result = await service.compare(payload.candidate_ids)
    except ValueError as exc:
        raise ApiError(400, str(exc), "Выберите от 2 до 10 кандидатов.") from exc
    return CompareOut(
        items=[_candidate(c) for c in result["items"]],  # type: ignore[arg-type]
        best_id=str(result["best_id"]),
        best_title=str(result["best_title"]),
        best_reason=str(result["best_reason"]),
    )


@router.post("/candidates/{candidate_id}/add", response_model=AddToSourcesOut)
async def add_to_sources(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> AddToSourcesOut:
    service = _service(session, provider_factory)
    try:
        candidate = await service.add_to_sources(candidate_id)
    except ValueError as exc:
        raise ApiError(404, str(exc), "Обновите список кандидатов.") from exc
    return AddToSourcesOut(
        candidate=_candidate(candidate_to_dict(candidate)),
        source_id=candidate.added_source_id,
    )


@router.post("/candidates/clear")
async def clear_candidates(
    session: AsyncSession = Depends(get_session),
    provider_factory: SessionProviderFactory = Depends(get_session_provider_factory),
) -> dict[str, int]:
    service = _service(session, provider_factory)
    return {"deleted": await service.clear()}


__all__ = ["router"]
