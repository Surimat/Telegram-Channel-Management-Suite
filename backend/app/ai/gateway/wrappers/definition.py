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
    #: Set when the wrapper can also send a file (upload input selector).
    attach_file_selector: str = ""
    extraction: str = "text"
    #: Attribute names to read for each structured record (extraction="structured").
    extract_attrs: tuple[str, ...] = ("href",)
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

#: v2.0: free web-UI backup templates. They are honest templates — disabled and
#: unverified until the owner enables them and a probe succeeds on the live site.
#: They drive the owner's own logged-in browser session and never bypass a login
#: wall, CAPTCHA/MFA, a regional block or any rate limit.
_CHATGPT_DEFINITION = WrapperDefinition(
    id="chatgpt",
    name="ChatGPT (web UI)",
    website="https://chatgpt.com/",
    capabilities=Capability(text=True, image=True, verified=False),
    auth_mode=AUTH_BROWSER_SESSION,
    input_selector="#prompt-textarea, textarea[data-id]",
    send_selector="button[data-testid='send-button']",
    response_selector="[data-message-author-role='assistant']",
    response_take_last=True,
    attach_selector="input[type='file']",
    attach_file_selector="input[type='file']",
    login_markers=("log in", "войти", "sign up"),
    version="1",
    enabled=False,
    fallback_priority=60,
    cost="free",
    note=(
        "Резервный бесплатный путь через вашу браузерную сессию ChatGPT. "
        "Селекторы могут меняться — обновляйте определение при изменении сайта."
    ),
)

_GEMINI_DEFINITION = WrapperDefinition(
    id="gemini",
    name="Google Gemini (web UI)",
    website="https://gemini.google.com/app",
    capabilities=Capability(text=True, image=True, verified=False),
    auth_mode=AUTH_BROWSER_SESSION,
    input_selector="rich-textarea [contenteditable='true'], .ql-editor",
    send_selector="button.send-button",
    response_selector="message-content, .model-response-text",
    response_take_last=True,
    attach_selector="input[type='file']",
    attach_file_selector="input[type='file']",
    login_markers=("sign in", "войти"),
    version="1",
    enabled=False,
    fallback_priority=65,
    cost="free",
    note=(
        "Резервный бесплатный путь через вашу браузерную сессию Google Gemini. "
        "Требуется вход владельца; ничего не обходится автоматически."
    ),
)

_COPILOT_DEFINITION = WrapperDefinition(
    id="copilot",
    name="Microsoft Copilot (web UI)",
    website="https://copilot.microsoft.com/",
    capabilities=Capability(text=True, image=True, verified=False),
    auth_mode=AUTH_BROWSER_SESSION,
    input_selector="textarea, [contenteditable='true']",
    send_selector="button[title*='Submit'], button[aria-label*='Submit']",
    response_selector="[data-content='ai-message'], .ai-message, [class*='message']",
    response_take_last=True,
    attach_selector="input[type='file']",
    login_markers=("sign in", "войти", "sign up"),
    version="1",
    enabled=False,
    fallback_priority=70,
    cost="free",
    note=(
        "Резервный бесплатный путь через вашу браузерную сессию Microsoft "
        "Copilot. Требуется вход владельца; ничего не обходится автоматически."
    ),
)

#: Duck.ai (DuckDuckGo Chat). Keyless, but the backend answers with an
#: anti-bot JS challenge for automated clients — the wrapper drives a real
#: logged-in browser and NEVER solves or bypasses that challenge. When the
#: challenge appears the engine reports ``auth_required``/``selector`` honestly.
_DUCKAI_DEFINITION = WrapperDefinition(
    id="duckai",
    name="Duck.ai (DuckDuckGo Chat)",
    website="https://duck.ai/",
    capabilities=Capability(text=True, verified=False),
    auth_mode=AUTH_BROWSER_SESSION,
    input_selector="textarea, [contenteditable='true']",
    send_selector="button[type='submit'], button[aria-label*='Send']",
    response_selector="[data-testid='chat-message'], .chat-message, article",
    response_take_last=True,
    login_markers=("enable javascript", "unusual traffic", "captcha"),
    version="1",
    enabled=False,
    fallback_priority=75,
    cost="free",
    note=(
        "Бесплатно и без ключа, но бэкенд защищён анти-бот проверкой. Обёртка "
        "работает только через вашу браузерную сессию и НЕ обходит проверку; "
        "при её появлении честно сообщает о требовании входа."
    ),
)

#: Shipped definitions (all disabled by default; enabling requires the owner and
#: the browser runtime). They are honest templates, not working integrations
#: until a probe verifies them on the live site.
LIBRARY: tuple[WrapperDefinition, ...] = (
    GENERIC_DEFINITION,
    _CHATGPT_DEFINITION,
    _GEMINI_DEFINITION,
    _COPILOT_DEFINITION,
    _DUCKAI_DEFINITION,
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
