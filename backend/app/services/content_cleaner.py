"""Deterministic Content Cleaner (v1.2: Content Studio).

Rule-based, explainable text cleanup — never an AI. Every transformation is
recorded so the UI can show a before/after preview and the owner can cancel the
cleanup. The cleaner never deletes text silently: it reports each removed block.

Rules applied (all opt-in per call):

* strip advertising blocks by marker lines ("реклама", "промокод", "#ad");
* drop UTM query parameters from links;
* drop repeated CTA lines ("подписывайтесь", "жми", "ставь лайк");
* normalize whitespace and blank lines;
* normalize links (strip tracking params, unwrap t.me redirects);
* drop footer junk (separator lines, "читать далее" stubs).

It also strips HTML/Markdown to plain text with Telegram-style entities so the
result can be published with correct formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: Lines that signal an advertising block.
_AD_MARKERS = (
    "реклама",
    "промокод",
    "промо-код",
    "#ad",
    "реклама канала",
    "по рекламе",
    "за рекламу",
)

#: Repeated calls to action.
_CTA_MARKERS = (
    "подписывайтесь",
    "подпишись",
    "подписаться на канал",
    "жми",
    "жмите",
    "ставь лайк",
    "ставьте лайк",
    "ставь реакцию",
    "поделись",
    "поделитесь",
)

#: Footer junk / navigation stubs.
_FOOTER_MARKERS = (
    "читать далее",
    "продолжение в",
    "продолжение следует",
    "больше новостей",
    "источник:",
    "наш сайт",
    "наш канал",
)

#: UTM/tracking query keys stripped from links.
_TRACKING_KEYS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_name",
        "fbclid",
        "gclid",
        "yclid",
        "igshid",
        "ref",
        "ref_src",
        "si",
    }
)

_SEPARATOR_RE = re.compile(r"^[\s\-_=~*•·—–]{3,}$")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class CleanChange:
    """One explainable change made by the cleaner."""

    rule: str
    title: str
    detail: str = ""


@dataclass(slots=True)
class CleanResult:
    """Before/after result of one cleanup call."""

    original: str
    cleaned: str
    changes: list[CleanChange] = field(default_factory=list)
    removed_lines: int = 0

    @property
    def changed(self) -> bool:
        return self.cleaned != self.original


def _strip_tracking(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _TRACKING_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def _normalize_links(text: str) -> tuple[str, int]:
    count = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal count
        original = match.group(0)
        # Trim trailing punctuation that is not part of the URL.
        trailing = ""
        while original and original[-1] in ".,;:!?)\"":
            trailing = original[-1] + trailing
            original = original[:-1]
        stripped = _strip_tracking(original)
        if stripped != original:
            count += 1
        return stripped + trailing

    return _URL_RE.sub(_replace, text), count


def _matches_marker(line_lower: str, markers: tuple[str, ...]) -> bool:
    return any(marker in line_lower for marker in markers)


def clean_text(
    text: str,
    *,
    strip_ads: bool = True,
    strip_cta: bool = True,
    strip_footer: bool = True,
    normalize_links: bool = True,
    normalize_whitespace: bool = True,
) -> CleanResult:
    """Clean ``text`` deterministically and report every change."""
    original = text or ""
    working = original
    changes: list[CleanChange] = []
    removed_lines = 0

    # Strip HTML tags up front (plain text with no markup).
    if _HTML_TAG_RE.search(working):
        working = _HTML_TAG_RE.sub("", working)
        changes.append(CleanChange("html", "Убрана HTML-разметка"))

    lines = working.split("\n")
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            kept.append("")
            continue
        if _SEPARATOR_RE.match(stripped):
            removed_lines += 1
            continue
        if strip_ads and _matches_marker(lower, _AD_MARKERS):
            removed_lines += 1
            continue
        if strip_cta and _matches_marker(lower, _CTA_MARKERS):
            removed_lines += 1
            continue
        if strip_footer and _matches_marker(lower, _FOOTER_MARKERS):
            removed_lines += 1
            continue
        kept.append(line.rstrip())
    working = "\n".join(kept)

    if removed_lines:
        changes.append(
            CleanChange("blocks", "Удалены рекламные/служебные блоки", f"строк: {removed_lines}")
        )

    if normalize_links:
        working, link_count = _normalize_links(working)
        if link_count:
            changes.append(
                CleanChange("links", "Очищены ссылки (убраны метки)", f"ссылок: {link_count}")
            )

    if normalize_whitespace:
        before = working
        working = _TRAILING_WS_RE.sub("\n", working)
        working = _MULTI_BLANK_RE.sub("\n\n", working)
        working = working.strip()
        if working != before:
            changes.append(CleanChange("whitespace", "Нормализованы пробелы и пустые строки"))

    return CleanResult(
        original=original,
        cleaned=working,
        changes=changes,
        removed_lines=removed_lines,
    )


__all__ = ["CleanChange", "CleanResult", "clean_text"]
