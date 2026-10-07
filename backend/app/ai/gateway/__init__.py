"""AI Gateway (v1.8): one access layer over API providers, local models and
Web UI wrappers.

This package is **pure domain logic**: it imports no FastAPI, SQLAlchemy or
Telegram code (the same invariant as the rest of ``backend/app/ai``). The
service layer (``services/ai_gateway_service.py``) wires it to the database and
DI; the API layer exposes it.

Nothing here registers accounts, bypasses CAPTCHA/MFA/verification, evades
regional blocks, or obtains/handles other people's cookies or sessions. A Web UI
wrapper only drives a browser session the owner already controls.
"""

from __future__ import annotations

from backend.app.ai.gateway.errors import (
    GatewayError,
    ProviderAuthRequiredError,
    ProviderRegionBlockedError,
    ProviderUnavailableError,
)
from backend.app.ai.gateway.types import (
    AUTH_API_KEY,
    AUTH_BROWSER_SESSION,
    AUTH_NONE,
    AUTH_OAUTH,
    MODALITY_FILE,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    STATUS_AUTH_REQUIRED,
    STATUS_AVAILABLE,
    STATUS_NETWORK_ERROR,
    STATUS_RATE_LIMITED,
    STATUS_REGION_BLOCKED,
    STATUS_UNAVAILABLE,
    STATUS_UNKNOWN,
    Availability,
    Capability,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ProviderInfo,
    ProviderStatus,
    SourceKind,
)

__all__ = [
    "AUTH_API_KEY",
    "AUTH_BROWSER_SESSION",
    "AUTH_NONE",
    "AUTH_OAUTH",
    "MODALITY_FILE",
    "MODALITY_IMAGE",
    "MODALITY_TEXT",
    "STATUS_AUTH_REQUIRED",
    "STATUS_AVAILABLE",
    "STATUS_NETWORK_ERROR",
    "STATUS_RATE_LIMITED",
    "STATUS_REGION_BLOCKED",
    "STATUS_UNAVAILABLE",
    "STATUS_UNKNOWN",
    "Availability",
    "Capability",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "GatewayError",
    "ProviderAuthRequiredError",
    "ProviderInfo",
    "ProviderRegionBlockedError",
    "ProviderStatus",
    "ProviderUnavailableError",
    "SourceKind",
]
