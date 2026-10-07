"""AI Gateway persistence models (v1.8).

Three tables:

* :class:`AiProviderRow` — one configured provider (API, local or Web UI). The
  API key is stored **sealed** (``enc:`` Fernet token); it is never returned,
  logged or exported in the clear.
* :class:`AiRouteSetting` — gateway-level routing preferences (strategy, default
  provider, retry/timeout), kept as typed key/value rows.
* :class:`AiGatewayRequest` — a bounded ring of recent request records for the
  observability panel (requirement 19). Never stores prompt text or secrets.

Nothing here stores browser cookies or another person's session data.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiProviderRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One configured AI provider."""

    __tablename__ = "ai_providers"

    # Stable identifier used everywhere (UI, router, diagnostics).
    provider: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    # Provider kind (openai_compatible/openrouter/google/anthropic/deepseek/ollama/web).
    kind: Mapped[str] = mapped_column(String(32), default="openai_compatible", nullable=False)
    model: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # Sealed (``enc:`` Fernet token). Empty when the provider needs no key.
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Declared auth mode (no_auth/api_key/oauth/browser_session).
    auth_mode: Mapped[str] = mapped_column(String(24), default="api_key", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Cost class: free/cheap/standard/premium (a hint, never a promise).
    cost: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    # Capability flags (declared; verified separately by a probe).
    cap_text: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cap_image: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cap_file: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cap_streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cap_structured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cap_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # For Web UI wrappers: which definition in the wrapper library.
    wrapper_id: Mapped[str] = mapped_column(String(48), default="", nullable=False)
    region_status: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiProviderRow {self.provider} kind={self.kind} enabled={self.enabled}>"


class AiRouteSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A gateway routing preference (typed key/value)."""

    __tablename__ = "ai_route_settings"

    key: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), default="str", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiRouteSetting {self.key}={self.value!r}>"


class AiGatewayRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recent gateway request, for the observability panel only.

    Stores metadata (provider, model, duration, fallback, error category) and
    **never** the prompt text, attachments or any secret.
    """

    __tablename__ = "ai_gateway_requests"

    request_id: Mapped[str] = mapped_column(String(48), default="", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    strategy: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    error_category: Mapped[str] = mapped_column(String(24), default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AiGatewayRequest {self.provider} ok={self.ok} fallback={self.fallback_used}>"


__all__ = ["AiGatewayRequest", "AiProviderRow", "AiRouteSetting"]
