"""Content Studio router (v1.2: Контент).

Sources (Telegram/RSS/Atom/manual), grabbing, items, cleaning, rewrite and the
content dashboard. Nothing here bypasses a source's protection or Telegram
limits; a protected source keeps only its link.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import (
    get_ai_profile_service,
    get_automation_rule_service,
    get_content_pipeline_service,
    get_content_service,
    get_posting_service,
)
from backend.app.api.errors import ApiError
from backend.app.api.schemas.content import (
    AiProcessIn,
    AiProfileIn,
    AiProfileOut,
    AiProfileUpdateIn,
    ApplyCleanIn,
    AutomationRuleIn,
    AutomationRuleOut,
    AutomationRuleUpdateIn,
    ButtonSetIn,
    ButtonSetOut,
    CalendarOut,
    CleanPreviewOut,
    ContentDashboardOut,
    ContentItemListOut,
    ContentItemOut,
    ContentItemUpdateIn,
    ContentSourceIn,
    ContentSourceListOut,
    ContentSourceOut,
    GrabOut,
    ModerationDecisionIn,
    ModerationIn,
    ModerationOut,
    PipelineAnalyticsOut,
    PipelineRecordOut,
    PlanIn,
    PlanOut,
    PreviewOut,
    PublicationOut,
    PublishOut,
    RewriteIn,
    RewriteOut,
    RightsOut,
    ScheduleIn,
    TickOut,
    ValidationOut,
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
from backend.app.services.posting_service import (
    PostingError,
    PostingService,
    TargetSpec,
)

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


def _raise_posting(exc: PostingError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(400, "Некорректная дата.", "Используйте формат ISO 8601.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


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
        blocked_keywords=_json_str_list(source.blocked_keywords),
        quiet_hours_enabled=source.quiet_hours_enabled,
        quiet_hours_start=source.quiet_hours_start,
        quiet_hours_end=source.quiet_hours_end,
        quiet_hours_tz=source.quiet_hours_tz,
    )


def _publication_out(pub: object) -> PublicationOut:
    ids = _json_int_list(getattr(pub, "telegram_message_ids", "[]"))
    status = str(getattr(getattr(pub, "status", ""), "value", getattr(pub, "status", "")))
    from backend.app.services.posting_service import _PUBLICATION_TITLES

    status_enum = getattr(pub, "status", "")
    return PublicationOut(
        id=str(getattr(pub, "id", "")),
        item_id=str(getattr(pub, "item_id", "")),
        channel_id=str(getattr(pub, "channel_id", "")),
        channel_username=str(getattr(pub, "channel_username", "")),
        status=status,
        status_title=_PUBLICATION_TITLES.get(status_enum, status),
        scheduled_at=_iso(getattr(pub, "scheduled_at", None)),
        published_at=_iso(getattr(pub, "published_at", None)),
        delete_at=_iso(getattr(pub, "delete_at", None)),
        telegram_message_ids=ids,
        error=str(getattr(pub, "error", "")),
        attempts=int(getattr(pub, "attempts", 0) or 0),
        profile_key=str(getattr(pub, "profile_key", "")),
        comment_status=str(getattr(pub, "comment_status", "")),
        delete_status=str(getattr(pub, "delete_status", "")),
    )


def _iso(value: object) -> str:
    return value.isoformat() if value else ""  # type: ignore[union-attr]


def _json_str_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _json_int_list(raw: str) -> list[int]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return [int(v) for v in value if str(v).lstrip("-").isdigit()]
    return []


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
        held=item.held,
        moderation_note=item.moderation_note,
        original_text=item.original_text,
        ai_status=item.ai_status,
        ai_category=item.ai_category,
        ai_intent=item.ai_intent,
        ai_profile=item.ai_profile,
        ai_note=item.ai_note,
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
        blocked=outcome.blocked,
        held=outcome.held,
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


# --- moderation (v1.2) -----------------------------------------------------


@router.get("/sources/{source_id}/moderation", response_model=ModerationOut)
async def get_moderation(
    source_id: str,
    service: ContentService = Depends(get_content_service),
) -> ModerationOut:
    source = await service.sources.get(source_id)
    if source is None:
        raise ApiError(404, "Источник не найден.")
    return ModerationOut(
        source_id=source.id,
        blocked_keywords=_json_str_list(source.blocked_keywords),
        quiet_hours_enabled=source.quiet_hours_enabled,
        quiet_hours_start=source.quiet_hours_start,
        quiet_hours_end=source.quiet_hours_end,
        quiet_hours_tz=source.quiet_hours_tz,
    )


@router.put("/sources/{source_id}/moderation", response_model=ModerationOut)
async def set_moderation(
    source_id: str,
    payload: ModerationIn,
    service: ContentService = Depends(get_content_service),
) -> ModerationOut:
    try:
        source = await service.set_moderation(
            source_id,
            blocked_keywords=payload.blocked_keywords,
            quiet_hours_enabled=payload.quiet_hours_enabled,
            quiet_hours_start=payload.quiet_hours_start,
            quiet_hours_end=payload.quiet_hours_end,
            quiet_hours_tz=payload.quiet_hours_tz,
        )
    except ContentError as exc:
        _raise(exc)
    return ModerationOut(
        source_id=source.id,
        blocked_keywords=_json_str_list(source.blocked_keywords),
        quiet_hours_enabled=source.quiet_hours_enabled,
        quiet_hours_start=source.quiet_hours_start,
        quiet_hours_end=source.quiet_hours_end,
        quiet_hours_tz=source.quiet_hours_tz,
    )


@router.post("/items/{item_id}/release", response_model=ContentItemOut)
async def release_item(
    item_id: str,
    service: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    try:
        item = await service.release_held(item_id)
    except ContentError as exc:
        _raise(exc)
    return _item_out(service, item)


# --- posting / calendar / buttons / preview (v1.2) -------------------------


@router.post("/items/{item_id}/plan", response_model=PlanOut)
async def plan_item(
    item_id: str,
    payload: PlanIn,
    service: PostingService = Depends(get_posting_service),
) -> PlanOut:
    targets = [
        TargetSpec(
            channel_id=t.channel_id,
            scheduled_at=_parse_dt(t.scheduled_at),
            text_override=t.text_override,
            profile_key=t.profile_key,
            ai_instructions=t.ai_instructions,
        )
        for t in payload.targets
    ]
    try:
        publications = await service.plan(item_id, targets, mode=payload.mode)
    except PostingError as exc:
        _raise_posting(exc)
    return PlanOut(publications=[_publication_out(p) for p in publications])


@router.get("/items/{item_id}/publications", response_model=PlanOut)
async def list_publications(
    item_id: str,
    service: PostingService = Depends(get_posting_service),
) -> PlanOut:
    rows = await service.publications.list_for_item(item_id)
    return PlanOut(publications=[_publication_out(p) for p in rows])


@router.post("/publications/{publication_id}/schedule", response_model=PublicationOut)
async def schedule_publication(
    publication_id: str,
    payload: ScheduleIn,
    service: PostingService = Depends(get_posting_service),
) -> PublicationOut:
    try:
        pub = await service.schedule(publication_id, _parse_dt(payload.scheduled_at))
    except PostingError as exc:
        _raise_posting(exc)
    return _publication_out(pub)


@router.post("/publications/{publication_id}/cancel", response_model=PublicationOut)
async def cancel_publication(
    publication_id: str,
    service: PostingService = Depends(get_posting_service),
) -> PublicationOut:
    try:
        pub = await service.cancel(publication_id)
    except PostingError as exc:
        _raise_posting(exc)
    return _publication_out(pub)


@router.post("/publications/{publication_id}/publish", response_model=PublishOut)
async def publish_publication(
    publication_id: str,
    force: bool = Query(False),
    service: PostingService = Depends(get_posting_service),
) -> PublishOut:
    outcome = await service.publish(publication_id, force=force)
    return PublishOut(
        publication_id=outcome.publication_id,
        ok=outcome.ok,
        status=outcome.status,
        message_ids=outcome.message_ids,
        message=outcome.message,
        how_to_fix=outcome.how_to_fix,
        uncertain=outcome.uncertain,
    )


@router.post("/publications/{publication_id}/retry", response_model=PublishOut)
async def retry_publication(
    publication_id: str,
    service: PostingService = Depends(get_posting_service),
) -> PublishOut:
    outcome = await service.retry(publication_id)
    return PublishOut(
        publication_id=outcome.publication_id,
        ok=outcome.ok,
        status=outcome.status,
        message_ids=outcome.message_ids,
        message=outcome.message,
        how_to_fix=outcome.how_to_fix,
        uncertain=outcome.uncertain,
    )


@router.get("/calendar", response_model=CalendarOut)
async def calendar(
    start: str | None = Query(None),
    end: str | None = Query(None),
    service: PostingService = Depends(get_posting_service),
) -> CalendarOut:
    from datetime import timedelta

    now = datetime.now(UTC)
    start_dt = _parse_dt(start) or (now - timedelta(days=7))
    end_dt = _parse_dt(end) or (now + timedelta(days=30))
    data = await service.calendar(start_dt, end_dt)
    return CalendarOut(**data)  # type: ignore[arg-type]


@router.put("/items/{item_id}/buttons", response_model=ButtonSetOut)
async def set_buttons(
    item_id: str,
    payload: ButtonSetIn,
    service: PostingService = Depends(get_posting_service),
) -> ButtonSetOut:
    rows = [[b.model_dump() for b in row] for row in payload.rows]
    try:
        record = await service.set_buttons(item_id, rows)
    except PostingError as exc:
        _raise_posting(exc)
    return ButtonSetOut(
        item_id=record.item_id,
        rows=_buttons_rows(record.rows),
        enabled=record.enabled,
    )


@router.get("/items/{item_id}/buttons", response_model=ButtonSetOut)
async def get_buttons(
    item_id: str,
    service: PostingService = Depends(get_posting_service),
) -> ButtonSetOut:
    record = await service.buttons.for_item(item_id)
    return ButtonSetOut(
        item_id=item_id,
        rows=_buttons_rows(record.rows if record else "[]"),
        enabled=record.enabled if record else True,
    )


@router.get("/items/{item_id}/validate", response_model=ValidationOut)
async def validate_item(
    item_id: str,
    channel_id: str = Query(""),
    service: PostingService = Depends(get_posting_service),
) -> ValidationOut:
    data = await service.validate(item_id, channel_id)
    return ValidationOut(**data)  # type: ignore[arg-type]


@router.get("/items/{item_id}/preview", response_model=PreviewOut)
async def preview_item(
    item_id: str,
    channel_id: str = Query(""),
    service: PostingService = Depends(get_posting_service),
) -> PreviewOut:
    try:
        preview = await service.preview(item_id, channel_id)
    except PostingError as exc:
        _raise_posting(exc)
    return PreviewOut(
        text=preview.text,
        entities=preview.entities,
        buttons=[
            [{"text": b.text, "action": b.action, "url": b.url} for b in row]
            for row in preview.buttons
        ],
        media=[
            {"kind": m.kind, "filename": m.filename, "caption": m.caption}
            for m in preview.media
        ],
        is_album=preview.is_album,
        caption_used=preview.caption_used,
        char_count=preview.char_count,
        notice=preview.notice,
    )


@router.post("/tick", response_model=TickOut)
async def run_tick(
    service: PostingService = Depends(get_posting_service),
) -> TickOut:
    result = await service.tick()
    due = await service.due_count()
    return TickOut(**result, due=due)


def _buttons_rows(raw: str) -> list[list[dict[str, object]]]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    out: list[list[dict[str, object]]] = []
    for row in value:
        if isinstance(row, list):
            out.append([v for v in row if isinstance(v, dict)])
    return out


# --- Content Operations 2.0 (v1.9) -----------------------------------------


def _profile_out(service, profile) -> AiProfileOut:  # type: ignore[no-untyped-def]
    return AiProfileOut(
        id=profile.id,
        key=profile.key,
        title=profile.title,
        language=profile.language,
        tone=profile.tone,
        max_length=profile.max_length,
        system_instructions=profile.system_instructions,
        provider_policy=profile.provider_policy,
        actions=service.actions_of(profile),
        enabled=profile.enabled,
        builtin=profile.builtin,
        description=profile.description,
    )


def _rule_out(service, rule) -> AutomationRuleOut:  # type: ignore[no-untyped-def]
    from backend.app.services.automation_rules import describe_actions

    actions = service.actions_of(rule)
    return AutomationRuleOut(
        id=rule.id,
        name=rule.name,
        enabled=rule.enabled,
        source_kind=rule.source_kind,
        condition=service.condition_of(rule),
        actions=actions,
        action_titles=describe_actions(actions),
        profile_key=rule.profile_key,
        priority=rule.priority,
        description=rule.description,
    )


@router.get("/ai-profiles", response_model=list[AiProfileOut])
async def list_ai_profiles(
    service=Depends(get_ai_profile_service),  # type: ignore[assignment]
) -> list[AiProfileOut]:
    return [_profile_out(service, p) for p in await service.list_profiles()]


@router.post("/ai-profiles", response_model=AiProfileOut, status_code=201)
async def create_ai_profile(
    payload: AiProfileIn,
    service=Depends(get_ai_profile_service),  # type: ignore[assignment]
) -> AiProfileOut:
    from backend.app.services.ai_profiles import ProfileError

    try:
        profile = await service.create(**payload.model_dump())
    except ProfileError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _profile_out(service, profile)


@router.patch("/ai-profiles/{profile_id}", response_model=AiProfileOut)
async def update_ai_profile(
    profile_id: str,
    payload: AiProfileUpdateIn,
    service=Depends(get_ai_profile_service),  # type: ignore[assignment]
) -> AiProfileOut:
    from backend.app.services.ai_profiles import ProfileError

    try:
        profile = await service.update(profile_id, **payload.model_dump(exclude_unset=True))
    except ProfileError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _profile_out(service, profile)


@router.delete("/ai-profiles/{profile_id}", status_code=204)
async def delete_ai_profile(
    profile_id: str,
    service=Depends(get_ai_profile_service),  # type: ignore[assignment]
) -> None:
    from backend.app.services.ai_profiles import ProfileError

    try:
        await service.delete(profile_id)
    except ProfileError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc


@router.post("/items/{item_id}/ai/classify", response_model=ContentItemOut)
async def classify_item(
    item_id: str,
    service=Depends(get_content_pipeline_service),  # type: ignore[assignment]
    content: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    from backend.app.services.content_pipeline import PipelineError

    try:
        item = await service.classify(item_id)
    except PipelineError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _item_out(content, item)


@router.post("/items/{item_id}/ai/process", response_model=ContentItemOut)
async def process_item(
    item_id: str,
    payload: AiProcessIn,
    service=Depends(get_content_pipeline_service),  # type: ignore[assignment]
    content: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    from backend.app.services.content_pipeline import PipelineError

    try:
        if payload.classify_only:
            item = await service.classify(item_id)
        else:
            item = await service.process(item_id, profile_key=payload.profile_key)
    except PipelineError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _item_out(content, item)


@router.post("/items/{item_id}/moderate", response_model=ContentItemOut)
async def moderate_item(
    item_id: str,
    payload: ModerationDecisionIn,
    service=Depends(get_content_pipeline_service),  # type: ignore[assignment]
    content: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    from backend.app.services.content_pipeline import PipelineError

    try:
        item = await service.moderate(item_id, decision=payload.decision, note=payload.note)
    except PipelineError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _item_out(content, item)


@router.get("/automation-rules", response_model=list[AutomationRuleOut])
async def list_automation_rules(
    service=Depends(get_automation_rule_service),  # type: ignore[assignment]
) -> list[AutomationRuleOut]:
    return [_rule_out(service, r) for r in await service.list_rules()]


@router.post("/automation-rules", response_model=AutomationRuleOut, status_code=201)
async def create_automation_rule(
    payload: AutomationRuleIn,
    service=Depends(get_automation_rule_service),  # type: ignore[assignment]
) -> AutomationRuleOut:
    from backend.app.services.automation_rules import RuleError

    try:
        rule = await service.create(**payload.model_dump())
    except RuleError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _rule_out(service, rule)


@router.patch("/automation-rules/{rule_id}", response_model=AutomationRuleOut)
async def update_automation_rule(
    rule_id: str,
    payload: AutomationRuleUpdateIn,
    service=Depends(get_automation_rule_service),  # type: ignore[assignment]
) -> AutomationRuleOut:
    from backend.app.services.automation_rules import RuleError

    try:
        rule = await service.update(rule_id, **payload.model_dump(exclude_unset=True))
    except RuleError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _rule_out(service, rule)


@router.delete("/automation-rules/{rule_id}", status_code=204)
async def delete_automation_rule(
    rule_id: str,
    service=Depends(get_automation_rule_service),  # type: ignore[assignment]
) -> None:
    from backend.app.services.automation_rules import RuleError

    try:
        await service.delete(rule_id)
    except RuleError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc


@router.post("/items/{item_id}/apply-rules", response_model=ContentItemOut)
async def apply_rules(
    item_id: str,
    service=Depends(get_content_pipeline_service),  # type: ignore[assignment]
    content: ContentService = Depends(get_content_service),
) -> ContentItemOut:
    from backend.app.services.content_pipeline import PipelineError

    try:
        item = await service._require_item(item_id)
        source = await content.sources.get(item.source_id)
        source_kind = source.kind.value if source else ""
        await service.apply_rule_actions(item_id, source_kind=source_kind)
    except PipelineError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _item_out(content, await service._require_item(item_id))


@router.get("/pipeline/analytics", response_model=PipelineAnalyticsOut)
async def pipeline_analytics(
    limit: int = Query(default=50, ge=1, le=500),
    service=Depends(get_content_pipeline_service),  # type: ignore[assignment]
) -> PipelineAnalyticsOut:
    operations = service.operations
    stage_counts = await operations.stage_counts()
    ai_statuses = await operations.status_counts_for_stage("ai")
    comment_statuses = await operations.status_counts_for_stage("comment")
    delete_statuses = await operations.status_counts_for_stage("delete")
    recent = await operations.list_recent(limit)
    provider_counts: dict[str, int] = {}
    for op in recent:
        if op.stage == "ai" and op.provider:
            provider_counts[op.provider] = provider_counts.get(op.provider, 0) + 1
    return PipelineAnalyticsOut(
        stage_counts=stage_counts,
        ai_provider_counts=provider_counts,
        ai_fallback=sum(1 for op in recent if op.stage == "ai" and op.fallback_used),
        ai_failed=ai_statuses.get("ai_unavailable", 0) + ai_statuses.get("error", 0),
        comment_posted=comment_statuses.get("comment_posted", 0),
        comment_failed=comment_statuses.get("comment_failed", 0),
        delete_failed=delete_statuses.get("delete_failed", 0),
        recent=[
            PipelineRecordOut(
                id=op.id,
                item_id=op.item_id,
                publication_id=op.publication_id,
                stage=op.stage,
                status=op.status,
                source_kind=op.source_kind,
                channel_id=op.channel_id,
                provider=op.provider,
                model=op.model,
                fallback_used=op.fallback_used,
                latency_ms=op.latency_ms,
                attempts=op.attempts,
                detail=op.detail,
                occurred_at=op.occurred_at.isoformat() if op.occurred_at else "",
            )
            for op in recent
        ],
    )


__all__ = ["router"]
