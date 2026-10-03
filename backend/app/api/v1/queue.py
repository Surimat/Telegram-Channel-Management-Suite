"""Queue router: inspect and manage durable jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.common import Page
from backend.app.api.schemas.jobs import JobOut
from backend.app.db.models.job import JobStatus
from backend.app.db.session import get_session
from backend.app.services.queue_service import QueueService

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("", response_model=Page[JobOut])
async def list_jobs(
    status: JobStatus | None = None,
    kind: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> Page[JobOut]:
    service = QueueService(session)
    offset = (page - 1) * page_size
    rows, total = await service.list(status=status, kind=kind, limit=page_size, offset=offset)
    return Page[JobOut](
        items=[JobOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: str, session: AsyncSession = Depends(get_session)) -> JobOut:
    service = QueueService(session)
    job = await service.retry(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    await session.commit()
    return JobOut.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, session: AsyncSession = Depends(get_session)) -> JobOut:
    service = QueueService(session)
    job = await service.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задание не найдено.")
    await session.commit()
    return JobOut.model_validate(job)
