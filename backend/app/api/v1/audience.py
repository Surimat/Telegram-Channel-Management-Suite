"""Audience router (PHASE 5).

Vertical slice: sources → scan → audience DB → dedup → tags → search → export →
dashboard. All endpoints return friendly RU errors and never expose secrets or
unmasked PII. Scanning is durable: ``start`` enqueues a job, the scheduler runs it
and this router exposes progress and lifecycle controls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_audience_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.audience import (
    AudienceDashboardOut,
    ExportIn,
    ExportOut,
    ExportPreviewOut,
    FilterPresetOut,
    ImportIn,
    ImportOut,
    ScanPreviewOut,
    ScanResultOut,
    SourceCheckOut,
    SourceCreateIn,
    SourceListOut,
    SourceOut,
    SourceUpdateIn,
    StatusBulkIn,
    TagOut,
    TagRenameIn,
    TagsBulkIn,
    UserDetailOut,
    UserListOut,
    UserOut,
)
from backend.app.db.models.audience import MemberStatus, ScanStatus
from backend.app.services.audience_service import (
    AudienceService,
    AudienceServiceError,
    ScanBatchOutcome,
)

router = APIRouter(prefix="/audience", tags=["audience"])


def _raise(exc: AudienceServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _source_out(source) -> SourceOut:  # type: ignore[no-untyped-def]
    return SourceOut(
        id=source.id,
        title=source.title,
        username=source.username,
        telegram_id=source.telegram_id,
        source_type=source.source_type.value,
        reference=source.reference,
        enabled=source.enabled,
        account_id=source.account_id,
        scan_status=source.scan_status.value,
        completeness=source.completeness.value,
        last_scan_at=source.last_scan_at,
        last_scan_finished_at=source.last_scan_finished_at,
        discovered_count=source.discovered_count,
        imported_count=source.imported_count,
        new_count=source.new_count,
        duplicate_count=source.duplicate_count,
        error_count=source.error_count,
        reported_total=source.reported_total,
        scanned_offset=source.scanned_offset,
        scan_job_id=source.scan_job_id,
        last_error=source.last_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _user_out(user, *, tags: list[str]) -> UserOut:  # type: ignore[no-untyped-def]
    return UserOut(
        id=user.id,
        telegram_user_id=user.telegram_user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=user.display_name,
        phone_masked=user.phone_masked,
        is_bot=user.is_bot,
        is_deleted=user.is_deleted,
        is_premium=user.is_premium,
        status=user.status.value,
        score=user.score,
        score_reason=user.score_reason,
        tags=tags,
        first_seen_at=user.first_seen_at,
        last_seen_at=user.last_seen_at,
        invite_status=user.invite_status,
        invite_attempts=user.invite_attempts,
        last_invite_at=user.last_invite_at,
        last_invite_error=user.last_invite_error,
    )


def _scan_result(
    source, outcome: ScanBatchOutcome | None, service: AudienceService
) -> ScanResultOut:
    return ScanResultOut(
        source_id=source.id,
        scan_status=source.scan_status.value,
        completeness=source.completeness.value,
        discovered=source.discovered_count,
        new=source.new_count,
        duplicates=source.duplicate_count,
        errors=source.error_count,
        reported_total=source.reported_total,
        offset=source.scanned_offset,
        explanation=service.explain_scan_result(source),
        completed=source.scan_status
        in {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED},
    )


# --- Dashboard ---------------------------------------------------------------
@router.get("/dashboard", response_model=AudienceDashboardOut)
async def audience_dashboard(
    service: AudienceService = Depends(get_audience_service),
) -> AudienceDashboardOut:
    return AudienceDashboardOut(**await service.dashboard())


@router.get("/filters/presets", response_model=list[FilterPresetOut])
async def filter_presets(
    service: AudienceService = Depends(get_audience_service),
) -> list[FilterPresetOut]:
    return [FilterPresetOut(**p) for p in service.filter_presets()]


# --- Sources -----------------------------------------------------------------
@router.get("/sources", response_model=SourceListOut)
async def list_sources(
    enabled: bool | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AudienceService = Depends(get_audience_service),
) -> SourceListOut:
    scan_status = ScanStatus(status) if status else None
    rows, total = await service.list_sources(
        enabled=enabled, status=scan_status, search=search, limit=limit, offset=offset
    )
    return SourceListOut(
        items=[_source_out(s) for s in rows], total=total, limit=limit, offset=offset
    )


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create_source(
    payload: SourceCreateIn, service: AudienceService = Depends(get_audience_service)
) -> SourceOut:
    try:
        source = await service.add_source(
            reference=payload.reference,
            title=payload.title,
            source_type=payload.source_type,
            account_id=payload.account_id,
        )
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return _source_out(source)


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> SourceOut:
    source = await service.get_source(source_id)
    if source is None:
        raise ApiError(404, "Источник не найден.", "Обновите список источников.")
    return _source_out(source)


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: str,
    payload: SourceUpdateIn,
    service: AudienceService = Depends(get_audience_service),
) -> SourceOut:
    try:
        source = await service.update_source(
            source_id, **payload.model_dump(exclude_none=True)
        )
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return _source_out(source)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> None:
    try:
        await service.delete_source(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()


@router.post("/sources/{source_id}/check", response_model=SourceCheckOut)
async def check_source(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> SourceCheckOut:
    try:
        result = await service.check_source(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return SourceCheckOut(**result)


@router.post("/sources/{source_id}/scan/preview", response_model=ScanPreviewOut)
async def preview_scan(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> ScanPreviewOut:
    try:
        preview = await service.preview_scan(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    return ScanPreviewOut(
        source_id=preview.source_id,
        title=preview.title,
        username=preview.username,
        source_type=preview.source_type,
        reference=preview.reference,
        account_id=preview.account_id,
        account_label=preview.account_label,
        mode=preview.mode,
        batch_size=preview.batch_size,
        chunk_size=preview.chunk_size,
        estimated_total=preview.estimated_total,
        filters=preview.filters,
        notes=preview.notes,
    )


@router.post("/sources/{source_id}/scan", response_model=ScanResultOut)
async def start_scan(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> ScanResultOut:
    try:
        await service.start_scan(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    source = await service.get_source(source_id)
    return _scan_result(source, None, service)


@router.get("/sources/{source_id}/scan/progress", response_model=ScanResultOut)
async def scan_progress(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> ScanResultOut:
    source = await service.get_source(source_id)
    if source is None:
        raise ApiError(404, "Источник не найден.", "Обновите список источников.")
    return _scan_result(source, None, service)


@router.post("/sources/{source_id}/scan/pause", response_model=ScanResultOut)
async def pause_scan(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> ScanResultOut:
    try:
        source = await service.pause_scan(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return _scan_result(source, None, service)


@router.post("/sources/{source_id}/scan/resume", response_model=ScanResultOut)
async def resume_scan(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> ScanResultOut:
    try:
        source = await service.resume_scan(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return _scan_result(source, None, service)


@router.post("/sources/{source_id}/scan/cancel", response_model=ScanResultOut)
async def cancel_scan(
    source_id: str, service: AudienceService = Depends(get_audience_service)
) -> ScanResultOut:
    try:
        source = await service.cancel_scan(source_id)
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return _scan_result(source, None, service)


# --- Users -------------------------------------------------------------------
@router.get("/users", response_model=UserListOut)
async def list_users(
    search: str = Query(default=""),
    source_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    status: str | None = Query(default=None),
    is_bot: bool | None = Query(default=None),
    is_deleted: bool | None = Query(default=None),
    has_username: bool | None = Query(default=None),
    is_premium: bool | None = Query(default=None),
    telegram_user_id: int | None = Query(default=None),
    sort: str = Query(default="last_seen"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: AudienceService = Depends(get_audience_service),
) -> UserListOut:
    member_status = MemberStatus(status) if status else None
    rows, total = await service.list_users(
        search=search,
        source_id=source_id,
        tag=tag,
        status=member_status,
        is_bot=is_bot,
        is_deleted=is_deleted,
        has_username=has_username,
        is_premium=is_premium,
        telegram_user_id=telegram_user_id,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    import json as _json

    items = []
    for u in rows:
        try:
            tags = _json.loads(u.tags or "[]")
        except ValueError:
            tags = []
        items.append(_user_out(u, tags=tags))
    return UserListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def get_user(
    user_id: str, service: AudienceService = Depends(get_audience_service)
) -> UserDetailOut:
    user = await service.get_user(user_id)
    if user is None:
        raise ApiError(404, "Пользователь не найден.", "Обновите список.")
    import json as _json

    try:
        tags = _json.loads(user.tags or "[]")
    except ValueError:
        tags = []
    base = _user_out(user, tags=tags)
    return UserDetailOut(
        **base.model_dump(),
        sources=await service.sources_of_user(user.id),
        score_components=service.score_components(user),
    )


# --- Tags --------------------------------------------------------------------
@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    service: AudienceService = Depends(get_audience_service),
) -> list[TagOut]:
    return [TagOut(**t) for t in await service.list_tags()]


@router.post("/tags/assign", response_model=dict)
async def assign_tags(
    payload: TagsBulkIn, service: AudienceService = Depends(get_audience_service)
) -> dict:
    updated = await service.add_tags(payload.user_ids, payload.tags)
    await service.session.commit()
    return {"updated": updated}


@router.post("/tags/remove", response_model=dict)
async def remove_tags(
    payload: TagsBulkIn, service: AudienceService = Depends(get_audience_service)
) -> dict:
    updated = await service.remove_tags(payload.user_ids, payload.tags)
    await service.session.commit()
    return {"updated": updated}


@router.post("/tags/rename", response_model=dict)
async def rename_tag(
    payload: TagRenameIn, service: AudienceService = Depends(get_audience_service)
) -> dict:
    updated = await service.rename_tag(payload.old, payload.new)
    await service.session.commit()
    return {"updated": updated}


@router.delete("/tags/{tag}", response_model=dict)
async def delete_tag(
    tag: str, service: AudienceService = Depends(get_audience_service)
) -> dict:
    updated = await service.delete_tag(tag)
    await service.session.commit()
    return {"updated": updated}


# --- Bulk status -------------------------------------------------------------
@router.post("/users/bulk-status", response_model=dict)
async def bulk_status(
    payload: StatusBulkIn, service: AudienceService = Depends(get_audience_service)
) -> dict:
    try:
        status = MemberStatus(payload.status)
    except ValueError:
        raise ApiError(400, "Неизвестный статус.", "Выберите статус из списка.") from None
    updated = await service.bulk_status(payload.user_ids, status)
    await service.session.commit()
    return {"updated": updated}


# --- Export / import ---------------------------------------------------------
@router.post("/export/preview", response_model=ExportPreviewOut)
async def export_preview(
    payload: ExportIn, service: AudienceService = Depends(get_audience_service)
) -> ExportPreviewOut:
    fields = service.export_fields(include_pii=payload.include_pii)
    _, total = await service.list_users(
        source_id=payload.source_id, tag=payload.tag, limit=1, offset=0
    )
    count = min(total, payload.limit) if payload.limit else total
    note = (
        "Файл сохраняется локально в папку exports и никуда не отправляется."
    )
    if payload.include_pii:
        note += " Включены персональные данные (телефон в маскированном виде)."
    return ExportPreviewOut(
        count=count,
        fields=fields,
        includes_pii=payload.include_pii,
        destination=str(service.settings.resolve_exports_dir()),
        note=note,
    )


@router.post("/export", response_model=ExportOut)
async def export_audience(
    payload: ExportIn, service: AudienceService = Depends(get_audience_service)
) -> ExportOut:
    try:
        result = await service.export_audience(
            fmt=payload.format,
            source_id=payload.source_id,
            tag=payload.tag,
            include_pii=payload.include_pii,
            limit=payload.limit,
        )
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return ExportOut(
        filename=result.filename,
        path=result.path,
        format=result.format,
        fields=result.fields,
        includes_pii=result.includes_pii,
        row_count=result.row_count,
        size_bytes=result.size_bytes,
    )


@router.post("/import", response_model=ImportOut)
async def import_audience(
    payload: ImportIn, service: AudienceService = Depends(get_audience_service)
) -> ImportOut:
    try:
        result = await service.import_audience(
            data=payload.data, fmt=payload.format, source_id=payload.source_id
        )
    except AudienceServiceError as exc:
        _raise(exc)
    await service.session.commit()
    return ImportOut(**result)


__all__ = ["router"]
