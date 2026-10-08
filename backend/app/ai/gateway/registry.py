"""Provider registry: build :class:`AIProvider` objects from configuration
(v1.8, requirement 2).

The registry is the single extension point: adding a provider kind means adding
one branch here, nothing else. It is *not* a claim that the provider works —
availability is probed separately. A registry entry with a broken/missing
implementation is caught by the consistency auditor and the meta-audit.

The registry is pure: it takes plain :class:`ProviderConfig` values and the
already-constructed transport/browser runtime. The service layer loads the
configuration from the database.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.ai.gateway.browser import BrowserRuntime, PlaywrightBrowserRuntime
from backend.app.ai.gateway.http import HttpTransport, HttpxTransport
from backend.app.ai.gateway.provider import AIProvider
from backend.app.ai.gateway.providers import (
    AnthropicProvider,
    DeepSeekProvider,
    GoogleProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
)
from backend.app.ai.gateway.types import Capability, SourceKind
from backend.app.ai.gateway.wrappers.definition import get_definition
from backend.app.ai.gateway.wrappers.engine import (
    GenericWebWrapperProvider,
    WebWrapperEngine,
)

# Provider kinds (requirement 2).
KIND_OPENAI = "openai_compatible"
KIND_OPENROUTER = "openrouter"
KIND_GOOGLE = "google"
KIND_ANTHROPIC = "anthropic"
KIND_DEEPSEEK = "deepseek"
KIND_OLLAMA = "ollama"
KIND_WEB = "web"

API_KINDS = (
    KIND_OPENAI,
    KIND_OPENROUTER,
    KIND_GOOGLE,
    KIND_ANTHROPIC,
    KIND_DEEPSEEK,
    KIND_OLLAMA,
)
WEB_KINDS = (KIND_WEB,)
ALL_KINDS = API_KINDS + WEB_KINDS

#: Human labels for the UI.
KIND_LABELS: dict[str, str] = {
    KIND_OPENAI: "OpenAI-совместимый API",
    KIND_OPENROUTER: "OpenRouter",
    KIND_GOOGLE: "Google (Gemini)",
    KIND_ANTHROPIC: "Anthropic (Claude)",
    KIND_DEEPSEEK: "DeepSeek",
    KIND_OLLAMA: "Локально (Ollama)",
    KIND_WEB: "Web UI обёртка",
}


@dataclass(slots=True)
class ProviderConfig:
    """One configured provider row (no secret: ``api_key`` is resolved separately)."""

    provider: str
    kind: str = KIND_OPENAI
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    enabled: bool = False
    priority: int = 0
    cost: str = ""
    capabilities: Capability | None = None
    wrapper_id: str = ""
    note: str = ""


def build_provider(
    config: ProviderConfig,
    *,
    transport: HttpTransport | None = None,
    browser_runtime: BrowserRuntime | None = None,
) -> AIProvider:
    """Return the :class:`AIProvider` for ``config`` (never raises for a gap)."""
    kind = config.kind or KIND_OPENAI
    http = transport or HttpxTransport()

    if kind == KIND_OPENROUTER:
        return OpenRouterProvider(
            model=config.model or "openrouter/auto",
            api_key=config.api_key,
            transport=http,
            cost=config.cost or "cheap",
            priority=config.priority,
        )
    if kind == KIND_GOOGLE:
        return GoogleProvider(
            model=config.model or "gemini-2.0-flash",
            api_key=config.api_key,
            transport=http,
            cost=config.cost or "cheap",
            priority=config.priority,
        )
    if kind == KIND_ANTHROPIC:
        return AnthropicProvider(
            model=config.model or "claude-3-5-haiku-latest",
            api_key=config.api_key,
            transport=http,
            cost=config.cost or "premium",
            priority=config.priority,
        )
    if kind == KIND_DEEPSEEK:
        return DeepSeekProvider(
            model=config.model or "deepseek-chat",
            api_key=config.api_key,
            transport=http,
            cost=config.cost or "cheap",
            priority=config.priority,
        )
    if kind == KIND_OLLAMA:
        return OllamaProvider(
            model=config.model or "llama3.2",
            base_url=config.base_url or "http://127.0.0.1:11434/v1",
            transport=http,
            api_key=config.api_key,
            priority=config.priority,
        )
    if kind == KIND_WEB:
        definition = get_definition(config.wrapper_id or "generic")
        runtime = browser_runtime or PlaywrightBrowserRuntime()
        unknown_id = definition is None
        if unknown_id:
            # Unknown wrapper id: yield a placeholder the auditor can inspect, but
            # never let it report AVAILABLE — a wrapper whose definition is missing
            # cannot honestly run. It is forced disabled with an explicit reason.
            from backend.app.ai.gateway.wrappers.definition import GENERIC_DEFINITION

            definition = GENERIC_DEFINITION
        engine = WebWrapperEngine(runtime)
        # A wrapper can also carry files when its definition declares an upload
        # selector; the capability is derived from the definition, never claimed.
        capabilities = definition.capabilities
        if definition.attach_file_selector and not capabilities.file:
            from dataclasses import replace

            capabilities = replace(capabilities, file=True)
        return GenericWebWrapperProvider(
            definition=definition,
            engine=engine,
            enabled=config.enabled and not unknown_id,
            # Keep the configured identity so a pinned provider name still routes
            # (the wrapper's ``web:<id>`` label is only a fallback).
            configured_name=config.provider,
            capabilities=capabilities,
            note=(
                f"Определение обёртки «{config.wrapper_id}» не найдено."
                if unknown_id
                else ""
            ),
        )
    # Default: generic OpenAI-compatible endpoint.
    return OpenAICompatibleProvider(
        provider=config.provider or "openai_compatible",
        model=config.model,
        base_url=config.base_url or "https://api.openai.com/v1",
        api_key=config.api_key,
        transport=http,
        capabilities=config.capabilities,
        cost=config.cost or "standard",
        priority=config.priority,
        note=config.note,
    )


def build_registry(
    configs: list[ProviderConfig],
    *,
    transport: HttpTransport | None = None,
    browser_runtime: BrowserRuntime | None = None,
) -> list[AIProvider]:
    """Build every enabled provider. Disabled rows are skipped."""
    out: list[AIProvider] = []
    for config in configs:
        if not config.enabled:
            continue
        out.append(
            build_provider(
                config, transport=transport, browser_runtime=browser_runtime
            )
        )
    return out


def source_for_kind(kind: str) -> str:
    return SourceKind.WEB if kind in WEB_KINDS else SourceKind.API


__all__ = [
    "ALL_KINDS",
    "API_KINDS",
    "KIND_ANTHROPIC",
    "KIND_DEEPSEEK",
    "KIND_GOOGLE",
    "KIND_LABELS",
    "KIND_OLLAMA",
    "KIND_OPENAI",
    "KIND_OPENROUTER",
    "KIND_WEB",
    "WEB_KINDS",
    "ProviderConfig",
    "build_provider",
    "build_registry",
    "source_for_kind",
]
