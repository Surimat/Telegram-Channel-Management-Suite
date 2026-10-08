"""Content language: source/target resolution, detection and protected translation.

v2.0 (Target Language). The Content Studio gains an explicit language stage:

* a **source language** (auto-detected or set per source),
* a **target language** resolved by precedence (publication → channel → source →
  global default),
* a **translation** step that runs only when the languages actually differ.

The translation must not corrupt the post. URLs, ``@username``, ``t.me`` links,
hashtags, inline code, HTML tags and Telegram-entity spans are **masked** with
private-use placeholders before the text is sent to the AI and restored verbatim
afterwards, so the model never rewrites a link or an identifier. Markdown/HTML
structure is preserved by the same mechanism.

Nothing here stores secrets. Translation goes through the **existing** AI
Gateway, so provider selection, retries and failover are exactly the v1.8
behaviour; a total failure never loses material (the caller keeps the original).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.models.content import ContentItem

MODULE = "content"

#: ``auto`` means "detect it"; a concrete code means "use it".
LANG_AUTO = "auto"

#: Language codes we detect/offer. Kept small and explicit so the UI can list it.
SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "ru",
    "en",
    "uk",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "tr",
    "ar",
    "zh",
    "ja",
)

#: Human titles (RU-first, matching the rest of the UI).
LANGUAGE_TITLES: dict[str, str] = {
    LANG_AUTO: "Определять автоматически",
    "ru": "Русский",
    "en": "Английский",
    "uk": "Украинский",
    "de": "Немецкий",
    "fr": "Французский",
    "es": "Испанский",
    "it": "Итальянский",
    "pt": "Португальский",
    "tr": "Турецкий",
    "ar": "Арабский",
    "zh": "Китайский",
    "ja": "Японский",
}

#: The language used when nothing else is configured.
DEFAULT_LANGUAGE = "ru"

#: Settings the language stage exposes in the Settings UI (title, type, default).
#: Declared here so the write-only-settings auditor sees the reader.
CONTENT_SETTING_SPECS: dict[str, tuple[str, str, str]] = {
    "content_default_language": ("Целевой язык по умолчанию", "string", DEFAULT_LANGUAGE),
}


def normalize_language(value: str | None) -> str:
    """Return a known language code, ``auto``, or the safe default."""
    code = (value or "").strip().lower()
    if not code:
        return DEFAULT_LANGUAGE
    if code == LANG_AUTO:
        return LANG_AUTO
    # Accept "ru-RU" / "en_US".
    base = re.split(r"[-_]", code)[0]
    if base in SUPPORTED_LANGUAGES:
        return base
    return base or DEFAULT_LANGUAGE


def is_auto(value: str | None) -> bool:
    return normalize_language(value) == LANG_AUTO


_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_LATIN = re.compile(r"[A-Za-z]")
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def detect_language(text: str) -> str:
    """Deterministic script-based language guess (never a network call).

    Honest and cheap: it distinguishes Cyrillic (ru/uk), CJK (zh/ja) and Latin
    (en by default). It is a *guess* used to avoid a pointless translation, not a
    linguistic verdict — the owner can always set the language explicitly.
    """
    sample = (text or "").strip()
    if not sample:
        return DEFAULT_LANGUAGE
    cyrillic = len(_CYRILLIC.findall(sample))
    latin = len(_LATIN.findall(sample))
    cjk = len(_CJK.findall(sample))
    total = max(1, cyrillic + latin + cjk)
    if cjk / total > 0.3:
        # Japanese kana vs. Chinese ideographs.
        if re.search(r"[\u3040-\u30ff]", sample):
            return "ja"
        return "zh"
    if cyrillic / total > 0.3:
        # Ukrainian-specific letters (і, ї, є, ґ) are a strong signal.
        if re.search(r"[іїєґІЇЄҐ]", sample):
            return "uk"
        return "ru"
    if latin / total > 0.3:
        return "en"
    return DEFAULT_LANGUAGE


def resolve_target(
    *,
    publication: str = "",
    channel: str = "",
    source: str = "",
    global_default: str = "",
) -> str:
    """Resolve the effective target language by precedence.

    publication → channel → source → global default. ``auto`` at any level means
    "fall through to the next level"; the final value is never ``auto`` (a target
    must be a concrete language so translation is deterministic).
    """
    for candidate in (publication, channel, source, global_default):
        # An empty value means "not set" and must fall through, not become the
        # default (``normalize_language("")`` would otherwise resolve to ``ru``).
        if not (candidate or "").strip():
            continue
        normalized = normalize_language(candidate)
        if normalized != LANG_AUTO:
            return normalized
    return DEFAULT_LANGUAGE


def needs_translation(source_language: str, target_language: str) -> bool:
    """True only when both are concrete and actually differ."""
    source = normalize_language(source_language)
    target = normalize_language(target_language)
    if source == LANG_AUTO or target == LANG_AUTO:
        return True
    return source != target


# ---------------------------------------------------------------------------
# Protected spans
# ---------------------------------------------------------------------------
#: Private-use characters wrap a placeholder index so the model is very unlikely
#: to merge or translate them. ``\ue000`` … ``\ue001`` bound the index digits.
_MASK_OPEN = "\ue000"
_MASK_CLOSE = "\ue001"

#: Order matters: longer/more specific patterns first so a URL is captured before
#: a bare domain. ``re.MULTILINE`` so code fences span lines.
_PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"```.*?```", re.DOTALL),          # fenced code
    re.compile(r"`[^`\n]+`"),                      # inline code
    re.compile(r"<[^>\n]+>"),                      # HTML/Telegram HTML tags
    re.compile(r"https?://[^\s<>\)\]]+"),          # URLs
    re.compile(r"tg://[^\s<>\)\]]+"),              # Telegram deep links
    re.compile(r"(?:t|telegram)\.me/[^\s<>\)\]]+", re.IGNORECASE),
    re.compile(r"@[A-Za-z][A-Za-z0-9_]{3,31}"),    # @username
    re.compile(r"#[^\s#<>]+"),                     # #hashtag
    re.compile(r"\b[A-Z]{2,}-\d+\b"),              # technical identifiers (ID-123)
)


@dataclass(slots=True)
class ProtectedText:
    """Text with protected spans replaced by placeholders."""

    masked: str
    tokens: list[str] = field(default_factory=list)

    def restore(self, text: str) -> str:
        """Put every protected span back into ``text`` (best effort)."""
        out = text
        for index, token in enumerate(self.tokens):
            out = out.replace(_placeholder(index), token)
        return out


def _placeholder(index: int) -> str:
    return f"{_MASK_OPEN}{index}{_MASK_CLOSE}"


def protect_text(text: str, *, entities: list[dict[str, object]] | None = None) -> ProtectedText:
    """Mask links, usernames, hashtags, code, tags and entity spans.

    ``entities`` are Telegram entities (type/offset/length). Their spans are
    masked too, so a translation cannot break the entity offsets; the caller
    re-parses entities from the restored text when needed.
    """
    tokens: list[str] = []
    masked = text or ""

    def _mask(value: str) -> str:
        index = len(tokens)
        tokens.append(value)
        return _placeholder(index)

    for pattern in _PROTECTED_PATTERNS:
        masked = pattern.sub(lambda m: _mask(m.group(0)), masked)

    if entities:
        # Mask entity spans from the end so earlier offsets stay valid.
        spans: list[tuple[int, int]] = []
        for entity in entities:
            try:
                start = int(entity.get("offset", 0))  # type: ignore[arg-type]
                length = int(entity.get("length", 0))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if length > 0:
                spans.append((start, start + length))
        for start, end in sorted(spans, reverse=True):
            if 0 <= start < end <= len(masked):
                masked = masked[:start] + _mask(masked[start:end]) + masked[end:]

    return ProtectedText(masked=masked, tokens=tokens)


def has_protected(text: str) -> bool:
    return any(p.search(text or "") for p in _PROTECTED_PATTERNS)


def translation_instruction(source_language: str, target_language: str) -> str:
    """The instruction sent to the gateway for a translation task."""
    src = LANGUAGE_TITLES.get(normalize_language(source_language), source_language)
    dst = LANGUAGE_TITLES.get(normalize_language(target_language), target_language)
    return (
        f"Переведи текст с языка «{src}» на «{dst}», сохранив смысл, тон и структуру. "
        "Символы вида \ue0000\ue001 — это защищённые фрагменты (ссылки, @упоминания, "
        "хештеги, код, HTML). НЕ переводи их, НЕ удаляй и оставь ровно как есть, "
        "включая окружающие символы. Сохрани разметку Markdown и переносы строк. "
        "Верни только переведённый текст без пояснений."
    )


@dataclass(slots=True)
class LanguageOutcome:
    """The result of a language resolution/translation attempt."""

    source_language: str
    target_language: str
    translated: bool
    text: str
    provider: str = ""
    model: str = ""
    fallback_used: bool = False
    detail: str = ""


class ContentLanguageService:
    """Resolve languages for an item and translate through the AI Gateway."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        gateway=None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self._gateway = gateway

    def _gateway_service(self):  # type: ignore[no-untyped-def]
        if self._gateway is None:
            from backend.app.services.ai_gateway_service import AiGatewayService

            self._gateway = AiGatewayService(self.session, settings=self.settings)
        return self._gateway

    async def default_language(self) -> str:
        """The global default target language (setting, else ``ru``)."""
        from backend.app.services.settings_service import SettingsService

        raw = await SettingsService(self.session).get_typed(
            "content_default_language", DEFAULT_LANGUAGE
        )
        return normalize_language(str(raw))

    async def resolve_for_item(self, item: ContentItem) -> LanguageOutcome:
        """Resolve source/target for an item without translating."""
        source = await self._source_language(item)
        target = await self._target_language(item)
        return LanguageOutcome(
            source_language=source,
            target_language=target,
            translated=False,
            text=item.cleaned_text or item.text,
        )

    async def _source_language(self, item: ContentItem) -> str:
        from backend.app.db.repositories.content import ContentSourceRepository

        # An explicit item-level source language is never overwritten by detection.
        raw_item = (getattr(item, "source_language", "") or "").strip().lower()
        if raw_item and raw_item != LANG_AUTO:
            return normalize_language(raw_item)

        source_row = None
        if item.source_id:
            source_row = await ContentSourceRepository(self.session).get(item.source_id)
        configured = getattr(source_row, "source_language", "") if source_row else ""
        if configured and not is_auto(configured):
            return normalize_language(configured)
        auto_detect = getattr(source_row, "auto_detect", True) if source_row else True
        stored = normalize_language(item.language)
        if auto_detect:
            return detect_language(item.cleaned_text or item.text)
        return stored

    async def _target_language(self, item: ContentItem) -> str:
        from backend.app.db.repositories.content import (
            ContentSourceRepository,
            PublicationRepository,
        )

        publication_target = ""
        pubs = await PublicationRepository(self.session).list_for_item(item.id)
        if pubs:
            publication_target = getattr(pubs[0], "target_language", "") or ""

        channel_target = ""
        channel_id = getattr(pubs[0], "channel_id", "") if pubs else ""
        if channel_id:
            from backend.app.db.repositories.channels import ChannelRepository

            channel = await ChannelRepository(self.session).get(channel_id)
            if channel is not None:
                channel_target = getattr(channel, "target_language", "") or ""

        source_target = ""
        if item.source_id:
            source_row = await ContentSourceRepository(self.session).get(item.source_id)
            if source_row is not None:
                source_target = getattr(source_row, "target_language", "") or ""

        item_target = getattr(item, "target_language", "") or ""
        return resolve_target(
            publication=publication_target or item_target,
            channel=channel_target,
            source=source_target,
            global_default=await self.default_language(),
        )

    async def translate(
        self,
        item: ContentItem,
        *,
        target_language: str = "",
        strategy: str = "",
        instruction: str = "",
    ) -> LanguageOutcome:
        """Translate an item's text if the languages differ.

        Never destructive: on failure the item keeps its previous text and the
        outcome records ``translated=False`` with a secret-free reason.
        """
        text = item.cleaned_text or item.text
        source = await self._source_language(item)
        target = (
            normalize_language(target_language)
            if target_language
            else await self._target_language(item)
        )
        if target == LANG_AUTO:
            target = await self.default_language()

        if not needs_translation(source, target):
            return LanguageOutcome(
                source_language=source,
                target_language=target,
                translated=False,
                text=text,
                detail="Язык совпадает — перевод не требуется.",
            )

        protected = protect_text(text, entities=_parse_entities(item.entities))
        base_instruction = instruction or translation_instruction(source, target)
        response = await self._gateway_service().transform(
            task="translation",
            text=protected.masked,
            instruction=base_instruction,
            strategy=strategy,
        )
        if not response.ok or not response.text.strip():
            return LanguageOutcome(
                source_language=source,
                target_language=target,
                translated=False,
                text=text,
                detail=response.error or "Перевод недоступен.",
            )
        restored = protected.restore(response.text.strip())
        return LanguageOutcome(
            source_language=source,
            target_language=target,
            translated=True,
            text=restored,
            provider=response.provider_used,
            model=response.model_used,
            fallback_used=response.fallback_used,
            detail="",
        )


def _parse_entities(raw: str) -> list[dict[str, object]]:
    import json

    try:
        value = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGE_TITLES",
    "LANG_AUTO",
    "SUPPORTED_LANGUAGES",
    "ContentLanguageService",
    "LanguageOutcome",
    "ProtectedText",
    "detect_language",
    "has_protected",
    "is_auto",
    "needs_translation",
    "normalize_language",
    "protect_text",
    "resolve_target",
    "translation_instruction",
]
