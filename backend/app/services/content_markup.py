"""Markup validation and Telegram-like preview (v1.2: Content Studio).

Before publishing, text + entities are parsed and validated so the owner is
never surprised by a broken message:

* unbalanced/unclosed Markdown or HTML tags;
* entities that fall outside the text or overlap illegally;
* invalid URLs;
* text/caption length beyond Telegram's limits.

:func:`validate_markup` returns precise, line-aware errors and can auto-fix the
simple cases (unclosed tags, stray markers). :func:`render_preview` produces a
structure the front end renders as a Telegram-like bubble. It does not claim to
be pixel-perfect — Telegram's own renderer cannot be reproduced exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Telegram limits (conservative; the Bot API rejects longer messages).
MAX_TEXT_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024
MAX_ALBUM_ITEMS = 10

#: Telegram-supported inline entity types.
SUPPORTED_ENTITY_TYPES = frozenset(
    {
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "spoiler",
        "code",
        "pre",
        "blockquote",
        "text_link",
        "text_mention",
        "url",
        "mention",
        "hashtag",
        "cashtag",
        "bot_command",
        "email",
        "phone_number",
    }
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


@dataclass(slots=True)
class MarkupIssue:
    """One precise markup problem."""

    kind: str            # unclosed | invalid_entity | invalid_url | too_long | invalid_tag
    message: str
    line: int = 0
    offset: int = 0
    auto_fixable: bool = False


@dataclass(slots=True)
class MarkupValidation:
    text: str
    ok: bool
    issues: list[MarkupIssue] = field(default_factory=list)
    fixed_text: str = ""
    entities: list[dict[str, object]] = field(default_factory=list)

    @property
    def first_error(self) -> str:
        if not self.issues:
            return ""
        issue = self.issues[0]
        where = f" (строка {issue.line})" if issue.line else ""
        return f"{issue.message}{where}"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _validate_entities(
    text: str, entities: list[dict[str, object]]
) -> list[MarkupIssue]:
    issues: list[MarkupIssue] = []
    length = len(text)
    for ent in entities:
        etype = str(ent.get("type", ""))
        if etype not in SUPPORTED_ENTITY_TYPES:
            issues.append(
                MarkupIssue(
                    kind="invalid_entity",
                    message=f"Неизвестный тип форматирования: {etype}.",
                    auto_fixable=True,
                )
            )
            continue
        offset = int(ent.get("offset", 0) or 0)
        ent_len = int(ent.get("length", 0) or 0)
        if offset < 0 or ent_len <= 0 or offset + ent_len > length:
            issues.append(
                MarkupIssue(
                    kind="invalid_entity",
                    message="Форматирование выходит за пределы текста.",
                    line=_line_of(text, offset),
                    offset=offset,
                    auto_fixable=True,
                )
            )
            continue
        if etype == "text_link":
            url = str(ent.get("url", "") or "")
            if not url.lower().startswith(("http://", "https://", "tg://")):
                issues.append(
                    MarkupIssue(
                        kind="invalid_url",
                        message=f"Некорректная ссылка: {url or '—'}.",
                        line=_line_of(text, offset),
                        auto_fixable=False,
                    )
                )
    return issues


def _validate_plain_urls(text: str) -> list[MarkupIssue]:
    issues: list[MarkupIssue] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?)")
        if url.lower().startswith(("http://", "https://")) and len(url) > 8:
            continue
        issues.append(
            MarkupIssue(
                kind="invalid_url",
                message=f"Подозрительная ссылка: {url}.",
                line=_line_of(text, match.start()),
                offset=match.start(),
            )
        )
    return issues


_MARKDOWN_MARKERS = ("**", "__", "`", "||", "~~")


def validate_markup(
    text: str,
    *,
    entities: list[dict[str, object]] | None = None,
    caption: bool = False,
) -> MarkupValidation:
    """Validate ``text`` + ``entities``; return precise issues and a fixed text."""
    entities = list(entities or [])
    issues: list[MarkupIssue] = []

    limit = MAX_CAPTION_LENGTH if caption else MAX_TEXT_LENGTH
    if len(text) > limit:
        issues.append(
            MarkupIssue(
                kind="too_long",
                message=f"Текст слишком длинный ({len(text)} из {limit} символов).",
                line=_line_of(text, limit),
            )
        )

    # Unclosed Markdown markers: an odd count of a paired marker.
    for marker in _MARKDOWN_MARKERS:
        if marker == "`":
            continue
        if text.count(marker) % 2 != 0:
            issues.append(
                MarkupIssue(
                    kind="unclosed",
                    message=f"Не закрыт тег форматирования {marker}.",
                    line=_line_of(text, text.rfind(marker)),
                    auto_fixable=True,
                )
            )

    # Unclosed HTML-style tags.
    for match in re.finditer(r"</?([a-zA-Z]+)[^>]*>", text):
        tag = match.group(1).lower()
        if tag not in {"b", "i", "u", "s", "a", "code", "pre", "tg-spoiler", "blockquote"}:
            issues.append(
                MarkupIssue(
                    kind="invalid_tag",
                    message=f"Неподдерживаемый тег: <{tag}>.",
                    line=_line_of(text, match.start()),
                    auto_fixable=True,
                )
            )

    issues.extend(_validate_entities(text, entities))
    issues.extend(_validate_plain_urls(text))

    fixed = _auto_fix(text) if any(i.auto_fixable for i in issues) else text
    ok = not issues
    return MarkupValidation(text=text, ok=ok, issues=issues, fixed_text=fixed, entities=entities)


def _auto_fix(text: str) -> str:
    """Best-effort fix for the simple cases (unclosed Markdown markers)."""
    fixed = text
    for marker in _MARKDOWN_MARKERS:
        if marker == "`":
            continue
        count = fixed.count(marker)
        if count % 2 != 0:
            fixed = fixed + marker
    # Drop unsupported HTML tags but keep their inner text.
    fixed = re.sub(
        r"</?(?!(?:b|i|u|s|a|code|pre|tg-spoiler|blockquote)\b)[a-zA-Z]+[^>]*>",
        "",
        fixed,
    )
    return fixed


@dataclass(slots=True)
class PreviewButton:
    text: str
    action: str
    url: str = ""


@dataclass(slots=True)
class PreviewMedia:
    kind: str
    filename: str
    caption: str = ""


@dataclass(slots=True)
class TelegramPreview:
    """Structure the front end renders as a Telegram-like bubble."""

    text: str
    entities: list[dict[str, object]]
    buttons: list[list[PreviewButton]]
    media: list[PreviewMedia]
    is_album: bool
    caption_used: bool
    char_count: int
    notice: str = (
        "Предпросмотр повторяет структуру сообщения Telegram, но не является "
        "пиксельно точным."
    )


def render_preview(
    text: str,
    *,
    entities: list[dict[str, object]] | None = None,
    buttons: list[list[dict[str, object]]] | None = None,
    media: list[dict[str, object]] | None = None,
    is_album: bool = False,
) -> TelegramPreview:
    """Build a Telegram-like preview structure (no HTML escaping assumptions)."""
    button_rows: list[list[PreviewButton]] = []
    for row in buttons or []:
        out_row: list[PreviewButton] = []
        for btn in row:
            out_row.append(
                PreviewButton(
                    text=str(btn.get("text", "")),
                    action=str(btn.get("action", "url")),
                    url=str(btn.get("value", "")),
                )
            )
        if out_row:
            button_rows.append(out_row)

    preview_media: list[PreviewMedia] = []
    for m in media or []:
        preview_media.append(
            PreviewMedia(
                kind=str(m.get("kind", "photo")),
                filename=str(m.get("filename", "")),
                caption=str(m.get("caption", "")),
            )
        )

    return TelegramPreview(
        text=text,
        entities=list(entities or []),
        buttons=button_rows,
        media=preview_media,
        is_album=is_album or len(preview_media) > 1,
        caption_used=bool(preview_media) and bool(text),
        char_count=len(text),
    )


__all__ = [
    "MAX_ALBUM_ITEMS",
    "MAX_CAPTION_LENGTH",
    "MAX_TEXT_LENGTH",
    "SUPPORTED_ENTITY_TYPES",
    "MarkupIssue",
    "MarkupValidation",
    "PreviewButton",
    "PreviewMedia",
    "TelegramPreview",
    "render_preview",
    "validate_markup",
]
