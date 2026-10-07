"""Web UI wrapper definitions (v1.8, requirement 17).

A wrapper drives a real browser session (the owner's own, logged in as them) and
pretends to be an ordinary API. All site-specific detail — the URL, the input and
send selectors, how to read the answer, whether it accepts an image — lives in a
:class:`WrapperDefinition`. No selector is scattered through business logic.

Nothing here tries to defeat CAPTCHA, MFA or verification, rotate identity, or
read another person's cookies. If a site demands a login the wrapper reports
``AUTH_REQUIRED`` and stops.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.ai.gateway.types import (
    AUTH_BROWSER_SESSION,
    Capability,
)


@dataclass(frozen=True, slots=True)
class WrapperStep:
    """A single browser interaction, expressed with a selector + value."""

    action: str  # "goto" | "fill" | "click" | "press" | "wait_for"
    selector: str = ""
    value: str = ""
    timeout_ms: int = 15000


@dataclass(frozen=True, slots=True)
class WrapperDefinition:
    """Everything specific to one Web UI. Versioned so drift is explicit."""

    id: str
    name: str
    website: str
    capabilities: Capability
    auth_mode: str = AUTH_BROWSER_SESSION
    #: Steps to reach a logged-in chat box from the site root.
    open_steps: tuple[WrapperStep, ...] = ()
    input_selector: str = ""
    send_selector: str = ""
    #: How to read the newest answer: a selector, and whether to take the last
    #: matching node (chat UIs append new messages).
    response_selector: str = ""
    response_take_last: bool = True
    #: Set when the wrapper can also send an image (upload input selector).
    attach_selector: str = ""
    extraction: str = "text"
    #: Markers that indicate the site is asking for a login.
    login_markers: tuple[str, ...] = ()
    version: str = "1"
    enabled: bool = False
    fallback_priority: int = 50
    cost: str = "free"
    note: str = ""

    def capability_dict(self) -> dict[str, bool]:
        c = self.capabilities
        return {
            "text": c.text,
            "image": c.image,
            "file": c.file,
            "streaming": c.streaming,
            "structured": c.structured,
        }


# ---------------------------------------------------------------------------
# Built-in library. These are *definitions only*; a wrapper is "enabled" only
# when the owner turns it on, and it is never reported available until a probe
# succeeds. Selectors are intentionally generic and marked unverified — a real
# deployment updates them per site version (requirement 18).
# ---------------------------------------------------------------------------
GENERIC_DEFINITION = WrapperDefinition(
    id="generic",
    name="Универсальная Web-обёртка",
    website="about:blank",
    capabilities=Capability(text=True, image=False, verified=False),
    auth_mode=AUTH_BROWSER_SESSION,
    input_selector="textarea, [contenteditable='true']",
    send_selector="button[type='submit']",
    response_selector="[data-message-author-role='assistant'], .message.assistant",
    extraction="text",
    login_markers=("sign in", "войти", "log in"),
    version="1",
    enabled=False,
    fallback_priority=100,
    note=(
        "Заготовка. Точные селекторы задаются в определении конкретного сайта. "
        "Работает через вашу собственную браузерную сессию."
    ),
)

#: Shipped definitions (all disabled by default; enabling requires the owner and
#: the browser runtime). They are honest templates, not working integrations
#: until a probe verifies them on the live site.
LIBRARY: tuple[WrapperDefinition, ...] = (
    GENERIC_DEFINITION,
)


def get_definition(wrapper_id: str) -> WrapperDefinition | None:
    for definition in LIBRARY:
        if definition.id == wrapper_id:
            return definition
    return None


__all__ = [
    "GENERIC_DEFINITION",
    "LIBRARY",
    "WrapperDefinition",
    "WrapperStep",
    "get_definition",
]
