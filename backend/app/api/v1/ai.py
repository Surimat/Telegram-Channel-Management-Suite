"""AI router (PHASE 7).

Exposes status, settings, classification, model management and metrics. All
responses are safe (no stack traces, no secrets) and RU-first.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.errors import AiError
from backend.app.ai.router import category_title
from backend.app.ai.types import MODE_AUTO, VALID_MODES
from backend.app.api.schemas.ai import (
    AiClassifyIn,
    AiClassifyOut,
    AiHistoryOut,
    AiMetricsOut,
    AiModelCheckOut,
    AiModelOut,
    AiOverviewOut,
    AiRecordOut,
    AiSettingHelp,
    AiSettingsOut,
    AiSettingsUpdate,
    AiStatusOut,
)
from backend.app.db.session import get_session
from backend.app.services.ai_help import human_size, setting_help
from backend.app.services.ai_service import AI_SETTING_SPECS, AiService, AiStatus, ModelCheck

router = APIRouter(prefix="/ai", tags=["ai"])

_SOURCE_TITLES = {
    "rules": "Обычные правила",
    "llm": "Мини-ИИ",
    "manual": "Вручную",
    "fallback": "Запасной вариант",
    "default": "По умолчанию",
}


def _service(session: AsyncSession) -> AiService:
    return AiService(session)


def _status_out(status: AiStatus) -> AiStatusOut:
    return AiStatusOut(
        enabled=status.enabled,
        backend=status.backend,
        runtime_available=status.runtime_available,
        model_path=status.model_path,
        model_exists=status.model_exists,
        model_size_bytes=status.model_size_bytes,
        model_size_human=human_size(status.model_size_bytes),
        model_loaded=status.model_loaded,
        effective=status.effective,
        reason=status.reason,
        how_to_fix=status.how_to_fix,
    )


def _check_out(check: ModelCheck) -> AiModelCheckOut:
    return AiModelCheckOut(
        ok=check.ok,
        runtime_available=check.runtime_available,
        model_exists=check.model_exists,
        message=check.message,
        how_to_fix=check.how_to_fix,
        size_bytes=check.size_bytes,
        load_ms=check.load_ms,
    )


def _metrics_out(data: dict[str, object]) -> AiMetricsOut:
    fields = set(AiMetricsOut.model_fields)
    return AiMetricsOut(**{k: int(v) for k, v in data.items() if k in fields})  # type: ignore[arg-type]


@router.get("/status", response_model=AiStatusOut)
async def ai_status(session: AsyncSession = Depends(get_session)) -> AiStatusOut:
    return _status_out(await _service(session).status())


@router.get("/overview", response_model=AiOverviewOut)
async def ai_overview(session: AsyncSession = Depends(get_session)) -> AiOverviewOut:
    service = _service(session)
    status = await service.status()
    metrics = await service.metrics()
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today = await service.metrics_since(today_start)
    return AiOverviewOut(
        status=_status_out(status),
        metrics=_metrics_out(metrics),
        today=_metrics_out(today),
    )


@router.get("/settings", response_model=AiSettingsOut)
async def ai_settings(session: AsyncSession = Depends(get_session)) -> AiSettingsOut:
    service = _service(session)
    effective = await service.effective()
    items: list[AiSettingHelp] = []
    for key in AI_SETTING_SPECS:
        default = getattr(service.settings, AI_SETTING_SPECS[key][2])
        items.append(AiSettingHelp(**setting_help(key, effective[key], default)))  # type: ignore[arg-type]
    return AiSettingsOut(items=items)


@router.put("/settings", response_model=AiSettingsOut)
async def ai_update_settings(
    payload: AiSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> AiSettingsOut:
    service = _service(session)
    for key, value in payload.values.items():
        try:
            await service.set_setting(key, value)
        except AiError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc
    await session.commit()
    return await ai_settings(session)


@router.post("/classify", response_model=AiClassifyOut)
async def ai_classify(
    payload: AiClassifyIn,
    session: AsyncSession = Depends(get_session),
) -> AiClassifyOut:
    mode = payload.mode if payload.mode in VALID_MODES else MODE_AUTO
    outcome = await _service(session).classify(payload.text, mode=mode)
    await session.commit()
    result = outcome.result
    return AiClassifyOut(
        category=str(result.category),
        category_title=category_title(result.category),
        tone=str(result.tone),
        intent=str(result.intent),
        suggested_emoji=result.suggested_emoji,
        confidence=result.confidence,
        source=result.source,
        source_title=_SOURCE_TITLES.get(result.source, result.source),
        model=result.model,
        processing_time_ms=result.processing_time_ms,
        mode=mode,
        ai_attempted=outcome.ai_attempted,
        ai_used=outcome.ai_used,
        encoder_attempted=outcome.encoder_attempted,
        encoder_used=outcome.encoder_used,
        fallback_used=outcome.fallback_used,
        ai_error=outcome.ai_error,
    )


@router.post("/test", response_model=AiClassifyOut)
async def ai_test(
    payload: AiClassifyIn,
    session: AsyncSession = Depends(get_session),
) -> AiClassifyOut:
    """Alias of /classify kept for the UI's "testing" panel."""
    return await ai_classify(payload, session)


@router.get("/models", response_model=list[AiModelOut])
async def ai_models(session: AsyncSession = Depends(get_session)) -> list[AiModelOut]:
    models = await _service(session).list_models()
    return [
        AiModelOut(
            name=str(m["name"]),
            path=str(m["path"]),
            size_bytes=int(m["size_bytes"]),
            size_human=human_size(int(m["size_bytes"])),
        )
        for m in models
    ]


@router.post("/model/check", response_model=AiModelCheckOut)
async def ai_model_check(session: AsyncSession = Depends(get_session)) -> AiModelCheckOut:
    check = await _service(session).check_model()
    await session.commit()
    return _check_out(check)


@router.post("/model/load", response_model=AiModelCheckOut)
async def ai_model_load(session: AsyncSession = Depends(get_session)) -> AiModelCheckOut:
    check = await _service(session).load_model()
    await session.commit()
    return _check_out(check)


@router.post("/model/unload", response_model=AiStatusOut)
async def ai_model_unload(session: AsyncSession = Depends(get_session)) -> AiStatusOut:
    status = await _service(session).unload_model()
    return _status_out(status)


@router.get("/metrics", response_model=AiMetricsOut)
async def ai_metrics(session: AsyncSession = Depends(get_session)) -> AiMetricsOut:
    return _metrics_out(await _service(session).metrics())


@router.get("/history", response_model=AiHistoryOut)
async def ai_history(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> AiHistoryOut:
    records, total = await _service(session).history(limit=limit, offset=offset)
    return AiHistoryOut(items=[AiRecordOut.model_validate(r) for r in records], total=total)


__all__ = ["router"]
