"""Web Wrapper Engine (v1.8, requirements 4/5/6/7/18).

Drives a :class:`BrowserRuntime` through a :class:`WrapperDefinition` pipeline:

    request → open site → (login check) → fill prompt → send → extract → normalize

It is the single place that knows how to execute a wrapper. Each site is just a
definition; the engine never grows per-site branches. Failures are classified:

* no browser runtime → :class:`BrowserUnavailableError` (``unavailable``).
* a login wall → :class:`ProviderAuthRequiredError` (``auth_required``).
* a selector that no longer matches → :class:`WrapperSelectorError`
  (``wrapper_selector``) so the provider is marked *degraded* and the router
  moves on (requirement 18).

The engine uses only the owner's own browser profile and never attempts to defeat
CAPTCHA/MFA/verification or to evade regional blocks.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.ai.gateway.browser import BrowserRuntime, PageSnapshot
from backend.app.ai.gateway.errors import (
    BrowserUnavailableError,
    WrapperSelectorError,
)
from backend.app.ai.gateway.types import (
    AUTH_NONE,
    MODALITY_FILE,
    MODALITY_IMAGE,
    STATUS_AVAILABLE,
    ChatRequest,
    ChatResponse,
    SourceKind,
)
from backend.app.ai.gateway.wrappers.definition import WrapperDefinition


def _items_to_text(items: list[dict[str, object]]) -> str:
    """Flatten structured records into a normalized text block (deterministic)."""
    lines: list[str] = []
    for item in items:
        text = str(item.get("text", "")).strip()
        href = str(item.get("href", "")).strip()
        if href and href not in text:
            lines.append(f"{text} — {href}" if text else href)
        elif text:
            lines.append(text)
    return "\n".join(lines)


@dataclass(slots=True)
class WrapperRun:
    """The outcome of one wrapper execution, before it becomes a ChatResponse."""

    ok: bool
    text: str = ""
    login_required: bool = False
    selector_error: bool = False
    detail: str = ""
    #: Structured records when the definition asks for ``extraction="structured"``.
    items: list[dict[str, object]] | None = None


class WebWrapperEngine:
    """Executes wrapper definitions on a browser runtime."""

    def __init__(self, runtime: BrowserRuntime) -> None:
        self.runtime = runtime

    def available(self) -> bool:
        return bool(self.runtime.available)

    def availability_detail(self) -> str:
        return self.runtime.availability_detail()

    def _check_login(self, definition: WrapperDefinition, snap: PageSnapshot) -> bool:
        if snap.login_detected:
            return True
        if not definition.login_markers:
            return False
        haystack = f"{snap.title}\n{snap.text}".lower()
        return any(marker.lower() in haystack for marker in definition.login_markers)

    async def run(
        self, definition: WrapperDefinition, request: ChatRequest
    ) -> WrapperRun:
        if not self.runtime.available:
            raise BrowserUnavailableError()
        prompt = request.text()
        try:
            snap = await self.runtime.open(definition.website)
            for step in definition.open_steps:
                if step.action == "goto":
                    snap = await self.runtime.open(step.value or definition.website)
                elif step.action == "fill":
                    snap = await self.runtime.fill(
                        step.selector, step.value, timeout_ms=step.timeout_ms
                    )
                elif step.action == "click":
                    snap = await self.runtime.click(step.selector, timeout_ms=step.timeout_ms)
                elif step.action == "press":
                    snap = await self.runtime.press(
                        step.selector, step.value, timeout_ms=step.timeout_ms
                    )
                elif step.action == "wait_for":
                    snap = await self.runtime.wait_for(
                        step.selector, timeout_ms=step.timeout_ms
                    )
            if self._check_login(definition, snap):
                return WrapperRun(
                    ok=False,
                    login_required=True,
                    detail="Сайт требует входа. Войдите в своей браузерной сессии.",
                )
            # Attach the caller's own files: images via ``attach_selector``, other
            # files via ``attach_file_selector``. Nothing is fetched from a third
            # party; only the owner's provided data is uploaded (v2.0 multimodal).
            for msg in request.messages:
                for att in msg.attachments:
                    if not att.reference:
                        continue
                    if att.kind == MODALITY_IMAGE and definition.attach_selector:
                        await self.runtime.fill(definition.attach_selector, att.reference)
                    elif att.kind == MODALITY_FILE and definition.attach_file_selector:
                        await self.runtime.fill(
                            definition.attach_file_selector, att.reference
                        )
            if definition.input_selector:
                snap = await self.runtime.fill(definition.input_selector, prompt)
            if definition.send_selector:
                snap = await self.runtime.click(definition.send_selector)
            elif definition.input_selector:
                snap = await self.runtime.press(definition.input_selector, "Enter")
            if definition.extraction == "structured" and definition.response_selector:
                # Read structured records (links/rows/cards) the owner asked for.
                snap = await self.runtime.extract(
                    definition.response_selector, attrs=definition.extract_attrs
                )
                items = list(snap.items)
                text = _items_to_text(items)
                if not items:
                    return WrapperRun(
                        ok=False,
                        selector_error=True,
                        detail="Не удалось прочитать структуру (селектор не найден).",
                    )
                return WrapperRun(ok=True, text=text, items=items)
            if definition.response_selector:
                snap = await self.runtime.read(
                    definition.response_selector,
                    take_last=definition.response_take_last,
                )
            text = snap.response_text or snap.text
            if not text:
                return WrapperRun(
                    ok=False,
                    selector_error=True,
                    detail="Не удалось прочитать ответ (селектор не найден).",
                )
            return WrapperRun(ok=True, text=text.strip())
        except BrowserUnavailableError:
            raise
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "timeout" in name:
                raise WrapperSelectorError(
                    "Браузер не дождался элемента (возможно, интерфейс изменился)."
                ) from exc
            raise WrapperSelectorError(
                "Ошибка выполнения в браузере: интерфейс сайта мог измениться."
            ) from exc


class GenericWebWrapperProvider:
    """A wrapper provider: pretends to be an ordinary AI API (requirement 5)."""

    def __init__(
        self,
        *,
        definition: WrapperDefinition,
        engine: WebWrapperEngine,
        enabled: bool = False,
        configured_name: str = "",
        capabilities: object | None = None,
        note: str = "",
    ) -> None:
        self.definition = definition
        self.engine = engine
        self.enabled = enabled
        from backend.app.ai.gateway.types import ProviderInfo

        # The configured provider name wins when present so a pinned provider
        # still routes; ``web:<id>`` is only a fallback label.
        name = configured_name or f"web:{definition.id}"
        self._info = ProviderInfo(
            provider=name,
            model=f"{definition.name} v{definition.version}",
            source=SourceKind.WEB,
            capabilities=capabilities or definition.capabilities,
            auth_mode=definition.auth_mode or AUTH_NONE,
            auth_required=definition.auth_mode not in ("", AUTH_NONE),
            cost=definition.cost,
            priority=definition.fallback_priority,
            note=note or definition.note,
        )

    @property
    def name(self) -> str:
        return self._info.provider

    @property
    def info(self):
        return self._info

    def availability(self):
        from backend.app.ai.gateway.types import Availability

        if not self.enabled:
            # Prefer an explicit reason (e.g. a missing wrapper definition) over
            # the generic "disabled by owner" so the UI never misleads.
            detail = self._info.note or "Wrapper выключен владельцем."
            return Availability(status="unavailable", detail=detail)
        if not self.engine.available():
            return Availability(
                status="unavailable", detail=self.engine.availability_detail()
            )
        return Availability(status=STATUS_AVAILABLE)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        from backend.app.ai.gateway.errors import GatewayError

        if not self.enabled:
            return ChatResponse(
                ok=False,
                provider_used=self.name,
                model_used=self._info.model,
                source=SourceKind.WEB,
                error="Wrapper выключен.",
                error_category="unavailable",
                request_id=request.correlation_id,
                status="unavailable",
            )
        try:
            run = await self.engine.run(self.definition, request)
        except GatewayError as exc:
            return ChatResponse(
                ok=False,
                provider_used=self.name,
                model_used=self._info.model,
                source=SourceKind.WEB,
                error=exc.message,
                error_category=exc.category,
                request_id=request.correlation_id,
                status="auth_required" if exc.category == "auth_required" else "unavailable",
            )
        if run.ok:
            structured = None
            if run.items is not None:
                structured = {
                    "kind": "extraction",
                    "items": run.items,
                }
            return ChatResponse(
                ok=True,
                text=run.text,
                provider_used=self.name,
                model_used=self._info.model,
                source=SourceKind.WEB,
                request_id=request.correlation_id,
                status=STATUS_AVAILABLE,
                structured=structured,
            )
        if run.login_required:
            return ChatResponse(
                ok=False,
                provider_used=self.name,
                model_used=self._info.model,
                source=SourceKind.WEB,
                error="Требуется вход в браузерную сессию.",
                error_category="auth_required",
                request_id=request.correlation_id,
                status="auth_required",
            )
        return ChatResponse(
            ok=False,
            provider_used=self.name,
            model_used=self._info.model,
            source=SourceKind.WEB,
            error=run.detail or "Wrapper не смог прочитать ответ.",
            error_category="wrapper_selector" if run.selector_error else "error",
            request_id=request.correlation_id,
            status="unavailable",
        )

    async def close(self) -> None:
        return None


__all__ = ["GenericWebWrapperProvider", "WebWrapperEngine", "WrapperRun"]
