"""Content source providers (v1.2: Content Studio grabber).

Four providers behind one :class:`ContentSourceProvider` protocol:

* :class:`TelegramContentProvider` — reads a Telegram channel through the
  existing :class:`SessionProvider` (never imports Telethon here, D-001). It
  respects content protection: a source that forbids forwarding/downloading is
  reported as ``protected`` and only its link is offered.
* :class:`RssContentProvider` / :class:`AtomContentProvider` — parse feeds with
  the standard library only, honouring ``ETag``/``Last-Modified`` and a
  ``last_seen_item`` marker so a feed is never fully re-downloaded.
* :class:`ManualContentProvider` — a public URL the owner pastes in, or the
  material itself.

A registry maps a source kind to its provider so new sources are additive.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from backend.app.core.logging import get_logger
from backend.app.providers.content_base import (
    ContentQuery,
    ContentSourceProvider,
    FetchedItem,
    FetchResult,
)

logger = get_logger(__name__)

KIND_TELEGRAM = "telegram"
KIND_RSS = "rss"
KIND_ATOM = "atom"
KIND_MANUAL = "manual"

PROTECTED_MESSAGE = "Контент нельзя автоматически получить из этого источника."
PROTECTED_FIX = (
    "Источник запрещает копирование. Сохраните только ссылку на источник "
    "и опубликуйте материал вручную."
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&nbsp;": " ",
}


def strip_html(value: str) -> str:
    """Very small HTML→text helper (no external dependency)."""
    text = _TAG_RE.sub("", value or "")
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    return _WS_RE.sub(" ", text).strip()


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(node: ET.Element, name: str) -> str:
    for child in node:
        if _localname(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _link(node: ET.Element) -> str:
    """Return the best link from an RSS ``<link>`` or Atom ``<link href>``."""
    for child in node:
        if _localname(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            rel = child.attrib.get("rel", "alternate")
            if rel == "alternate":
                return href
        elif child.text:
            return child.text.strip()
    return ""


@dataclass
class _FeedParse:
    title: str
    items: list[FetchedItem]


def parse_feed(xml_text: str, *, kind: str, reference: str, limit: int) -> _FeedParse:
    """Parse an RSS or Atom document into :class:`FetchedItem` objects."""
    root = ET.fromstring(xml_text)
    root_name = _localname(root.tag)
    is_atom = root_name == "feed" or kind == KIND_ATOM

    feed_title = _text(root, "title")
    items: list[FetchedItem] = []

    if is_atom:
        entries = [c for c in root if _localname(c.tag) == "entry"]
    else:
        channel = next((c for c in root if _localname(c.tag) == "channel"), root)
        feed_title = _text(channel, "title") or feed_title
        entries = [c for c in channel if _localname(c.tag) == "item"]

    for entry in entries[: max(1, limit)]:
        title = _text(entry, "title")
        link = _link(entry)
        summary = _text(entry, "summary") or _text(entry, "description")
        content = _text(entry, "encoded") or _text(entry, "content")
        body = strip_html(content or summary)
        published = (
            _text(entry, "pubDate")
            or _text(entry, "published")
            or _text(entry, "updated")
        )
        author = _text(entry, "author") or _text(entry, "creator")
        guid = _text(entry, "guid") or _text(entry, "id") or link
        items.append(
            FetchedItem(
                title=title,
                text=body,
                source_url=link,
                source_channel=feed_title or reference,
                source_author=author,
                published_at=published,
                extra={"guid": guid},
            )
        )
    return _FeedParse(title=feed_title or reference, items=items)


class _HttpFeedProvider:
    """Shared incremental HTTP fetch for RSS/Atom."""

    kind = KIND_RSS
    title = "RSS"

    def available(self) -> tuple[bool, str]:
        return True, ""

    async def fetch(self, query: ContentQuery, *, state: dict[str, str]) -> FetchResult:
        reference = (query.reference or "").strip()
        if not reference:
            return FetchResult(ok=False, message="Укажите адрес канала (feed).")
        xml_text, etag, last_modified, status, error = await self._download(
            reference, state
        )
        if status == 304:
            return FetchResult(
                ok=True,
                message="Новых материалов нет.",
                etag=state.get("etag", ""),
                last_modified=state.get("last_modified", ""),
                last_seen_item=state.get("last_seen_item", ""),
            )
        if error:
            return FetchResult(ok=False, message=error, how_to_fix="Проверьте адрес канала.")
        try:
            parsed = parse_feed(xml_text, kind=self.kind, reference=reference, limit=query.limit)
        except ET.ParseError as exc:
            logger.info("Feed parse error for %s: %s", reference, exc)
            return FetchResult(
                ok=False,
                message="Не удалось разобрать файл канала (RSS/Atom).",
                how_to_fix="Проверьте, что адрес возвращает корректный RSS или Atom.",
            )
        seen = state.get("last_seen_item", "")
        items = parsed.items
        if seen:
            new_items: list[FetchedItem] = []
            for item in items:
                guid = str(item.extra.get("guid", ""))
                if guid and guid == seen:
                    break
                new_items.append(item)
            items = new_items
        newest = ""
        if parsed.items:
            newest = str(parsed.items[0].extra.get("guid", ""))
        return FetchResult(
            ok=True,
            items=items,
            message=f"Найдено материалов: {len(items)}.",
            etag=etag,
            last_modified=last_modified,
            last_seen_item=newest or seen,
        )

    async def _download(
        self, url: str, state: dict[str, str]
    ) -> tuple[str, str, str, int, str]:
        """Fetch a feed with conditional headers. Returns (text, etag, lm, status, error)."""
        import asyncio
        import urllib.error
        import urllib.request

        headers = {"User-Agent": "TelegramChannelManagementSuite/1.2 (+feed reader)"}
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]

        def _run() -> tuple[str, str, str, int, str]:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    body = resp.read(2_000_000).decode("utf-8", errors="replace")
                    return (
                        body,
                        resp.headers.get("ETag", ""),
                        resp.headers.get("Last-Modified", ""),
                        int(resp.status),
                        "",
                    )
            except urllib.error.HTTPError as exc:
                if exc.code == 304:
                    return "", state.get("etag", ""), state.get("last_modified", ""), 304, ""
                return "", "", "", exc.code, f"Источник ответил ошибкой {exc.code}."
            except Exception as exc:  # pragma: no cover - network dependent
                return "", "", "", 0, f"Не удалось загрузить канал: {type(exc).__name__}."

        return await asyncio.to_thread(_run)


class RssContentProvider(_HttpFeedProvider):
    """RSS 2.0 feed provider."""

    kind = KIND_RSS
    title = "RSS"


class AtomContentProvider(_HttpFeedProvider):
    """Atom feed provider."""

    kind = KIND_ATOM
    title = "Atom"


class ManualContentProvider:
    """A public URL the owner pastes in, or material entered by hand."""

    kind = KIND_MANUAL
    title = "Вручную / публичная ссылка"

    def available(self) -> tuple[bool, str]:
        return True, ""

    async def fetch(self, query: ContentQuery, *, state: dict[str, str]) -> FetchResult:
        reference = (query.reference or "").strip()
        if not reference:
            return FetchResult(ok=False, message="Укажите ссылку или текст.")
        # A plain text/paragraph reference is stored verbatim (no network).
        if not reference.lower().startswith(("http://", "https://")):
            return FetchResult(
                ok=True,
                items=[FetchedItem(text=reference, source_url="")],
                message="Материал принят.",
            )
        title, text, error = await self._fetch_page(reference)
        if error:
            return FetchResult(
                ok=True,
                items=[FetchedItem(text="", source_url=reference, title=reference)],
                message="Текст страницы получить не удалось — сохранена только ссылка.",
                how_to_fix="Откройте ссылку и скопируйте текст вручную.",
            )
        return FetchResult(
            ok=True,
            items=[FetchedItem(title=title, text=text, source_url=reference)],
            message="Страница загружена.",
        )

    async def _fetch_page(self, url: str) -> tuple[str, str, str]:
        import asyncio
        import re as _re
        import urllib.request

        def _run() -> tuple[str, str, str]:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "TelegramChannelManagementSuite/1.2"}
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    html = resp.read(2_000_000).decode("utf-8", errors="replace")
            except Exception as exc:  # pragma: no cover - network dependent
                return "", "", type(exc).__name__
            title_match = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.I | _re.S)
            title = strip_html(title_match.group(1)) if title_match else url
            # Strip script/style then all tags for a rough body.
            body = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=_re.I | _re.S)
            return title, strip_html(body), ""

        return await asyncio.to_thread(_run)


class TelegramContentProvider:
    """Read a Telegram channel through the existing :class:`SessionProvider`.

    Telethon is never imported here (D-001). Content protection is respected: a
    protected source yields ``protected=True`` and only its link.

    ``resolve_provider`` is an async callable ``(account_id) -> SessionProvider``;
    it keeps the Content Service free of any Telegram-library detail.
    """

    kind = KIND_TELEGRAM
    title = "Telegram-канал"

    def __init__(self, resolve_provider=None) -> None:  # type: ignore[no-untyped-def]
        self._resolve = resolve_provider

    def available(self) -> tuple[bool, str]:
        if self._resolve is None:
            return False, "Нет доступа к аккаунту Telegram."
        return True, ""

    async def fetch(self, query: ContentQuery, *, state: dict[str, str]) -> FetchResult:
        reference = (query.reference or "").strip().lstrip("@")
        if not reference:
            return FetchResult(ok=False, message="Укажите канал Telegram.")
        if self._resolve is None:
            return FetchResult(
                ok=False,
                message="Для этого источника нужен подключённый аккаунт Telegram.",
                how_to_fix="Добавьте аккаунт в разделе «Аккаунты».",
            )
        try:
            provider = await self._resolve(query.account_id)
        except Exception as exc:
            from backend.app.providers.errors import TelegramProviderError

            if isinstance(exc, TelegramProviderError):
                return FetchResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)
            return FetchResult(
                ok=False,
                message="Для этого источника нужен подключённый аккаунт Telegram.",
                how_to_fix="Добавьте аккаунт в разделе «Аккаунты».",
            )
        try:
            result = await provider.fetch_channel_messages(
                reference, limit=query.limit, min_id=int(state.get("last_message_id", "0") or 0)
            )
        except Exception as exc:
            from backend.app.providers.errors import TelegramProviderError

            if isinstance(exc, TelegramProviderError):
                return FetchResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)
            logger.info("Telegram content fetch failed: %s", type(exc).__name__)
            return FetchResult(
                ok=False,
                message="Не удалось прочитать канал Telegram.",
                how_to_fix="Проверьте, что аккаунт подключён и видит канал.",
            )
        finally:
            with contextlib.suppress(Exception):
                await provider.aclose()

        if result.protected:
            return FetchResult(
                ok=True,
                protected=True,
                message=PROTECTED_MESSAGE,
                how_to_fix=PROTECTED_FIX,
                items=[
                    FetchedItem(
                        source_url=result.source_url,
                        source_channel=result.source_channel,
                        protected=True,
                    )
                ],
            )
        newest = 0
        items: list[FetchedItem] = []
        for msg in result.items:
            newest = max(newest, int(msg.message_id or 0))
            items.append(
                FetchedItem(
                    text=msg.text or "",
                    source_url=msg.url or "",
                    source_message_id=int(msg.message_id or 0),
                    source_channel=result.source_channel,
                    source_author=result.source_channel,
                    published_at=msg.date or "",
                    entities=list(msg.entities or []),
                    media_urls=list(msg.media_urls or []),
                    protected=bool(msg.protected),
                )
            )
        return FetchResult(
            ok=True,
            items=items,
            message=f"Найдено сообщений: {len(items)}.",
            last_seen_item=str(newest) if newest else "",
        )


#: Provider registry (kind → factory). New sources register here.
_PROVIDERS: dict[str, type] = {
    KIND_RSS: RssContentProvider,
    KIND_ATOM: AtomContentProvider,
    KIND_MANUAL: ManualContentProvider,
}


def build_content_provider(
    kind: str, *, resolve_provider=None  # type: ignore[no-untyped-def]
) -> ContentSourceProvider | None:
    """Return a provider for ``kind`` (or ``None`` when unknown)."""
    if kind == KIND_TELEGRAM:
        return TelegramContentProvider(resolve_provider)
    cls = _PROVIDERS.get(kind)
    if cls is None:
        return None
    return cls()


def provider_titles() -> dict[str, str]:
    return {
        KIND_TELEGRAM: TelegramContentProvider.title,
        KIND_RSS: RssContentProvider.title,
        KIND_ATOM: AtomContentProvider.title,
        KIND_MANUAL: ManualContentProvider.title,
    }


def stable_guid(*parts: object) -> str:
    """Return a stable, non-secret id from parts (for dedup markers)."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "KIND_ATOM",
    "KIND_MANUAL",
    "KIND_RSS",
    "KIND_TELEGRAM",
    "PROTECTED_FIX",
    "PROTECTED_MESSAGE",
    "AtomContentProvider",
    "ManualContentProvider",
    "RssContentProvider",
    "TelegramContentProvider",
    "build_content_provider",
    "parse_feed",
    "provider_titles",
    "stable_guid",
    "strip_html",
]
