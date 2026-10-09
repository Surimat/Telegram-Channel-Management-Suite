"""API-backed AI providers (v1.8, requirement 2).

Every adapter satisfies :class:`~backend.app.ai.gateway.provider.AIProvider` and
talks HTTP only through the injected transport, so CI runs with no network and no
credentials. An adapter maps transport failures to the shared availability
statuses and never echoes a key.

Providers:
* :class:`OpenAICompatibleProvider` — any ``/chat/completions`` endpoint (also
  the base for OpenRouter, DeepSeek and local Ollama's OpenAI mode).
* :class:`AnthropicProvider` — the Messages API.
* :class:`GoogleProvider` — the Gemini ``generateContent`` API.
* :class:`FakeProvider` — a deterministic in-process provider for tests/offline.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any
from urllib.parse import quote

from backend.app.ai.gateway.errors import (
    GatewayError,
    ProviderAuthRequiredError,
    ProviderRateLimitedError,
    ProviderRegionBlockedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from backend.app.ai.gateway.http import HttpResponse, HttpTransport
from backend.app.ai.gateway.types import (
    AUTH_API_KEY,
    AUTH_NONE,
    CALL_AUTH_REQUIRED,
    CALL_BAD_REQUEST,
    CALL_ERROR,
    CALL_NETWORK_ERROR,
    CALL_RATE_LIMITED,
    CALL_REGION_BLOCKED,
    CALL_TIMEOUT,
    MODALITY_IMAGE,
    STATUS_AUTH_REQUIRED,
    STATUS_AVAILABLE,
    STATUS_NETWORK_ERROR,
    STATUS_RATE_LIMITED,
    STATUS_REGION_BLOCKED,
    STATUS_UNAVAILABLE,
    STATUS_UNKNOWN,
    Availability,
    Capability,
    ChatRequest,
    ChatResponse,
    ProviderInfo,
    SourceKind,
)


def _classify_http(status: int, body: str) -> tuple[str, str]:
    """Map an HTTP status/body to (availability status, short detail)."""
    if status in (401, 403):
        return STATUS_AUTH_REQUIRED, "Требуется авторизация (ключ или доступ)."
    if status == 429:
        return STATUS_RATE_LIMITED, "Сервис просит снизить частоту запросов."
    if status in (451,):
        return STATUS_REGION_BLOCKED, "Сервис недоступен из этого региона."
    if status == 400:
        return STATUS_AVAILABLE, f"Некорректный запрос: {body[:120]}"
    if status >= 500:
        return STATUS_NETWORK_ERROR, "Сервис вернул ошибку сервера."
    return STATUS_NETWORK_ERROR, f"HTTP {status}"


def _raise_for_response(resp: HttpResponse, provider: str) -> None:
    if resp.error:
        if resp.timed_out:
            raise ProviderTimeoutError(provider=provider)
        raise ProviderUnavailableError(
            "Не удалось подключиться к провайдеру.",
            provider=provider,
            how_to_fix="Проверьте сетевой доступ и адрес провайдера.",
        )
    if resp.status in (401, 403):
        raise ProviderAuthRequiredError(
            "Провайдер требует авторизацию.", provider=provider
        )
    if resp.status == 429:
        raise ProviderRateLimitedError("Слишком много запросов.", provider=provider)
    if resp.status == 451:
        raise ProviderRegionBlockedError(
            "Провайдер заблокирован в этом регионе.", provider=provider
        )


class _BaseApiProvider:
    """Shared plumbing for HTTP providers."""

    source = SourceKind.API
    auth_mode = AUTH_API_KEY

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str = "",
        transport: HttpTransport,
        capabilities: Capability | None = None,
        cost: str = "standard",
        priority: int = 0,
        note: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._name = provider
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport
        self._extra_headers = extra_headers or {}
        self._caps = capabilities or Capability(text=True)
        self._info = ProviderInfo(
            provider=provider,
            model=model,
            source=self.source,
            capabilities=self._caps,
            auth_mode=self.auth_mode,
            auth_required=bool(api_key) is False,
            cost=cost,
            priority=priority,
            note=note,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def info(self) -> ProviderInfo:
        # Auth is required only for an api-key provider that has no key. A
        # keyless provider (Ollama, Pollinations) or a browser-session provider
        # must never report itself as requiring a key.
        return replace(
            self._info,
            auth_required=self.auth_mode == AUTH_API_KEY and not self._api_key,
        )

    def availability(self) -> Availability:
        if self.auth_mode == AUTH_API_KEY and not self._api_key:
            return Availability(
                status=STATUS_AUTH_REQUIRED,
                detail="Не указан ключ доступа.",
            )
        return Availability(status=STATUS_AVAILABLE)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def chat(self, request: ChatRequest) -> ChatResponse:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        return None

    def _error_response(self, exc: GatewayError, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            ok=False,
            provider_used=self._name,
            model_used=self._model,
            source=self.source,
            error=exc.message,
            error_category=exc.category,
            request_id=request.correlation_id,
            status=_category_to_status(exc.category),
        )


def _category_to_status(category: str) -> str:
    return {
        CALL_AUTH_REQUIRED: STATUS_AUTH_REQUIRED,
        CALL_RATE_LIMITED: STATUS_RATE_LIMITED,
        CALL_REGION_BLOCKED: STATUS_REGION_BLOCKED,
        CALL_TIMEOUT: STATUS_NETWORK_ERROR,
        CALL_NETWORK_ERROR: STATUS_NETWORK_ERROR,
        CALL_BAD_REQUEST: STATUS_AVAILABLE,
        CALL_ERROR: STATUS_UNKNOWN,
    }.get(category, STATUS_UNKNOWN)


def _openai_messages(request: ChatRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in request.messages:
        if msg.attachments:
            parts: list[dict[str, Any]] = []
            if msg.content:
                parts.append({"type": "text", "text": msg.content})
            for att in msg.attachments:
                if att.kind == MODALITY_IMAGE:
                    url = att.data_b64 or att.reference
                    parts.append({"type": "image_url", "image_url": {"url": url}})
                else:
                    parts.append(
                        {"type": "text", "text": f"[файл: {att.filename or att.reference}]"}
                    )
            out.append({"role": msg.role, "content": parts})
        else:
            out.append({"role": msg.role, "content": msg.content})
    return out


class OpenAICompatibleProvider(_BaseApiProvider):
    """Any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        provider: str = "openai_compatible",
        model: str = "",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        transport: HttpTransport,
        capabilities: Capability | None = None,
        cost: str = "standard",
        priority: int = 0,
        note: str = "",
    ) -> None:
        super().__init__(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            capabilities=capabilities
            or Capability(text=True, image=True, streaming=True, structured=True),
            cost=cost,
            priority=priority,
            note=note,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": request.provider or self._model,
            "messages": _openai_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.structured:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = await self._transport.post_json(
                f"{self._base_url}/chat/completions",
                payload,
                headers=self._headers(),
                timeout=request.timeout_seconds,
            )
            _raise_for_response(resp, self._name)
        except GatewayError as exc:
            return self._error_response(exc, request)
        data = resp.json() or {}
        text = ""
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                error="Пустой ответ провайдера.",
                error_category=CALL_ERROR,
                request_id=request.correlation_id,
                status=STATUS_NETWORK_ERROR,
            )
        return ChatResponse(
            ok=True,
            text=text,
            provider_used=self._name,
            model_used=self._model,
            source=self.source,
            request_id=request.correlation_id,
            status=STATUS_AVAILABLE,
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter (OpenAI-compatible with attribution headers)."""

    def __init__(
        self,
        *,
        model: str = "openrouter/auto",
        api_key: str = "",
        transport: HttpTransport,
        base_url: str = "https://openrouter.ai/api/v1",
        cost: str = "cheap",
        priority: int = 0,
    ) -> None:
        super().__init__(
            provider="openrouter",
            model=model,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            capabilities=Capability(
                text=True, image=True, streaming=True, structured=True
            ),
            cost=cost,
            priority=priority,
            note="Агрегатор моделей; условия и цены задаёт сам сервис.",
        )
        self._extra_headers = {
            "HTTP-Referer": "https://github.com/Surimat/Telegram-Channel-Management-Suite",
            "X-Title": "Telegram Channel Management Suite",
        }


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek (OpenAI-compatible)."""

    def __init__(
        self,
        *,
        model: str = "deepseek-chat",
        api_key: str = "",
        transport: HttpTransport,
        base_url: str = "https://api.deepseek.com/v1",
        cost: str = "cheap",
        priority: int = 0,
    ) -> None:
        super().__init__(
            provider="deepseek",
            model=model,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            capabilities=Capability(text=True, streaming=True, structured=True),
            cost=cost,
            priority=priority,
        )


class PollinationsProvider(OpenAICompatibleProvider):
    """Keyless free text endpoint (Pollinations, v2.0).

    No API key and no account: it is the "works out of the box" free-first
    provider. It is **text only** — a request carrying an image/file is refused
    honestly (the upstream model does not support image input), so the router
    falls over to a vision-capable provider instead of pretending.
    """

    def __init__(
        self,
        *,
        model: str = "openai-fast",
        transport: HttpTransport,
        base_url: str = "https://text.pollinations.ai/openai",
        cost: str = "free",
        priority: int = 90,
    ) -> None:
        super().__init__(
            provider="pollinations",
            model=model,
            base_url=base_url,
            api_key="",
            transport=transport,
            capabilities=Capability(text=True, structured=True),
            cost=cost,
            priority=priority,
            note=(
                "Бесплатный доступ без ключа. Только текст — без изображений и "
                "файлов. Доступность сервиса может меняться."
            ),
        )
        # A keyless provider must never require auth.
        self.auth_mode = AUTH_NONE
        self._info = replace(
            self._info, auth_mode=AUTH_NONE, auth_required=False, cost="free"
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.modality() != "text":
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                source=self.source,
                error=(
                    "Бесплатный текстовый провайдер не принимает изображения или "
                    "файлы. Выбран другой совместимый провайдер."
                ),
                error_category=CALL_BAD_REQUEST,
                request_id=request.correlation_id,
                status=STATUS_UNAVAILABLE,
            )
        return await super().chat(request)


class Llm7Provider(OpenAICompatibleProvider):
    """llm7.io — a keyless, community-run OpenAI-compatible gateway (v2.0).

    Anonymous chat is accepted (no key, no account). Many catalogue models need a
    key or are temporarily unavailable, so only a small, explicitly keyless model
    set is ever used; anything else honestly returns ``auth_required`` and the
    router fails over. It is a *best-effort* free path, never a critical
    dependency. The catalogue model list does **not** confirm vision for the
    keyless models (a real image request was refused upstream), so this provider
    declares text-only.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-oss:20b",
        transport: HttpTransport,
        base_url: str = "https://api.llm7.io/v1",
        cost: str = "free",
        priority: int = 85,
    ) -> None:
        super().__init__(
            provider="llm7",
            model=model,
            base_url=base_url,
            api_key="",
            transport=transport,
            capabilities=Capability(text=True, structured=True),
            cost=cost,
            priority=priority,
            note=(
                "Бесплатный шлюз без ключа (llm7.io, gpt-oss:20b). Только текст; "
                "модели и доступность меняются без предупреждения."
            ),
        )
        self.auth_mode = AUTH_NONE
        self._info = replace(
            self._info, auth_mode=AUTH_NONE, auth_required=False, cost="free"
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.modality() != "text":
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                source=self.source,
                error=(
                    "Бесплатный шлюз здесь работает только с текстом. Изображения "
                    "и файлы обработает другой провайдер."
                ),
                error_category=CALL_BAD_REQUEST,
                request_id=request.correlation_id,
                status=STATUS_UNAVAILABLE,
            )
        return await super().chat(request)


class PollinationsImageProvider(_BaseApiProvider):
    """Keyless Pollinations image generation (v2.0, ``image_generation``).

    It is **not** a chat model: it answers an image-generation prompt with an
    image and never parses chat text. A caller passes the prompt as the request's
    text; the response is an honest ``image_url`` (the deterministic public URL
    for the prompt + seed). No key, no account. It never claims image
    *understanding* (vision) — only generation.
    """

    def __init__(
        self,
        *,
        model: str = "flux",
        transport: HttpTransport,
        base_url: str = "https://image.pollinations.ai",
        cost: str = "free",
        priority: int = 70,
    ) -> None:
        super().__init__(
            provider="pollinations_image",
            model=model,
            base_url=base_url,
            api_key="",
            transport=transport,
            capabilities=Capability(text=False, image=False),
            cost=cost,
            priority=priority,
            note=(
                "Бесплатная генерация изображений без ключа (Pollinations, Flux). "
                "Генерирует картинку из текста; изображения НЕ распознаёт."
            ),
        )
        self.auth_mode = AUTH_NONE
        self._info = replace(
            self._info, auth_mode=AUTH_NONE, auth_required=False, cost="free"
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        prompt = request.text()
        if not prompt:
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                source=self.source,
                error="Пустой запрос на генерацию изображения.",
                error_category=CALL_BAD_REQUEST,
                request_id=request.correlation_id,
                status=STATUS_UNAVAILABLE,
            )
        if request.modality() != "text":
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                source=self.source,
                error=(
                    "Генератор изображений принимает только текстовый запрос "
                    "(что нарисовать), без вложений."
                ),
                error_category=CALL_BAD_REQUEST,
                request_id=request.correlation_id,
                status=STATUS_UNAVAILABLE,
            )
        seed = int.from_bytes(
            hashlib.sha256(prompt.encode("utf-8")).digest()[:4], "big"
        )
        url = (
            f"{self._base_url}/prompt/{quote(prompt, safe='')}"
            f"?width=1024&height=1024&nologo=true&seed={seed}"
        )
        resp = await self._transport.get_json(url, timeout=request.timeout_seconds)
        if resp.error or resp.status >= 400:
            return self._error_response(
                ProviderUnavailableError(
                    "Не удалось получить изображение.", provider=self._name
                ),
                request,
            )
        return ChatResponse(
            ok=True,
            text=url,
            structured={"image_url": url},
            provider_used=self._name,
            model_used=self._model,
            source=self.source,
            request_id=request.correlation_id,
            status=STATUS_AVAILABLE,
        )


class AnthropicProvider(_BaseApiProvider):
    """Anthropic Messages API."""

    def __init__(
        self,
        *,
        model: str = "claude-3-5-haiku-latest",
        api_key: str = "",
        transport: HttpTransport,
        base_url: str = "https://api.anthropic.com/v1",
        cost: str = "premium",
        priority: int = 0,
    ) -> None:
        super().__init__(
            provider="anthropic",
            model=model,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            capabilities=Capability(
                text=True, image=True, streaming=True, structured=True
            ),
            cost=cost,
            priority=priority,
        )
        self._extra_headers = {"anthropic-version": "2023-06-01"}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    async def chat(self, request: ChatRequest) -> ChatResponse:
        system = "\n".join(m.content for m in request.messages if m.role == "system")
        msgs = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role != "system"
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system:
            payload["system"] = system
        try:
            resp = await self._transport.post_json(
                f"{self._base_url}/messages",
                payload,
                headers=self._headers(),
                timeout=request.timeout_seconds,
            )
            _raise_for_response(resp, self._name)
        except GatewayError as exc:
            return self._error_response(exc, request)
        data = resp.json() or {}
        text = ""
        try:
            parts = data.get("content") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        except (AttributeError, TypeError):
            text = ""
        if not text:
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                error="Пустой ответ провайдера.",
                error_category=CALL_ERROR,
                request_id=request.correlation_id,
                status=STATUS_NETWORK_ERROR,
            )
        return ChatResponse(
            ok=True,
            text=text,
            provider_used=self._name,
            model_used=self._model,
            source=self.source,
            request_id=request.correlation_id,
            status=STATUS_AVAILABLE,
        )


class GoogleProvider(_BaseApiProvider):
    """Google Gemini ``generateContent``."""

    def __init__(
        self,
        *,
        model: str = "gemini-2.0-flash",
        api_key: str = "",
        transport: HttpTransport,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        cost: str = "cheap",
        priority: int = 0,
    ) -> None:
        super().__init__(
            provider="google",
            model=model,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            capabilities=Capability(
                text=True, image=True, streaming=True, structured=True
            ),
            cost=cost,
            priority=priority,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self._extra_headers}
        if self._api_key:
            headers["x-goog-api-key"] = self._api_key
        return headers

    async def chat(self, request: ChatRequest) -> ChatResponse:
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, Any]] = []
        for msg in request.messages:
            parts: list[dict[str, Any]] = []
            if msg.content:
                parts.append({"text": msg.content})
            for att in msg.attachments:
                if att.kind == MODALITY_IMAGE and att.data_b64:
                    b64 = att.data_b64.split(",", 1)[-1]
                    parts.append(
                        {"inline_data": {"mime_type": att.mime or "image/png", "data": b64}}
                    )
            if msg.role == "system":
                system_parts.extend(parts)
            else:
                role = "user" if msg.role != "assistant" else "model"
                contents.append({"role": role, "parts": parts})
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        try:
            resp = await self._transport.post_json(
                f"{self._base_url}/models/{self._model}:generateContent",
                payload,
                headers=self._headers(),
                timeout=request.timeout_seconds,
            )
            _raise_for_response(resp, self._name)
        except GatewayError as exc:
            return self._error_response(exc, request)
        data = resp.json() or {}
        text = ""
        try:
            cands = data.get("candidates") or []
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._model,
                error="Пустой ответ провайдера.",
                error_category=CALL_ERROR,
                request_id=request.correlation_id,
                status=STATUS_NETWORK_ERROR,
            )
        return ChatResponse(
            ok=True,
            text=text,
            provider_used=self._name,
            model_used=self._model,
            source=self.source,
            request_id=request.correlation_id,
            status=STATUS_AVAILABLE,
        )


class OllamaProvider(_BaseApiProvider):
    """A local Ollama server (OpenAI-compatible mode, no auth by default)."""

    def __init__(
        self,
        *,
        model: str = "llama3.2",
        base_url: str = "http://127.0.0.1:11434/v1",
        transport: HttpTransport,
        api_key: str = "",
        priority: int = 100,
    ) -> None:
        super().__init__(
            provider="ollama",
            model=model,
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            capabilities=Capability(text=True, streaming=True, structured=True),
            cost="free",
            priority=priority,
            note="Локальный сервер на этом компьютере — данные не покидают его.",
        )
        self.auth_mode = AUTH_NONE
        self._info = replace(self._info, auth_mode=AUTH_NONE, cost="free")


class FakeProvider:
    """Deterministic in-process provider (tests, offline demo)."""

    def __init__(
        self,
        *,
        provider: str = "fake",
        model: str = "fake-model",
        reply: str = "готово",
        capabilities: Capability | None = None,
        available: bool = True,
        fail_with: str = "",
        cost: str = "free",
        priority: int = 0,
        source: str = SourceKind.API,
    ) -> None:
        self._name = provider
        self._reply = reply
        self._available = available
        self._fail_with = fail_with
        self._info = ProviderInfo(
            provider=provider,
            model=model,
            source=source,
            capabilities=capabilities or Capability(text=True),
            auth_mode=AUTH_NONE,
            cost=cost,
            priority=priority,
        )
        self.calls: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def info(self) -> ProviderInfo:
        return self._info

    def availability(self) -> Availability:
        if not self._available:
            return Availability(status=STATUS_UNAVAILABLE, detail="Отключён.")
        return Availability(status=STATUS_AVAILABLE)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        if self._fail_with:
            status = self._fail_with
            return ChatResponse(
                ok=False,
                provider_used=self._name,
                model_used=self._info.model,
                source=self._info.source,
                error=f"fake failure: {status}",
                error_category=CALL_ERROR,
                request_id=request.correlation_id,
                status=status,
            )
        return ChatResponse(
            ok=True,
            text=self._reply,
            provider_used=self._name,
            model_used=self._info.model,
            source=self._info.source,
            request_id=request.correlation_id,
            status=STATUS_AVAILABLE,
        )

    async def close(self) -> None:
        return None


__all__ = [
    "AnthropicProvider",
    "DeepSeekProvider",
    "FakeProvider",
    "GoogleProvider",
    "Llm7Provider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "PollinationsImageProvider",
    "PollinationsProvider",
]
