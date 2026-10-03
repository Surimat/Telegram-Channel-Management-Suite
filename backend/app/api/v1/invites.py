"""Invites router (PHASE 6).

Vertical slice: preview (dry-run) → create draft → confirm & start → monitor →
pause/resume/stop/retry. All endpoints return friendly RU errors (never a stack
trace) and never expose secrets. The confirmation step is mandatory before a run
starts (docs/SECURITY.md §7).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_invite_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.invites import (
    InviteJobCreateIn,
    InviteJobListOut,
    InviteJobOut,
    InvitePreviewIn,
    InvitePreviewOut,
    InviteSummaryOut,
    InviteTaskListOut,
    InviteTaskOut,
)
from backend.app.db.models.invite import InviteJobStatus, InviteStatus
from backend.app.services.invite_service import InviteService, InviteServiceError

router = APIRouter(prefix="/invites", tags=["invites"])


def _raise(exc: InviteServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _json_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _json_obj(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _job_out(service: InviteService, job) -> InviteJobOut:  # type: ignore[no-untyped-def]
    return InviteJobOut(
        id=job.id,
        name=job.name,
        target=job.target,
        target_title=job.target_title,
        channel_id=getattr(job, "channel_id", "") or "",
        status=job.status.value,
        dry_run=job.dry_run,
        confirmed_at=job.confirmed_at,
        account_ids=_json_list(job.account_ids),
        source_ids=_json_list(job.source_ids),
        filters=_json_obj(job.filters),
        total_tasks=job.total_tasks,
        processed_count=job.processed_count,
        invited_count=job.invited_count,
        already_count=job.already_count,
        privacy_count=job.privacy_count,
        flood_count=job.flood_count,
        error_count=job.error_count,
        waiting_account_id=job.waiting_account_id,
        wait_until=job.wait_until,
        started_at=job.started_at,
        finished_at=job.finished_at,
        last_error=job.last_error,
        explanation=service.explain_job(job),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/preview", response_model=InvitePreviewOut)
async def preview(
    payload: InvitePreviewIn,
    service: InviteService = Depends(get_invite_service),
) -> InvitePreviewOut:
    try:
        result = await service.preview(
            target=payload.target,
            channel_id=payload.channel_id,
            account_ids=payload.account_ids,
            source_ids=payload.source_ids,
            filters=payload.filters,
            max_total=payload.max_total,
            sample_limit=payload.sample_limit,
        )
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover - _raise always raises
    return InvitePreviewOut(**result)


@router.get("/summary", response_model=InviteSummaryOut)
async def summary(
    service: InviteService = Depends(get_invite_service),
) -> InviteSummaryOut:
    return InviteSummaryOut(**await service.summary())


@router.get("", response_model=InviteJobListOut)
async def list_jobs(
    status: str | None = Query(default=None),
    search: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: InviteService = Depends(get_invite_service),
) -> InviteJobListOut:
    status_enum = None
    if status:
        try:
            status_enum = InviteJobStatus(status)
        except ValueError:
            raise ApiError(400, "Неизвестный статус задания.") from None
    jobs, total = await service.jobs.list(
        status=status_enum, search=search, limit=limit, offset=offset
    )
    return InviteJobListOut(
        items=[_job_out(service, j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=InviteJobOut, status_code=201)
async def create_job(
    payload: InviteJobCreateIn,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    try:
        job = await service.create_job(
            name=payload.name,
            target=payload.target,
            channel_id=payload.channel_id,
            account_ids=payload.account_ids,
            source_ids=payload.source_ids,
            filters=payload.filters,
            dry_run=payload.dry_run,
            per_account_delay_min=payload.per_account_delay_min,
            per_account_delay_max=payload.per_account_delay_max,
            max_per_account=payload.max_per_account,
            max_total=payload.max_total,
        )
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover
    await service.session.commit()
    return _job_out(service, job)


@router.get("/{job_id}", response_model=InviteJobOut)
async def get_job(
    job_id: str,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    job = await service.jobs.get(job_id)
    if job is None:
        raise ApiError(404, "Задание приглашения не найдено.")
    return _job_out(service, job)


@router.post("/{job_id}/confirm", response_model=InviteJobOut)
async def confirm_job(
    job_id: str,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    try:
        job = await service.confirm_and_start(job_id)
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover
    await service.session.commit()
    return _job_out(service, job)


@router.post("/{job_id}/pause", response_model=InviteJobOut)
async def pause_job(
    job_id: str,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    try:
        job = await service.pause_job(job_id)
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover
    await service.session.commit()
    return _job_out(service, job)


@router.post("/{job_id}/resume", response_model=InviteJobOut)
async def resume_job(
    job_id: str,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    try:
        job = await service.resume_job(job_id)
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover
    await service.session.commit()
    return _job_out(service, job)


@router.post("/{job_id}/stop", response_model=InviteJobOut)
async def stop_job(
    job_id: str,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    try:
        job = await service.stop_job(job_id)
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover
    await service.session.commit()
    return _job_out(service, job)


@router.post("/{job_id}/retry", response_model=InviteJobOut)
async def retry_job(
    job_id: str,
    service: InviteService = Depends(get_invite_service),
) -> InviteJobOut:
    try:
        job = await service.retry_failed(job_id)
    except InviteServiceError as exc:
        _raise(exc)
        raise  # pragma: no cover
    await service.session.commit()
    return _job_out(service, job)


@router.get("/{job_id}/tasks", response_model=InviteTaskListOut)
async def list_tasks(
    job_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: InviteService = Depends(get_invite_service),
) -> InviteTaskListOut:
    status_enum = None
    if status:
        try:
            status_enum = InviteStatus(status)
        except ValueError:
            raise ApiError(400, "Неизвестный статус задачи.") from None
    tasks, total = await service.tasks.list_for_job(
        job_id, status=status_enum, limit=limit, offset=offset
    )
    counts = await service.tasks.status_counts(job_id)
    return InviteTaskListOut(
        items=[InviteTaskOut.model_validate(t) for t in tasks],
        total=total,
        limit=limit,
        offset=offset,
        status_counts=counts,
    )
