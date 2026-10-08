"""Bot Factory router (v1.3: bulk managed-bot preparation).

Generate names/usernames, check availability with Telegram, create bots through
the official managed-bot flow (native or deep-link), register tokens and bind the
created bots to a channel. Nothing bypasses Telegram limits; nothing is created
without an explicit owner action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_bot_factory_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.bot_factory import (
    AdoptIn,
    BatchCreateIn,
    BatchDetailOut,
    BatchListOut,
    BatchOut,
    BindIn,
    BindManyIn,
    BindResultOut,
    CandidateOut,
    DashboardOut,
    TemplateOut,
    TokenRegisterOut,
)
from backend.app.services.bot_factory import (
    BOT_FACTORY_JOB_KIND,
    NAME_TEMPLATES,
    USERNAME_TEMPLATES,
    BotFactoryError,
    BotFactoryService,
)
from backend.app.services.queue_service import QueueService

router = APIRouter(prefix="/bot-factory", tags=["bot-factory"])


def _raise(exc: BotFactoryError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates() -> list[TemplateOut]:
    return [
        TemplateOut(
            key=key,
            name_template=NAME_TEMPLATES[key],
            username_template=USERNAME_TEMPLATES[key],
        )
        for key in NAME_TEMPLATES
    ]


@router.get("/batches", response_model=BatchListOut)
async def list_batches(
    limit: int = 100,
    offset: int = 0,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> BatchListOut:
    rows, total = await service.list_batches(limit=limit, offset=offset)
    return BatchListOut(
        items=[BatchOut(**service.batch_to_dict(b)) for b in rows], total=total
    )


@router.post("/batches", response_model=BatchDetailOut, status_code=201)
async def create_batch(
    payload: BatchCreateIn,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> BatchDetailOut:
    try:
        batch = await service.create_batch(
            title=payload.title,
            prefix=payload.prefix,
            topic=payload.topic,
            style=payload.style,
            count=payload.count,
            name_template=payload.name_template,
            username_template=payload.username_template,
            manager_bot_id=payload.manager_bot_id,
            account_id=payload.account_id,
            channel_id=payload.channel_id,
        )
    except BotFactoryError as exc:
        _raise(exc)
    candidates = await service.list_candidates(batch.id)
    return BatchDetailOut(
        batch=BatchOut(**service.batch_to_dict(batch)),
        candidates=[CandidateOut(**service.candidate_to_dict(c)) for c in candidates],
    )


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
async def get_batch(
    batch_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> BatchDetailOut:
    try:
        batch = await service.get_batch(batch_id)
    except BotFactoryError as exc:
        _raise(exc)
    candidates = await service.list_candidates(batch_id)
    return BatchDetailOut(
        batch=BatchOut(**service.batch_to_dict(batch)),
        candidates=[CandidateOut(**service.candidate_to_dict(c)) for c in candidates],
    )


@router.delete("/batches/{batch_id}", status_code=204)
async def delete_batch(
    batch_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> None:
    try:
        await service.delete_batch(batch_id)
    except BotFactoryError as exc:
        _raise(exc)


@router.post("/batches/{batch_id}/check", response_model=BatchDetailOut)
async def check_availability(
    batch_id: str,
    account_id: str = "",
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> BatchDetailOut:
    try:
        await service.check_availability(batch_id, account_id=account_id)
    except BotFactoryError as exc:
        _raise(exc)
    batch = await service.get_batch(batch_id)
    candidates = await service.list_candidates(batch_id)
    return BatchDetailOut(
        batch=BatchOut(**service.batch_to_dict(batch)),
        candidates=[CandidateOut(**service.candidate_to_dict(c)) for c in candidates],
    )


@router.post("/candidates/{candidate_id}/regenerate", response_model=CandidateOut)
async def regenerate_candidate(
    candidate_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> CandidateOut:
    try:
        row = await service.regenerate_candidate(candidate_id)
    except BotFactoryError as exc:
        _raise(exc)
    return CandidateOut(**service.candidate_to_dict(row))


@router.post("/batches/{batch_id}/create", response_model=BatchDetailOut)
async def create_bots(
    batch_id: str,
    via_deeplink: bool = False,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> BatchDetailOut:
    try:
        await service.create_batch_bots(batch_id, via_deeplink=via_deeplink)
    except BotFactoryError as exc:
        _raise(exc)
    batch = await service.get_batch(batch_id)
    candidates = await service.list_candidates(batch_id)
    return BatchDetailOut(
        batch=BatchOut(**service.batch_to_dict(batch)),
        candidates=[CandidateOut(**service.candidate_to_dict(c)) for c in candidates],
    )


@router.post("/batches/{batch_id}/adopt", response_model=CandidateOut)
async def adopt_created(
    batch_id: str,
    payload: AdoptIn,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> CandidateOut:
    try:
        row = await service.adopt_created(
            batch_id, payload.username, payload.telegram_id, title=payload.title
        )
    except BotFactoryError as exc:
        _raise(exc)
    return CandidateOut(**service.candidate_to_dict(row))


@router.post("/batches/{batch_id}/tokens", response_model=TokenRegisterOut)
async def register_tokens(
    batch_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> TokenRegisterOut:
    try:
        result = await service.register_tokens(batch_id)
    except BotFactoryError as exc:
        _raise(exc)
    return TokenRegisterOut(**result)


@router.post("/batches/{batch_id}/bind", response_model=list[BindResultOut])
async def bind_created(
    batch_id: str,
    payload: BindIn,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> list[BindResultOut]:
    try:
        results = await service.bind_created(
            batch_id, payload.channel_id, function=payload.function
        )
    except BotFactoryError as exc:
        _raise(exc)
    return [BindResultOut(**r) for r in results]


@router.post("/batches/{batch_id}/bind-many", response_model=list[BindResultOut])
async def bind_created_many(
    batch_id: str,
    payload: BindManyIn,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> list[BindResultOut]:
    """Connect every created bot of a batch to several channels (v2.0)."""
    try:
        results = await service.bind_created_many(
            batch_id, payload.channel_ids, function=payload.function
        )
    except BotFactoryError as exc:
        _raise(exc)
    return [BindResultOut(**r) for r in results]


@router.get("/batches/{batch_id}/dashboard", response_model=DashboardOut)
async def batch_dashboard(
    batch_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> DashboardOut:
    try:
        data = await service.dashboard(batch_id)
    except BotFactoryError as exc:
        _raise(exc)
    return DashboardOut(**data)


async def _detail(service: BotFactoryService, batch_id: str) -> BatchDetailOut:
    batch = await service.get_batch(batch_id)
    candidates = await service.list_candidates(batch_id)
    return BatchDetailOut(
        batch=BatchOut(**service.batch_to_dict(batch)),
        candidates=[CandidateOut(**service.candidate_to_dict(c)) for c in candidates],
    )


@router.post("/batches/{batch_id}/enqueue", response_model=BatchDetailOut)
async def enqueue_batch(
    batch_id: str,
    via_deeplink: bool = False,
    service: BotFactoryService = Depends(get_bot_factory_service),
) -> BatchDetailOut:
    """Queue every free candidate and hand the work to the durable scheduler.

    The queue is processed one operation per scheduler tick, so nothing blocks a
    request and a restart resumes the queue (D-109). Nothing is created here.
    """
    try:
        await service.enqueue_candidates(batch_id)
        batch = await service.get_batch(batch_id)
        progress = await service.queue_progress(batch_id)
        if progress["queued"] > 0:
            await QueueService(service.session).enqueue(
                kind=BOT_FACTORY_JOB_KIND,
                payload={"batch_id": batch.id, "via_deeplink": via_deeplink},
                group_key=batch.id,
                max_attempts=1,
            )
            await service.session.commit()
        return await _detail(service, batch_id)
    except BotFactoryError as exc:
        _raise(exc)


@router.post("/candidates/{candidate_id}/retry", response_model=CandidateOut)
async def retry_candidate(
    candidate_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> CandidateOut:
    try:
        row = await service.retry_candidate(candidate_id)
    except BotFactoryError as exc:
        _raise(exc)
    return CandidateOut(**service.candidate_to_dict(row))


@router.post("/candidates/{candidate_id}/skip", response_model=CandidateOut)
async def skip_candidate(
    candidate_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> CandidateOut:
    try:
        row = await service.skip_candidate(candidate_id)
    except BotFactoryError as exc:
        _raise(exc)
    return CandidateOut(**service.candidate_to_dict(row))


@router.post("/batches/{batch_id}/cancel", response_model=BatchDetailOut)
async def cancel_batch(
    batch_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> BatchDetailOut:
    try:
        await service.cancel_queue(batch_id)
        return await _detail(service, batch_id)
    except BotFactoryError as exc:
        _raise(exc)


@router.post("/batches/{batch_id}/resume", response_model=BatchDetailOut)
async def resume_batch(
    batch_id: str, service: BotFactoryService = Depends(get_bot_factory_service)
) -> BatchDetailOut:
    try:
        await service.resume_queue(batch_id)
        return await _detail(service, batch_id)
    except BotFactoryError as exc:
        _raise(exc)


__all__ = ["router"]
