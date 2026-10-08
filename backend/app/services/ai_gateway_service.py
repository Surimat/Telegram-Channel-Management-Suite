"""AiGatewayService — wires the AI Gateway domain to the database (v1.8).

Responsibilities:

* provider CRUD, with API keys **sealed** via :func:`seal_secret` (never returned,
  logged, exported or shown in diagnostics);
* routing preferences (strategy, allow-paid, timeout, retries);
* building the router + registry and running a request with failover;
* honest status/health reporting and a bounded observability ring;
* the wrapper library and browser-runtime status;
* a capability/use-case matrix;
* a small content-integration interface (rewrite/summarize/classify/…) so the
  Content Studio can call the gateway at a later stage (requirement 22).

The service never registers accounts, bypasses CAPTCHA/MFA/verification or
regional blocks, and never handles someone else's cookies/sessions.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.gateway import registry as reg
from backend.app.ai.gateway.browser import BrowserRuntime, PlaywrightBrowserRuntime
from backend.app.ai.gateway.errors import GatewayError
from backend.app.ai.gateway.http import HttpTransport, HttpxTransport
from backend.app.ai.gateway.provider import AIProvider
from backend.app.ai.gateway.reliability import (
    HealthStore,
    new_correlation_id,
)
from backend.app.ai.gateway.router import STRATEGIES, AIRouter
from backend.app.ai.gateway.types import (
    AUTH_API_KEY,
    Capability,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ProviderInfo,
)
from backend.app.ai.gateway.wrappers.definition import LIBRARY
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import register_secrets
from backend.app.core.security import open_secret, seal_secret
from backend.app.db.models.ai_gateway import AiGatewayRequest, AiProviderRow
from backend.app.db.repositories.ai_gateway import (
    AiGatewayRequestRepository,
    AiProviderRepository,
    AiRouteSettingRepository,
)
from backend.app.services.events_service import EventsService

#: Routing preference keys stored in ``ai_route_settings``.
ROUTE_KEYS = {
    "ai_gateway_enabled": ("Включить шлюз ИИ", bool, "ai_gateway_enabled"),
    "ai_gateway_strategy": ("Стратегия выбора", str, "ai_gateway_strategy"),
    "ai_gateway_max_retries": ("Повторы на провайдера", int, "ai_gateway_max_retries"),
    "ai_gateway_timeout_seconds": ("Таймаут запроса", float, "ai_gateway_timeout_seconds"),
    "ai_gateway_history_limit": ("Хранить записей", int, "ai_gateway_history_limit"),
    "ai_gateway_allow_paid": ("Разрешить платные", bool, "ai_gateway_allow_paid"),
    "ai_gateway_web_enabled": ("Web-обёртки", bool, "ai_gateway_web_enabled"),
}


@dataclass(slots=True)
class ProviderView:
    """A provider as shown to the UI — **never** includes the API key."""

    provider: str
    kind: str
    kind_label: str
    model: str
    base_url: str
    auth_mode: str
    has_key: bool
    enabled: bool
    priority: int
    cost: str
    source: str
    capabilities: dict[str, bool]
    wrapper_id: str
    region_status: str
    note: str
    status: str = "unknown"
    status_detail: str = ""
    latency_ms: int = 0
    last_error: str = ""
    last_success: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "kind_label": self.kind_label,
            "model": self.model,
            "base_url": self.base_url,
            "auth_mode": self.auth_mode,
            "has_key": self.has_key,
            "enabled": self.enabled,
            "priority": self.priority,
            "cost": self.cost,
            "source": self.source,
            "capabilities": self.capabilities,
            "wrapper_id": self.wrapper_id,
            "region_status": self.region_status,
            "note": self.note,
            "status": self.status,
            "status_detail": self.status_detail,
            "latency_ms": self.latency_ms,
            "last_error": self.last_error,
            "last_success": self.last_success,
        }


@dataclass(slots=True)
class GatewayStatus:
    enabled: bool
    strategy: str
    providers: int
    enabled_providers: int
    available_providers: int
    browser_available: bool
    browser_detail: str
    allow_paid: bool
    web_enabled: bool
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "strategy": self.strategy,
            "providers": self.providers,
            "enabled_providers": self.enabled_providers,
            "available_providers": self.available_providers,
            "browser_available": self.browser_available,
            "browser_detail": self.browser_detail,
            "allow_paid": self.allow_paid,
            "web_enabled": self.web_enabled,
            "note": self.note,
        }


class AiGatewayService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        transport: HttpTransport | None = None,
        browser_runtime: BrowserRuntime | None = None,
        health: HealthStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.providers_repo = AiProviderRepository(session)
        self.route_repo = AiRouteSettingRepository(session)
        self.requests_repo = AiGatewayRequestRepository(session)
        self.events = EventsService(session)
        self._transport = transport
        self._browser_runtime = browser_runtime
        self._health = health
        self._provider_cache: list[AIProvider] | None = None

    # ==================================================================
    # Routing preferences
    # ==================================================================
    async def _setting(self, key: str):
        _title, _type, attr = ROUTE_KEYS[key]
        default = getattr(self.settings, attr)
        row = await self.route_repo.get(key)
        if row is None:
            return default
        try:
            if isinstance(default, bool):
                return str(row.value).lower() in ("1", "true", "yes", "on")
            if isinstance(default, int) and not isinstance(default, bool):
                return int(float(row.value))
            if isinstance(default, float):
                return float(row.value)
            return str(row.value)
        except (TypeError, ValueError):
            return default

    async def effective(self) -> dict[str, object]:
        return {key: await self._setting(key) for key in ROUTE_KEYS}

    async def set_setting(self, key: str, value: object) -> None:
        if key not in ROUTE_KEYS:
            raise GatewayError("Неизвестная настройка шлюза.")
        _title, type_, _attr = ROUTE_KEYS[key]
        if type_ is bool:
            value = bool(value)
            stored = "true" if value else "false"
        elif type_ is int:
            value = int(value)  # raises ValueError on bad input
            stored = str(value)
        elif type_ is float:
            value = float(value)
            stored = str(value)
        else:
            value = str(value)
            if key == "ai_gateway_strategy" and value not in STRATEGIES:
                raise GatewayError(
                    "Неизвестная стратегия.",
                    how_to_fix="Выберите: " + ", ".join(STRATEGIES),
                )
            stored = value
        await self.route_repo.set(key, stored, value_type=type_.__name__)
        self._provider_cache = None

    # ==================================================================
    # Provider CRUD
    # ==================================================================
    async def list_providers(self) -> list[AiProviderRow]:
        return await self.providers_repo.list_all()

    async def get_provider(self, provider: str) -> AiProviderRow | None:
        return await self.providers_repo.find(provider)

    async def upsert_provider(
        self,
        *,
        provider: str,
        kind: str,
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        auth_mode: str = AUTH_API_KEY,
        enabled: bool = False,
        priority: int = 0,
        cost: str = "standard",
        capabilities: Capability | None = None,
        wrapper_id: str = "",
        note: str = "",
    ) -> AiProviderRow:
        if kind not in reg.ALL_KINDS:
            raise GatewayError(
                "Неизвестный тип провайдера.",
                how_to_fix="Выберите из: " + ", ".join(reg.ALL_KINDS),
            )
        row = await self.providers_repo.find(provider)
        caps = capabilities or Capability(text=True)
        if row is None:
            row = AiProviderRow(provider=provider)
            self.session.add(row)
        row.kind = kind
        row.model = model
        row.base_url = base_url
        row.auth_mode = auth_mode
        row.enabled = enabled
        row.priority = priority
        row.cost = cost
        row.wrapper_id = wrapper_id
        row.note = note
        row.cap_text = caps.text
        row.cap_image = caps.image
        row.cap_file = caps.file
        row.cap_streaming = caps.streaming
        row.cap_structured = caps.structured
        if api_key:
            # Seal on write; register for log redaction. Never stored in the clear.
            row.api_key_encrypted = seal_secret(api_key, self.settings)
            register_secrets([api_key])
        await self.session.flush()
        self._provider_cache = None
        return row

    async def delete_provider(self, provider: str) -> bool:
        row = await self.providers_repo.find(provider)
        if row is None:
            return False
        await self.providers_repo.delete(row)
        self._provider_cache = None
        return True

    def _capabilities(self, row: AiProviderRow) -> Capability:
        return Capability(
            text=row.cap_text,
            image=row.cap_image,
            file=row.cap_file,
            streaming=row.cap_streaming,
            structured=row.cap_structured,
            verified=row.cap_verified,
        )

    def _api_key(self, row: AiProviderRow) -> str:
        if not row.api_key_encrypted:
            return ""
        try:
            return open_secret(row.api_key_encrypted, self.settings)
        except ValueError:
            return ""

    def _config(self, row: AiProviderRow) -> reg.ProviderConfig:
        return reg.ProviderConfig(
            provider=row.provider,
            kind=row.kind,
            model=row.model,
            base_url=row.base_url,
            api_key=self._api_key(row),
            enabled=row.enabled,
            priority=row.priority,
            cost=row.cost,
            capabilities=self._capabilities(row),
            wrapper_id=row.wrapper_id,
            note=row.note,
        )

    def _transport_for(self) -> HttpTransport:
        return self._transport or HttpxTransport()

    def _runtime_for(self) -> BrowserRuntime:
        return self._browser_runtime or PlaywrightBrowserRuntime(
            user_data_dir=str(self.settings.resolve_models_dir().parent / "browser-profile")
        )

    async def build_providers(self) -> list[AIProvider]:
        """Build (and cache) the enabled providers."""
        if self._provider_cache is not None:
            return self._provider_cache
        rows = await self.providers_repo.list_all()
        transport = self._transport_for()
        runtime = self._runtime_for()
        providers: list[AIProvider] = []
        for row in rows:
            if not row.enabled:
                continue
            providers.append(
                reg.build_provider(
                    self._config(row), transport=transport, browser_runtime=runtime
                )
            )
        self._provider_cache = providers
        return providers

    def health(self) -> HealthStore:
        if self._health is None:
            self._health = HealthStore()
        return self._health

    # ==================================================================
    # Status
    # ==================================================================
    async def status(self) -> GatewayStatus:
        rows = await self.providers_repo.list_all()
        enabled = [r for r in rows if r.enabled]
        providers = await self.build_providers()
        available = sum(1 for p in providers if p.availability().usable)
        runtime = self._runtime_for()
        return GatewayStatus(
            enabled=bool(await self._setting("ai_gateway_enabled")),
            strategy=str(await self._setting("ai_gateway_strategy")),
            providers=len(rows),
            enabled_providers=len(enabled),
            available_providers=available,
            browser_available=bool(runtime.available),
            browser_detail=runtime.availability_detail(),
            allow_paid=bool(await self._setting("ai_gateway_allow_paid")),
            web_enabled=bool(await self._setting("ai_gateway_web_enabled")),
            note=(
                "Провайдеры могут менять условия и доступность. Suite не "
                "гарантирует бесплатность навсегда."
            ),
        )

    async def provider_views(self) -> list[ProviderView]:
        rows = await self.providers_repo.list_all()
        providers = {p.name: p for p in await self.build_providers()}
        health = self.health()
        out: list[ProviderView] = []
        for row in rows:
            info = self._info_for(row, providers.get(row.provider))
            st = health.status(row.provider)
            view = ProviderView(
                provider=row.provider,
                kind=row.kind,
                kind_label=reg.KIND_LABELS.get(row.kind, row.kind),
                model=row.model,
                base_url=row.base_url,
                auth_mode=row.auth_mode,
                has_key=bool(row.api_key_encrypted),
                enabled=row.enabled,
                priority=row.priority,
                cost=row.cost,
                source=str(info.source),
                capabilities=info.as_dict()["capabilities"],  # type: ignore[assignment]
                wrapper_id=row.wrapper_id,
                region_status=row.region_status,
                note=row.note,
                status=st.availability.status,
                status_detail=st.availability.detail,
                latency_ms=st.latency_ms,
                last_error=st.last_error,
                last_success=st.last_success,
            )
            if not row.enabled:
                view.status = "unavailable"
                view.status_detail = "Выключен."
            out.append(view)
        return out

    def _info_for(self, row: AiProviderRow, provider: AIProvider | None) -> ProviderInfo:
        if provider is not None:
            return provider.info
        return ProviderInfo(
            provider=row.provider,
            model=row.model,
            source=reg.source_for_kind(row.kind),
            capabilities=self._capabilities(row),
            auth_mode=row.auth_mode,
            auth_required=row.auth_mode == AUTH_API_KEY and not row.api_key_encrypted,
            cost=row.cost,
            priority=row.priority,
            note=row.note,
        )

    # ==================================================================
    # Execution
    # ==================================================================
    def _router(self) -> AIRouter:
        return AIRouter(health=self.health())

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Run a request through the gateway with failover and observability."""
        if not request.correlation_id:
            request.correlation_id = new_correlation_id()
        strategy = request.strategy or str(await self._setting("ai_gateway_strategy"))
        allow_paid = bool(await self._setting("ai_gateway_allow_paid"))
        providers = await self.build_providers()
        if not allow_paid:
            providers = [
                p
                for p in providers
                if p.info.cost in ("free", "cheap")
                or p.info.source in ("local", "web")
                or request.provider == p.name
            ]
        if not request.timeout_seconds or request.timeout_seconds <= 0:
            request.timeout_seconds = float(
                await self._setting("ai_gateway_timeout_seconds")
            )
        request.strategy = strategy
        response = await self._router().route(request, providers)
        await self._record(request, response)
        return response

    async def _record(self, request: ChatRequest, response: ChatResponse) -> None:
        try:
            await self.requests_repo.add(
                AiGatewayRequest(
                    request_id=response.request_id or request.correlation_id,
                    provider=response.provider_used,
                    model=response.model_used,
                    source=response.source,
                    strategy=request.strategy,
                    ok=response.ok,
                    fallback_used=response.fallback_used,
                    attempts=len(response.attempts) or 1,
                    latency_ms=response.latency_ms,
                    status=response.status,
                    error_category=response.error_category,
                )
            )
            limit = int(await self._setting("ai_gateway_history_limit"))
            if limit > 0:
                await self.requests_repo.trim(limit)
        except Exception:  # pragma: no cover - observability must never break a call
            pass

    # ==================================================================
    # Wrapper library + browser runtime
    # ==================================================================
    def wrapper_library(self) -> list[dict[str, object]]:
        return [
            {
                "id": d.id,
                "name": d.name,
                "website": d.website,
                "capabilities": d.capability_dict(),
                "auth_mode": d.auth_mode,
                "version": d.version,
                "enabled": d.enabled,
                "fallback_priority": d.fallback_priority,
                "cost": d.cost,
                "note": d.note,
            }
            for d in LIBRARY
        ]

    def browser_status(self) -> dict[str, object]:
        runtime = self._runtime_for()
        return {
            "available": bool(runtime.available),
            "detail": runtime.availability_detail(),
            "runtime": runtime.name,
            "docker_note": (
                "В Docker браузерный движок необязателен: API-провайдеры работают "
                "и без него."
            ),
        }

    # ==================================================================
    # Capability / use-case matrix
    # ==================================================================
    def use_cases(self) -> list[dict[str, object]]:
        return [
            {"group": "content", "id": "rewrite", "modality": "text"},
            {"group": "content", "id": "summarize", "modality": "text"},
            {"group": "content", "id": "title", "modality": "text"},
            {"group": "content", "id": "description", "modality": "text"},
            {"group": "content", "id": "translation", "modality": "text"},
            {"group": "content", "id": "moderation", "modality": "text"},
            {"group": "content", "id": "classification", "modality": "text"},
            {"group": "media", "id": "image_understanding", "modality": "image"},
            {"group": "media", "id": "ocr", "modality": "image"},
            {"group": "media", "id": "captioning", "modality": "image"},
            {"group": "media", "id": "visual_moderation", "modality": "image"},
            {"group": "media", "id": "image_to_text", "modality": "image"},
            {"group": "channel", "id": "draft_generation", "modality": "text"},
            {"group": "channel", "id": "comment_generation", "modality": "text"},
            {"group": "channel", "id": "content_classification", "modality": "text"},
            {"group": "channel", "id": "scheduling_recommendations", "modality": "text"},
            {"group": "research", "id": "web_research", "modality": "text"},
            {"group": "research", "id": "source_extraction", "modality": "text"},
            {"group": "research", "id": "comparison", "modality": "text"},
            {"group": "research", "id": "fact_summarization", "modality": "text"},
            {"group": "automation", "id": "browser_task", "modality": "text"},
            {"group": "automation", "id": "form_filling", "modality": "text"},
            {"group": "automation", "id": "website_interaction", "modality": "text"},
            {"group": "automation", "id": "data_extraction", "modality": "text"},
        ]

    async def capability_matrix(self) -> list[dict[str, object]]:
        """For each use case, which providers can serve it (honest)."""
        providers = await self.build_providers()
        out: list[dict[str, object]] = []
        for uc in self.use_cases():
            needed = Capability(
                text=True,
                image=uc["modality"] == "image",
                structured=uc["id"] == "classification",
            )
            capable = [
                p.name for p in providers if p.info.capabilities.at_least(needed)
            ]
            out.append({**uc, "providers": capable, "available": bool(capable)})
        return out

    # ==================================================================
    # Observability
    # ==================================================================
    async def recent_requests(self, limit: int = 50) -> list[dict[str, object]]:
        rows = await self.requests_repo.list_recent(limit)
        return [
            {
                "request_id": r.request_id,
                "provider": r.provider,
                "model": r.model,
                "source": r.source,
                "strategy": r.strategy,
                "ok": r.ok,
                "fallback_used": r.fallback_used,
                "attempts": r.attempts,
                "latency_ms": r.latency_ms,
                "status": r.status,
                "error_category": r.error_category,
                "at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]

    def diagnostics(self) -> dict[str, object]:
        """A redacted snapshot for the Diagnostics panel.

        Contains no API keys, no prompt text and no browser profile data.
        """
        runtime = self._runtime_for()
        return {
            "gateway": "ai_gateway",
            "strategies": list(STRATEGIES),
            "kinds": list(reg.ALL_KINDS),
            "browser": {
                "runtime": runtime.name,
                "available": bool(runtime.available),
            },
            "wrappers": len(LIBRARY),
            "fallback": "enabled",
        }

    # ==================================================================
    # Content integration point (requirement 22)
    # ==================================================================
    async def transform(
        self,
        *,
        task: str,
        text: str,
        instruction: str = "",
        modality: str = "text",
        strategy: str = "",
        provider: str = "",
    ) -> ChatResponse:
        """A thin, task-named entry the Content Studio can call later.

        ``task`` is one of the content/media use-case ids above. This composes a
        prompt and routes it; the Upper layers decide retention/policy.
        """
        system = (
            "Ты помощник для редактора Telegram-канала. Отвечай по-русски, "
            "кратко и по делу. Не выдумывай факты."
        )
        if instruction:
            system += f"\nЗадача: {instruction}"
        else:
            system += f"\nЗадача: {task}."
        requires = Capability(text=True, image=modality == "image")
        request = ChatRequest(
            messages=[
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=text),
            ],
            requires=requires,
            strategy=strategy,
            provider=provider,
            task=task,
            correlation_id=new_correlation_id(),
        )
        return await self.chat(request)


__all__ = [
    "ROUTE_KEYS",
    "AiGatewayService",
    "GatewayStatus",
    "ProviderView",
]
