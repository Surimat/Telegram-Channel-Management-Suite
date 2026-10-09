"""First-run provisioning of free AI providers (v2.0, requirement "out of the box").

On the first start the Suite already has a working AI path with **no key, no
command line and no library hunt**: the keyless Pollinations text endpoint and,
if it is running, a local Ollama. Both are ordinary registry providers, so the
router, the health store and the failover treat them exactly like a paid API.

Provisioning is *additive and idempotent*: it never overwrites a provider the
owner already configured (even one they disabled) and never changes secrets. It
is not a promise the provider works — availability is still probed live.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.ai.gateway.types import Capability


@dataclass(frozen=True, slots=True)
class FreeProviderDefault:
    """A provider the Suite can configure for the owner on first run."""

    provider: str
    kind: str
    model: str
    base_url: str
    cost: str
    capabilities: Capability
    enabled: bool
    priority: int
    note: str


#: Free-first defaults, highest priority first. Only providers that need **no
#: key and no browser** are enabled automatically; everything that needs an
#: account or a browser session stays opt-in.
FREE_PROVIDER_DEFAULTS: tuple[FreeProviderDefault, ...] = (
    FreeProviderDefault(
        provider="pollinations",
        kind="pollinations",
        model="openai-fast",
        base_url="https://text.pollinations.ai/openai",
        cost="free",
        capabilities=Capability(text=True, structured=True),
        enabled=True,
        priority=90,
        note=(
            "Бесплатный доступ без ключа (Pollinations). Только текст — без "
            "изображений и файлов. Доступность сервиса может меняться."
        ),
    ),
    FreeProviderDefault(
        provider="ollama",
        kind="ollama",
        model="llama3.2",
        base_url="http://127.0.0.1:11434/v1",
        cost="free",
        capabilities=Capability(text=True, structured=True),
        # Off by default: it only works when the owner runs Ollama locally.
        enabled=False,
        priority=80,
        note="Локальный сервер на этом компьютере (включите, когда он запущен).",
    ),
)


__all__ = ["FREE_PROVIDER_DEFAULTS", "FreeProviderDefault"]
