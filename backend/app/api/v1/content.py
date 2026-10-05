"""Content Studio router (v1.2: Контент).

Sources (Telegram/RSS/Atom/manual), grabbing, items, cleaning, rewrite and the
content dashboard. Nothing here bypasses a source's protection or Telegram
limits; a protected source keeps only its link.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_content_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.content import (
    ApplyCleanIn,
    CleanPreviewOut,
    ContentDashboardOut,
    ContentItemListOut,
    ContentItemOut,
    ContentItemUpdateIn,
    ContentSourceIn,
    ContentSourceListOut,
    ContentSourceOut,
    GrabOut,
    RewriteIn,
    RewriteOut,
    RightsOut,
)
from backend.app.db.models.content import (
    RIGHTS_TITLES,
    STATUS_TITLES,
    ContentItem,
    ContentSource,
    ContentSourceKind,
    ContentSourceStatus,
)
from backend.app.services.content_rewrite import MODE_TITLES
from backend.app.services.content_service import ContentError, ContentService

router = APIRouter(prefix="/content", tags=["content"])

SOURCE_KIND_TITLES = {
    ContentSourceKind.TELEGRAM: "Telegram-канал",
    ContentSourceKind.RSS: "RSS",
    ContentSourceKind.ATOM: "Atom",
    ContentSourceKind.MANUAL: "Вручную / публичная ссылка",
}
SOURCE_STATUS_TITLES = {
    ContentSourceStatus.IDLE: "Не запускался",
    ContentSourceStatus.OK: "Работает",
    ContentSourceStatus.ERROR: "Ошибка",
    ContentSourceStatus.PROTECTED: "Защищён от копирования",
}


def _raise(exc: ContentError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _source_out(source: ContentSource) -> ContentSourceOut:
    return ContentSourceOut(
        id=source.id,
        kind=source.kind.value,
        kind_title=SOURCE_KIND_TITLES.get(source.kind, source.kind.value),
        title=source.title,
        reference=source.reference,
        enabled=source.enabled,
        channel_id=source.channel_id,
        status=source.status.value,
        status_title=SOURCE_STATUS_TITLES.get(source.status, source.status.value),
        last_error=source.last_error,
        last_fetch=source.last_fetch.isoformat() if source.last_fetch else "",
        last_fetch_new=source.last_fetch_new,
        etag=source.etag,
        last_modified=source.last_modified,
        last_seen_item=source.last_seen_item,
    )


def _item_out(service: ContentService, item: ContentItem) -> ContentItemOut:
    return ContentItemOut(
        id=item.id,
        title=item.title,
        text=item.text,
        cleaned_text=item.cleaned_text,
        entities=_json_list(item.entities),
        buttons=_json_list(item.buttons),
        status=item.status.value,
        status_title=STATUS_TITLES.get(item.status, item.status.value),
        mode=item.mode,
        source_id=item.source_id,
        source_message_id=item.source_message_id,
        source_url=item.source_url,
        source_channel=item.source_channel,
        source_author=item.source_author,
        imported_at=item.imported_at.isoformat() if item.imported_at else "",
        rights_status=item.rights_status.value,
        rights_title=RIGHTS_TITLES.get(item.rights_status, item.rights_status.value),
        attribution_enabled=item.attribution_enabled,
        protected=item.protected,
        content_hash=item.content_hash,
        language=item.language,
        note=item.note,
        scheduled_at=item.scheduled_at.isoformat() if item.scheduled_at else "",
        rights_warning=service.rights_warning(item),
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


def _json_list(raw: str) -> list[dict[str, object]]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


@router.get("/providers")
async def provider_status(
    service: ContentService = Depends(get_content_service),
) -> list[dict[str, object]]:
    return service.provider_status()


@router.get("/sources", response_model=ContentSourceListOut)
async def list_sources(
    service: ContentService = Depends(get_content_service),
) -> ContentSourceListOut:
    sources = await service.list_sources()
    return ContentSourceListOut(
        items=[_source_out(s) for s in sources],
        providers=service.provider_status(),
    )


@router.post("/sources", response_model=ContentSourceOut, status_code=201)
async def create_source(
    payload: ContentSourceIn,
    service: ContentService = Depends(get_content_service),
) -> ContentSourceOut:
    try:
        source = await service.create_source(
            kind=payload.kind,
            reference=payload.reference,
            title=payload.title,
            enabled=payload.enabled,
            channel_id=payload.channel_id,
            account_id=payload.account_id,
        )
    except ContentError as exc:
        _raise(exc)
    return _source_out(source)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str, service: ContentService = Depends(get_content_service)
) -> None:
    try:
        await service.delete_source(source_id)
    except ContentError as exc:
        _raise(exc)


@router.post("/sources/{source_id}/grab", response_model=GrabOut)
async def grab_source(
    source_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    service: ContentService = Depends(get_content_service),
) -> GrabOut:
    try:
        outcome = await service.grab(source_id, limit=limit)
    except ContentError as exc:
        _raise(exc)
    return GrabOut(
        source_id=outcome.source_id,
        ok=outcome.ok,
        new_items=outcome.new_items,
        duplicates=outcome.duplicates,
        protected=outcome.protected,
        message=outcome.message,
        how_to_fix=outcome.how_to_fix,
        item_ids=list(outcome.item_ids or []),
    )


@router.get("/items", response_model=ContentItemListOut)
async def list_items(
    status: str | None = None,
    source_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: ContentService = Depends(get_content_service),
) -> ContentItemListOut:
    try:
        items, total = await service.list_items(
            status=status, source_id=source_id, limit=limit, offset=offset
        )
    except ContentError as exc:
        _raise(exc)
    return ContentItemListOut(
        items=[_item_out(service, i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/items/{item_id}", response_model=ContentItemOut)
async def get_item(
    item_id: str, service: ContentService = Depends(get_content_service)
) -> ContentItemOut:
    try:
        item = await service.get_item(item_id)
    except ContentError as exc:
        _raise(exc)
    return _item_out(service, item)


@router.patch("/items/{item_id}", response_model=ContentItemOut)
async def update_item(
    item_id: str,
    payload: ContentItemUpdateIn,
    service: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    try:
        item = await service.update_item(item_id, **payload.model_dump(exclude_unset=True))
    except ContentError as exc:
        _raise(exc)
    return _item_out(service, item)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: str, service: ContentService = Depends(get_content_service)
) -> None:
    try:
        await service.delete_item(item_id)
    except ContentError as exc:
        _raise(exc)


@router.get("/items/{item_id}/clean", response_model=CleanPreviewOut)
async def clean_preview(
    item_id: str, service: ContentService = Depends(get_content_service)
) -> CleanPreviewOut:
    try:
        result = await service.clean_preview(item_id)
    except ContentError as exc:
        _raise(exc)
    return CleanPreviewOut(
        original=result.original,
        cleaned=result.cleaned,
        changed=result.changed,
        changes=[
            {"rule": c.rule, "title": c.title, "detail": c.detail} for c in result.changes
        ],
        removed_lines=result.removed_lines,
    )


@router.post("/items/{item_id}/clean", response_model=ContentItemOut)
async def apply_clean(
    item_id: str,
    payload: ApplyCleanIn,
    service: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    try:
        item = await service.apply_clean(item_id, cleaned=payload.cleaned)
    except ContentError as exc:
        _raise(exc)
    return _item_out(service, item)


@router.post("/items/{item_id}/clean/revert", response_model=ContentItemOut)
async def revert_clean(
    item_id: str, service: ContentService = Depends(get_content_service)
) -> ContentItemOut:
    try:
        item = await service.revert_clean(item_id)
    except ContentError as exc:
        _raise(exc)
    return _item_out(service, item)


@router.post("/items/{item_id}/rewrite", response_model=RewriteOut)
async def rewrite_item(
    item_id: str,
    payload: RewriteIn,
    service: ContentService = Depends(get_content_service),
) -> RewriteOut:
    try:
        result = await service.rewrite_preview(item_id, mode=payload.mode)
    except ContentError as exc:
        _raise(exc)
    return RewriteOut(
        ok=result.ok,
        text=result.text,
        mode=result.mode,
        mode_title=MODE_TITLES.get(result.mode, result.mode),
        message=result.message,
        how_to_fix=result.how_to_fix,
        used_model=result.used_model,
    )


@router.post("/items/{item_id}/rewrite/apply", response_model=ContentItemOut)
async def apply_rewrite(
    item_id: str,
    payload: RewriteIn,
    service: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    try:
        item, result = await service.apply_rewrite(item_id, mode=payload.mode)
    except ContentError as exc:
        _raise(exc)
    if not result.ok and result.mode != "none":
        raise ApiError(409, result.message, result.how_to_fix)
    return _item_out(service, item)


@router.get("/items/{item_id}/rights", response_model=RightsOut)
async def item_rights(
    item_id: str, service: ContentService = Depends(get_content_service)
) -> RightsOut:
    try:
        item = await service.get_item(item_id)
    except ContentError as exc:
        _raise(exc)
    return RightsOut(
        rights_status=item.rights_status.value,
        rights_title=RIGHTS_TITLES.get(item.rights_status, item.rights_status.value),
        attribution_block=service.attribution_block(item),
        warning=service.rights_warning(item),
    )


@router.get("/dashboard", response_model=ContentDashboardOut)
async def dashboard(
    service: ContentService = Depends(get_content_service),
) -> ContentDashboardOut:
    data = await service.dashboard()
    return ContentDashboardOut(**data)  # type: ignore[arg-type]


__all__ = ["router"]
