"""Core value objects for the AI Gateway (v1.8).

Everything a caller (the router, the service, the API, the UI) needs to describe
*what* it wants and *what actually happened* lives here. The types are frozen
where they describe facts (capabilities, availability, a provider's info) and
plain dataclasses where they are built up request by request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceKind(StrEnum):
    """Where a provider actually runs."""

    LOCAL = "local"  # a model on this computer (Ollama, GGUF)
    API = "api"  # a remote HTTP API
    WEB = "web"  # a Web UI wrapper driven through a real browser


#: Auth modes (requirement 7). A provider states which one it needs.
AUTH_NONE = "no_auth"
AUTH_API_KEY = "api_key"
AUTH_OAUTH = "oauth"
AUTH_BROWSER_SESSION = "browser_session"

#: Modalities a provider may support (requirement 11).
MODALITY_TEXT = "text"
MODALITY_IMAGE = "image"
MODALITY_FILE = "file"

#: Availability states (requirement 8). Never claim more than was observed.
STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_AUTH_REQUIRED = "auth_required"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_NETWORK_ERROR = "network_error"
STATUS_REGION_BLOCKED = "region_blocked"
STATUS_UNKNOWN = "unknown"

#: Transport-level statuses an API call may report (subset used by adapters).
CALL_OK = "ok"
CALL_TIMEOUT = "timeout"
CALL_AUTH_REQUIRED = "auth_required"
CALL_RATE_LIMITED = "rate_limited"
CALL_REGION_BLOCKED = "region_blocked"
CALL_NETWORK_ERROR = "network_error"
CALL_BAD_REQUEST = "bad_request"
CALL_ERROR = "error"

#: Which failure categories are worth retrying on a *different* provider.
FALLBACK_STATUSES = frozenset(
    {
        STATUS_UNAVAILABLE,
        STATUS_NETWORK_ERROR,
        STATUS_RATE_LIMITED,
        STATUS_REGION_BLOCKED,
    }
)


@dataclass(frozen=True, slots=True)
class Capability:
    """What a provider can really do.

    A Web UI that only sends text must report ``image=False``/``file=False``. A
    capability is a claim; the router trusts it only after a provider reported
    it as *verified* (``verified`` is False by default, and a wrapper's
    capabilities are marked verified only after a successful probe).
    """

    text: bool = False
    image: bool = False
    file: bool = False
    streaming: bool = False
    structured: bool = False
    #: True when the provider has actually demonstrated this capability.
    verified: bool = False

    def supports(self, modality: str) -> bool:
        if modality == MODALITY_IMAGE:
            return self.image
        if modality == MODALITY_FILE:
            return self.file
        return self.text

    def at_least(self, other: Capability) -> bool:
        """True when ``self`` covers every modality ``other`` requires."""
        for modality in (MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE):
            if getattr(other, modality, False) and not getattr(self, modality, False):
                return False
        if other.structured and not self.structured:
            return False
        return not (other.streaming and not self.streaming)


@dataclass(frozen=True, slots=True)
class Availability:
    """Observed availability of a provider at a point in time."""

    status: str = STATUS_UNKNOWN
    detail: str = ""
    #: Honest recommendation when the state is network/region related.
    check_network: bool = False

    @property
    def usable(self) -> bool:
        return self.status == STATUS_AVAILABLE

    @property
    def fallback_worthy(self) -> bool:
        return self.status in FALLBACK_STATUSES


@dataclass(slots=True)
class ProviderInfo:
    """Static description of a provider, independent of any live call."""

    provider: str
    model: str = ""
    source: str = SourceKind.API
    capabilities: Capability = field(default_factory=Capability)
    auth_mode: str = AUTH_NONE
    auth_required: bool = False
    #: Cost class: "free", "cheap", "standard", "premium" (never a promise).
    cost: str = "standard"
    region_status: str = ""
    note: str = ""
    #: Higher runs first within the same strategy tier (default 0).
    priority: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "source": self.source,
            "capabilities": {
                "text": self.capabilities.text,
                "image": self.capabilities.image,
                "file": self.capabilities.file,
                "streaming": self.capabilities.streaming,
                "structured": self.capabilities.structured,
                "verified": self.capabilities.verified,
            },
            "auth_mode": self.auth_mode,
            "auth_required": self.auth_required,
            "cost": self.cost,
            "region_status": self.region_status,
            "note": self.note,
            "priority": self.priority,
        }


@dataclass(slots=True)
class ProviderStatus:
    """A provider's live health snapshot (requirement 14/19)."""

    provider: str
    availability: Availability = field(default_factory=Availability)
    latency_ms: int = 0
    last_error: str = ""
    last_success: str = ""
    failure_count: int = 0
    cooldown_until: float = 0.0
    enabled: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "status": self.availability.status,
            "detail": self.availability.detail,
            "check_network": self.availability.check_network,
            "latency_ms": self.latency_ms,
            "last_error": self.last_error,
            "last_success": self.last_success,
            "failure_count": self.failure_count,
            "cooldown_until": self.cooldown_until,
            "enabled": self.enabled,
        }


@dataclass(slots=True)
class Attachment:
    """An image or document part of a request (never a raw secret)."""

    kind: str = MODALITY_IMAGE  # MODALITY_IMAGE | MODALITY_FILE
    #: A local path or an opaque reference the caller owns.
    reference: str = ""
    mime: str = ""
    #: Inline base64 is allowed only for small images the caller already holds.
    data_b64: str = ""
    filename: str = ""


@dataclass(slots=True)
class ChatMessage:
    role: str = "user"  # system | user | assistant
    content: str = ""
    attachments: list[Attachment] = field(default_factory=list)


@dataclass(slots=True)
class ChatRequest:
    """One request to the gateway, provider-agnostic."""

    messages: list[ChatMessage] = field(default_factory=list)
    #: Desired output modality / features.
    requires: Capability = field(
        default_factory=lambda: Capability(text=True)
    )
    #: Routing strategy (see router.py). Empty = the configured default.
    strategy: str = ""
    #: Preferred provider name, when the owner pinned one.
    provider: str = ""
    #: Hint for a capability class the router should look for.
    task: str = ""
    max_tokens: int = 512
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    #: When True the caller wants a structured (JSON) answer.
    structured: bool = False
    #: Stable caller id so the health store can correlate retries.
    correlation_id: str = ""

    def text(self) -> str:
        return "\n".join(m.content for m in self.messages if m.content).strip()

    def modality(self) -> str:
        if self.requires.image or any(
            a.kind == MODALITY_IMAGE for m in self.messages for a in m.attachments
        ):
            return MODALITY_IMAGE
        if self.requires.file or any(
            a.kind == MODALITY_FILE for m in self.messages for a in m.attachments
        ):
            return MODALITY_FILE
        return MODALITY_TEXT


@dataclass(slots=True)
class ChatResponse:
    """The normalized result, whatever provider(s) produced it (requirement 9)."""

    ok: bool
    text: str = ""
    provider_used: str = ""
    model_used: str = ""
    source: str = SourceKind.API
    fallback_used: bool = False
    attempts: list[dict[str, object]] = field(default_factory=list)
    latency_ms: int = 0
    #: Optional structured payload when ``structured`` was requested.
    structured: dict[str, object] | None = None
    error: str = ""
    error_category: str = ""
    request_id: str = ""
    status: str = STATUS_AVAILABLE

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "text": self.text,
            "provider_used": self.provider_used,
            "model_used": self.model_used,
            "source": self.source,
            "fallback_used": self.fallback_used,
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "structured": self.structured,
            "error": self.error,
            "error_category": self.error_category,
            "request_id": self.request_id,
            "status": self.status,
        }
