"""AI Gateway API (v1.8).

Owner-facing configuration, health and observability for the AI Gateway. No
endpoint ever returns an API key, a browser credential or prompt text. The
Web-wrapper layer reports honest availability; it never claims a capability that
was not probed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.ai.gateway import registry as reg
from backend.app.ai.gateway.errors import GatewayError
from backend.app.ai.gateway.router import STRATEGIES
from backend.app.ai.gateway.types import Capability, ChatRequest
from backend.app.api.deps import get_ai_gateway_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.ai_gateway import (
    AttemptOut,
    BrowserStatusOut,
    ChatIn,
    ChatOut,
    GatewayStatusOut,
    ProviderIn,
    ProviderListOut,
    ProviderOut,
    RequestHistoryOut,
    RouteSettingsOut,
    RouteUpdateIn,
    ToggleIn,
    UseCaseMatrixOut,
    UseCaseOut,
    WrapperLibraryOut,
    WrapperOut,
)
from backend.app.services.ai_gateway_service import AiGatewayService, ProviderView

router = APIRouter(prefix="/ai-gateway", tags=["ai-gateway"])

GatewayDep = Annotated[AiGatewayService, Depends(get_ai_gateway_service)]


def _raise(exc: GatewayError) -> None:
    raise ApiError(400, exc.message, exc.how_to_fix)


def _provider_out(view: ProviderView) -> ProviderOut:
    return ProviderOut(**view.as_dict())  # type: ignore[arg-type]


def _chat_out(response) -> ChatOut:
    return ChatOut(
        ok=response.ok,
        text=response.text,
        provider_used=response.provider_used,
        model_used=response.model_used,
        source=str(response.source),
        fallback_used=response.fallback_used,
        attempts=[AttemptOut(**a) for a in response.attempts],
        latency_ms=response.latency_ms,
        status=response.status,
        error=response.error,
        error_category=response.error_category,
        request_id=response.request_id,
        structured=response.structured,
    )


@router.get("/status", response_model=GatewayStatusOut)
async def gateway_status(service: GatewayDep) -> GatewayStatusOut:
    return GatewayStatusOut(**(await service.status()).as_dict())  # type: ignore[arg-type]


@router.get("/providers", response_model=ProviderListOut)
async def list_providers(service: GatewayDep) -> ProviderListOut:
    views = await service.provider_views()
    return ProviderListOut(
        items=[_provider_out(v) for v in views],
        kinds=[{"value": k, "label": reg.KIND_LABELS[k]} for k in reg.ALL_KINDS],
        strategies=list(STRATEGIES),
    )


@router.post("/providers", response_model=ProviderOut, status_code=201)
async def upsert_provider(
    payload: ProviderIn, service: GatewayDep
) -> ProviderOut:
    caps = None
    if payload.capabilities is not None:
        caps = Capability(
            text=payload.capabilities.text,
            image=payload.capabilities.image,
            file=payload.capabilities.file,
            streaming=payload.capabilities.streaming,
            structured=payload.capabilities.structured,
        )
    service = service
    try:
        await service.upsert_provider(
            provider=payload.provider,
            kind=payload.kind,
            model=payload.model,
            base_url=payload.base_url,
            api_key=payload.api_key,
            auth_mode=payload.auth_mode,
            enabled=payload.enabled,
            priority=payload.priority,
            cost=payload.cost,
            capabilities=caps,
            wrapper_id=payload.wrapper_id,
            note=payload.note,
        )
    except GatewayError as exc:
        _raise(exc)
    await service.session.commit()
    for view in await service.provider_views():
        if view.provider == payload.provider:
            return _provider_out(view)
    raise ApiError(500, "Не удалось сохранить провайдера.")


@router.post("/providers/{provider}/toggle", response_model=ProviderOut)
async def toggle_provider(
    provider: str,
    payload: ToggleIn,
    service: GatewayDep,
) -> ProviderOut:
    service = service
    row = await service.get_provider(provider)
    if row is None:
        raise ApiError(404, "Провайдер не найден.")
    row.enabled = payload.enabled
    await service.session.commit()
    service._provider_cache = None
    for view in await service.provider_views():
        if view.provider == provider:
            return _provider_out(view)
    raise ApiError(500, "Не удалось переключить провайдера.")


@router.delete("/providers/{provider}", status_code=204)
async def delete_provider(
    provider: str, service: GatewayDep
) -> None:
    service = service
    if not await service.delete_provider(provider):
        raise ApiError(404, "Провайдер не найден.")
    await service.session.commit()
    return None


@router.get("/settings", response_model=RouteSettingsOut)
async def route_settings(
    service: GatewayDep,
) -> RouteSettingsOut:
    eff = await service.effective()
    return RouteSettingsOut(
        strategy=str(eff["ai_gateway_strategy"]),
        allow_paid=bool(eff["ai_gateway_allow_paid"]),
        web_enabled=bool(eff["ai_gateway_web_enabled"]),
        max_retries=int(eff["ai_gateway_max_retries"]),
        timeout_seconds=float(eff["ai_gateway_timeout_seconds"]),
        history_limit=int(eff["ai_gateway_history_limit"]),
        enabled=bool(eff["ai_gateway_enabled"]),
    )


@router.put("/settings", response_model=RouteSettingsOut)
async def update_route_settings(
    payload: RouteUpdateIn, service: GatewayDep
) -> RouteSettingsOut:
    service = service
    try:
        await service.set_setting(payload.key, payload.value)
    except GatewayError as exc:
        _raise(exc)
    except (TypeError, ValueError):
        raise ApiError(400, "Недопустимое значение настройки.") from None
    await service.session.commit()
    eff = await service.effective()
    return RouteSettingsOut(
        strategy=str(eff["ai_gateway_strategy"]),
        allow_paid=bool(eff["ai_gateway_allow_paid"]),
        web_enabled=bool(eff["ai_gateway_web_enabled"]),
        max_retries=int(eff["ai_gateway_max_retries"]),
        timeout_seconds=float(eff["ai_gateway_timeout_seconds"]),
        history_limit=int(eff["ai_gateway_history_limit"]),
        enabled=bool(eff["ai_gateway_enabled"]),
    )


@router.post("/chat", response_model=ChatOut)
async def gateway_chat(payload: ChatIn, service: GatewayDep) -> ChatOut:
    from backend.app.ai.gateway.types import ChatMessage

    messages = []
    if payload.system:
        messages.append(ChatMessage(role="system", content=payload.system))
    messages.append(ChatMessage(role="user", content=payload.text))
    requires = Capability(text=True, image=payload.modality == "image")
    request = ChatRequest(
        messages=messages,
        requires=requires,
        strategy=payload.strategy,
        provider=payload.provider,
        task=payload.task,
        timeout_seconds=payload.timeout_seconds,
        structured=payload.structured,
    )
    response = await service.chat(request)
    await service.session.commit()
    return _chat_out(response)


@router.get("/wrappers", response_model=WrapperLibraryOut)
async def wrapper_library(service: GatewayDep) -> WrapperLibraryOut:
    items = service.wrapper_library()
    return WrapperLibraryOut(items=[WrapperOut(**item) for item in items])  # type: ignore[arg-type]


@router.get("/browser", response_model=BrowserStatusOut)
async def browser_status(service: GatewayDep) -> BrowserStatusOut:
    return BrowserStatusOut(**service.browser_status())  # type: ignore[arg-type]


@router.get("/use-cases", response_model=UseCaseMatrixOut)
async def use_case_matrix(service: GatewayDep) -> UseCaseMatrixOut:
    items = await service.capability_matrix()
    return UseCaseMatrixOut(items=[UseCaseOut(**item) for item in items])  # type: ignore[arg-type]


@router.get("/requests", response_model=RequestHistoryOut)
async def request_history(
    service: GatewayDep, limit: int = 50
) -> RequestHistoryOut:
    items = await service.recent_requests(limit)
    return RequestHistoryOut(items=items)  # type: ignore[arg-type]


__all__ = ["router"]
