"""Pydantic schemas for the AI Gateway API (v1.8).

No schema ever carries a raw API key or browser credential: providers are shown
with a boolean ``has_key`` only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CapabilityOut(BaseModel):
    text: bool = False
    image: bool = False
    file: bool = False
    streaming: bool = False
    structured: bool = False
    verified: bool = False


class ProviderOut(BaseModel):
    provider: str
    kind: str
    kind_label: str
    model: str = ""
    base_url: str = ""
    auth_mode: str = "api_key"
    has_key: bool = False
    enabled: bool = False
    priority: int = 0
    cost: str = "standard"
    source: str = "api"
    capabilities: dict[str, bool] = Field(default_factory=dict)
    wrapper_id: str = ""
    region_status: str = ""
    note: str = ""
    status: str = "unknown"
    status_detail: str = ""
    latency_ms: int = 0
    last_error: str = ""
    last_success: str = ""


class ProviderIn(BaseModel):
    provider: str
    kind: str = "openai_compatible"
    model: str = ""
    base_url: str = ""
    # Write-only: sealed on the server and never echoed back.
    api_key: str = ""
    auth_mode: str = "api_key"
    enabled: bool = False
    priority: int = 0
    cost: str = "standard"
    capabilities: CapabilityOut | None = None
    wrapper_id: str = ""
    note: str = ""


class ProviderListOut(BaseModel):
    items: list[ProviderOut]
    kinds: list[dict[str, str]]
    strategies: list[str]


class ToggleIn(BaseModel):
    enabled: bool


class GatewayStatusOut(BaseModel):
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


class RouteSettingsOut(BaseModel):
    strategy: str = "auto"
    allow_paid: bool = False
    web_enabled: bool = False
    max_retries: int = 2
    timeout_seconds: float = 60.0
    history_limit: int = 200
    enabled: bool = False


class RouteUpdateIn(BaseModel):
    key: str
    value: object


class AttachmentIn(BaseModel):
    """A caller-owned image/file reference (v2.0 multimodal). Never a secret."""

    kind: str = "image"
    reference: str = ""
    mime: str = ""
    filename: str = ""


class ChatIn(BaseModel):
    text: str = ""
    system: str = ""
    strategy: str = ""
    provider: str = ""
    task: str = ""
    timeout_seconds: float = 0.0
    structured: bool = False
    modality: str = "text"
    attachments: list[AttachmentIn] = Field(default_factory=list)


class AttemptOut(BaseModel):
    provider: str = ""
    status: str = ""
    ok: bool = False
    latency_ms: int = 0
    detail: str = ""


class ChatOut(BaseModel):
    ok: bool
    text: str = ""
    provider_used: str = ""
    model_used: str = ""
    source: str = "api"
    fallback_used: bool = False
    attempts: list[AttemptOut] = Field(default_factory=list)
    latency_ms: int = 0
    status: str = "available"
    error: str = ""
    error_category: str = ""
    request_id: str = ""
    structured: dict[str, object] | None = None


class WrapperOut(BaseModel):
    id: str
    name: str
    website: str
    capabilities: dict[str, bool] = Field(default_factory=dict)
    auth_mode: str = ""
    version: str = "1"
    enabled: bool = False
    fallback_priority: int = 50
    cost: str = "free"
    note: str = ""


class WrapperLibraryOut(BaseModel):
    items: list[WrapperOut]


class BrowserStatusOut(BaseModel):
    available: bool
    detail: str
    runtime: str
    docker_note: str = ""


class UseCaseOut(BaseModel):
    group: str
    id: str
    modality: str
    providers: list[str] = Field(default_factory=list)
    available: bool = False


class UseCaseMatrixOut(BaseModel):
    items: list[UseCaseOut]


class RequestRecordOut(BaseModel):
    request_id: str = ""
    provider: str = ""
    model: str = ""
    source: str = ""
    strategy: str = ""
    ok: bool = True
    fallback_used: bool = False
    attempts: int = 1
    latency_ms: int = 0
    status: str = ""
    error_category: str = ""
    at: str = ""


class RequestHistoryOut(BaseModel):
    items: list[RequestRecordOut]


class VersionedProviderDefaultsOut(BaseModel):
    providers: list[str] = Field(default_factory=list)
    message: str = ""


class ModelCapabilityOut(BaseModel):
    provider: str
    model: str
    kind: str
    source: str = "api"
    operations: list[str] = Field(default_factory=list)
    auth: str = "api_key"
    availability: str = "unknown"
    cost: str = "standard"
    verified: bool = False
    verified_operations: list[str] = Field(default_factory=list)
    note: str = ""
    params: dict[str, object] = Field(default_factory=dict)


class ModelMatrixOut(BaseModel):
    items: list[ModelCapabilityOut]
    operations: dict[str, str] = Field(default_factory=dict)


class OperationAvailabilityOut(BaseModel):
    operation: str
    title: str
    providers: list[str] = Field(default_factory=list)
    available: bool = False


class OperationAvailabilityListOut(BaseModel):
    items: list[OperationAvailabilityOut]


class PrepStepOut(BaseModel):
    id: str
    title: str
    status: str = "unknown"
    detail: str = ""


class BrowserPreflightOut(BaseModel):
    available: bool = False
    runtime: str = "playwright"
    steps: list[PrepStepOut] = Field(default_factory=list)
    install_hint: str = ""
    api_works_without_browser: bool = True
    detail: str = ""


__all__ = [
    "AttemptOut",
    "BrowserPreflightOut",
    "BrowserStatusOut",
    "CapabilityOut",
    "ChatIn",
    "ChatOut",
    "GatewayStatusOut",
    "ModelCapabilityOut",
    "ModelMatrixOut",
    "OperationAvailabilityListOut",
    "OperationAvailabilityOut",
    "PrepStepOut",
    "ProviderIn",
    "ProviderListOut",
    "ProviderOut",
    "RequestHistoryOut",
    "RequestRecordOut",
    "RouteSettingsOut",
    "RouteUpdateIn",
    "ToggleIn",
    "UseCaseMatrixOut",
    "UseCaseOut",
    "VersionedProviderDefaultsOut",
    "WrapperLibraryOut",
    "WrapperOut",
]
