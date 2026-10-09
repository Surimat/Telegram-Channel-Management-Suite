"""Bot onboarding router (v2.0: mass bot-to-channel connection).

Connect the bots created by the Bot Factory to a channel in bulk, using only
Telegram's official ``startchannel`` deep links and the existing BindingService
for the real rights verification. The durable queue advances one bot per
scheduler tick, so nothing silently succeeds and one failure never stops the rest.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_bot_onboarding_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.bot_onboarding import (
    OnboardingActionResultOut,
    OnboardingBatchDetailOut,
    OnboardingBatchListOut,
    OnboardingBatchOut,
    OnboardingCandidateOut,
    OnboardingCreateIn,
    OnboardingDashboardOut,
    RightsProfileOut,
)
from backend.app.services.bot_onboarding import (
    BOT_ONBOARDING_JOB_KIND,
    RIGHTS_PROFILES,
    BotOnboardingError,
    BotOnboardingService,
)
from backend.app.services.queue_service import QueueService

router = APIRouter(prefix="/bot-onboarding", tags=["bot-onboarding"])


def _raise(exc: BotOnboardingError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


async def _detail(service: BotOnboardingService, batch_id: str) -> OnboardingBatchDetailOut:
    batch = await service.get_batch(batch_id)
    candidates = await service.list_candidates(batch_id)
    return OnboardingBatchDetailOut(
        batch=OnboardingBatchOut(**service.batch_to_dict(batch)),
        candidates=[OnboardingCandidateOut(**service.candidate_to_dict(c)) for c in candidates],
    )


async def _ensure_job(service: BotOnboardingService, batch_id: str) -> None:
    """Hand a fresh queue to the durable scheduler (one op per tick)."""
    progress = await service.queue_progress(batch_id)
    if progress.active > 0 and not progress.paused:
        await QueueService(service.session).enqueue(
            kind=BOT_ONBOARDING_JOB_KIND,
            payload={"batch_id": batch_id},
            group_key=batch_id,
            max_attempts=1,
        )
        await service.session.commit()


@router.get("/rights-profiles", response_model=list[RightsProfileOut])
async def rights_profiles() -> list[RightsProfileOut]:
    """Minimal, purpose-named rights profiles (never a blanket "all rights")."""
    return [
        RightsProfileOut(
            key=p.key,
            title_ru=p.title_ru,
            title_en=p.title_en,
            function=p.function,
            admin_rights=list(p.admin_rights),
            description_ru=p.description_ru,
            description_en=p.description_en,
        )
        for p in RIGHTS_PROFILES
    ]


@router.get("/batches", response_model=OnboardingBatchListOut)
async def list_batches(
    limit: int = 100,
    offset: int = 0,
    service: BotOnboardingService = Depends(get_bot_onboarding_service),
) -> OnboardingBatchListOut:
    rows, total = await service.list_batches(limit=limit, offset=offset)
    return OnboardingBatchListOut(
        items=[OnboardingBatchOut(**service.batch_to_dict(b)) for b in rows], total=total
    )


@router.post("/batches", response_model=OnboardingBatchDetailOut, status_code=201)
async def create_batch(
    payload: OnboardingCreateIn,
    service: BotOnboardingService = Depends(get_bot_onboarding_service),
) -> OnboardingBatchDetailOut:
    """Create the onboarding queue and hand it to the durable scheduler."""
    try:
        batch = await service.create_batch(
            bot_ids=payload.bot_ids,
            channel_id=payload.channel_id,
            rights_profile=payload.rights_profile,
        )
    except BotOnboardingError as exc:
        _raise(exc)
    await _ensure_job(service, batch.id)
    return await _detail(service, batch.id)


@router.get("/batches/{batch_id}", response_model=OnboardingBatchDetailOut)
async def get_batch(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    try:
        return await _detail(service, batch_id)
    except BotOnboardingError as exc:
        _raise(exc)


@router.delete("/batches/{batch_id}", status_code=204)
async def delete_batch(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> None:
    try:
        await service.delete_batch(batch_id)
    except BotOnboardingError as exc:
        _raise(exc)


@router.get("/batches/{batch_id}/dashboard", response_model=OnboardingDashboardOut)
async def batch_dashboard(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingDashboardOut:
    try:
        batch = await service.get_batch(batch_id)
        progress = await service.queue_progress(batch_id)
    except BotOnboardingError as exc:
        _raise(exc)
    return OnboardingDashboardOut(**service.dashboard(batch, progress))


@router.post("/batches/{batch_id}/next", response_model=OnboardingBatchDetailOut)
async def next_bot(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    """Advance the queue by one bot right now ("Следующий бот")."""
    try:
        await service.get_batch(batch_id)
        await service.run_queue_once(batch_id)
    except BotOnboardingError as exc:
        _raise(exc)
    await _ensure_job(service, batch_id)
    return await _detail(service, batch_id)


@router.post("/batches/{batch_id}/verify", response_model=OnboardingBatchDetailOut)
async def verify_all(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    """Re-check every bot in the queue against Telegram ("Проверить подключение")."""
    try:
        rows = await service.list_candidates(batch_id)
        for row in rows:
            if row.status != "skipped":
                await service.verify_candidate(row.id)
    except BotOnboardingError as exc:
        _raise(exc)
    await _ensure_job(service, batch_id)
    return await _detail(service, batch_id)


@router.post("/batches/{batch_id}/retry", response_model=OnboardingBatchDetailOut)
async def retry_failed(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    """Re-queue every failed bot in the batch ("Повторить ошибку")."""
    try:
        rows = await service.list_candidates(batch_id)
        for row in rows:
            if row.status == "failed":
                await service.retry_candidate(row.id)
    except BotOnboardingError as exc:
        _raise(exc)
    await _ensure_job(service, batch_id)
    return await _detail(service, batch_id)


@router.post("/batches/{batch_id}/skip", response_model=OnboardingBatchDetailOut)
async def skip_remaining(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    """Skip every bot still waiting in the batch."""
    try:
        rows = await service.list_candidates(batch_id)
        for row in rows:
            if row.status in {"queued", "waiting_confirmation", "verifying", "failed"}:
                await service.skip_candidate(row.id)
    except BotOnboardingError as exc:
        _raise(exc)
    return await _detail(service, batch_id)


@router.post("/batches/{batch_id}/pause", response_model=OnboardingBatchDetailOut)
async def pause_batch(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    try:
        await service.pause(batch_id)
    except BotOnboardingError as exc:
        _raise(exc)
    return await _detail(service, batch_id)


@router.post("/batches/{batch_id}/resume", response_model=OnboardingBatchDetailOut)
async def resume_batch(
    batch_id: str, service: BotOnboardingService = Depends(get_bot_onboarding_service)
) -> OnboardingBatchDetailOut:
    try:
        await service.resume(batch_id)
    except BotOnboardingError as exc:
        _raise(exc)
    await _ensure_job(service, batch_id)
    return await _detail(service, batch_id)


@router.post("/candidates/{candidate_id}/retry", response_model=OnboardingActionResultOut)
async def retry_candidate(
    candidate_id: str,
    service: BotOnboardingService = Depends(get_bot_onboarding_service),
) -> OnboardingActionResultOut:
    try:
        row = await service.retry_candidate(candidate_id)
    except BotOnboardingError as exc:
        _raise(exc)
    return OnboardingActionResultOut(**service.result_dict(row))


@router.post("/candidates/{candidate_id}/skip", response_model=OnboardingActionResultOut)
async def skip_candidate(
    candidate_id: str,
    service: BotOnboardingService = Depends(get_bot_onboarding_service),
) -> OnboardingActionResultOut:
    try:
        row = await service.skip_candidate(candidate_id)
    except BotOnboardingError as exc:
        _raise(exc)
    return OnboardingActionResultOut(**service.result_dict(row))


@router.post("/candidates/{candidate_id}/verify", response_model=OnboardingActionResultOut)
async def verify_candidate(
    candidate_id: str,
    service: BotOnboardingService = Depends(get_bot_onboarding_service),
) -> OnboardingActionResultOut:
    """Re-check one bot's real rights against Telegram ("Проверить подключение")."""
    try:
        result = await service.verify_candidate(candidate_id)
    except BotOnboardingError as exc:
        _raise(exc)
    return OnboardingActionResultOut(
        candidate_id=result.candidate_id,
        bot_id=result.bot_id,
        bot_username=result.bot_username,
        status=result.status,
        status_label=result.status_label,
        binding_id=result.binding_id,
        deep_link=result.deep_link,
        error=result.error,
    )


__all__ = ["router"]
