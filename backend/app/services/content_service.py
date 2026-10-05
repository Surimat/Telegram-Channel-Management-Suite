"""Content Studio service (v1.2).

Owns sources, grabbing (with deduplication), cleaning, rights/attribution and
the content dashboard. Publication scheduling lives in
:mod:`backend.app.services.posting_service`; media in
:mod:`backend.app.services.media_service`.

Design notes:

* Telegram access goes through the existing :class:`SessionProvider`; Telethon is
  never imported here (D-001).
* Nothing bypasses a source's protection: a protected Telegram source keeps only
  its link and reports that plainly (D-006).
* Deduplication is deterministic (source hash, source message id, content hash,
  media hash) so the same material never creates dozens of copies.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.content import (
    MODE_MANUAL,
    RIGHTS_TITLES,
    STATUS_TITLES,
    VALID_MODES,
    ContentItem,
    ContentItemStatus,
    ContentSource,
    ContentSourceKind,
    ContentSourceStatus,
    RightsStatus,
)
from backend.app.db.repositories.content import (
    ContentItemRepository,
    ContentSourceRepository,
)
from backend.app.providers.content_base import ContentQuery, FetchedItem
from backend.app.providers.content_sources import (
    KIND_TELEGRAM,
    build_content_provider,
    provider_titles,
)
from backend.app.services.content_cleaner import CleanResult, clean_text
from backend.app.services.content_rewrite import (
    ContentRewriteService,
    RewriteResult,
)
from backend.app.services.events_service import EventsService

MODULE = "content"


def _load_keywords(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(k).strip().lower() for k in data if str(k).strip()]


def _matches_blocked(text: str, keywords: list[str]) -> bool:
    low = (text or "").lower()
    return any(k in low for k in keywords)

#: A source's content rights are unknown by default → autopublishing warns.
UNKNOWN_RIGHTS_WARNING = (
    "У этого материала права на использование не указаны. "
    "Публикация возможна, но убедитесь, что у вас есть право на использование."
)

#: Shown when a Telegram source forbids copying.
PROTECTED_NOTICE = "Контент нельзя автоматически получить из этого источника."

_WS_RE = re.compile(r"\s+")


class ContentError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


def content_hash(text: str) -> str:
    """Hash normalized text so whitespace-only edits do not create a new item."""
    normalized = _WS_RE.sub(" ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def source_hash(kind: str, reference: str, message_id: int | None = None, guid: str = "") -> str:
    """Hash a source identity (kind + reference + message id / guid)."""
    key = f"{kind}|{reference}|{message_id or ''}|{guid}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def media_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(slots=True)
class GrabOutcome:
    """Result of one grab run for a source."""

    source_id: str
    ok: bool
    new_items: int
    duplicates: int
    protected: bool
    message: str
    how_to_fix: str = ""
    item_ids: list[str] | None = None
    blocked: int = 0
    held: int = 0


class ContentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        resolve_provider=None,  # type: ignore[no-untyped-def]
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.sources = ContentSourceRepository(session)
        self.items = ContentItemRepository(session)
        self.events = EventsService(session)
        self._resolve = resolve_provider

    # --- providers -----------------------------------------------------------
    def provider_status(self) -> list[dict[str, object]]:
        titles = provider_titles()
        out: list[dict[str, object]] = []
        for kind in (KIND_TELEGRAM, "rss", "atom", "manual"):
            provider = build_content_provider(kind, resolve_provider=self._resolve)
            available, reason = (True, "") if provider is None else provider.available()
            out.append(
                {
                    "kind": kind,
                    "title": titles.get(kind, kind),
                    "available": available,
                    "requires_account": kind == KIND_TELEGRAM,
                    "message": reason,
                }
            )
        return out

    # --- sources -------------------------------------------------------------
    async def list_sources(self) -> list[ContentSource]:
        return await self.sources.list_all()

    async def create_source(
        self,
        *,
        kind: str,
        reference: str,
        title: str = "",
        enabled: bool = True,
        channel_id: str = "",
        account_id: str = "",
    ) -> ContentSource:
        try:
            kind_enum = ContentSourceKind(kind)
        except ValueError as exc:
            raise ContentError(
                "Неизвестный тип источника.",
                how_to_fix="Допустимо: telegram, rss, atom, manual.",
            ) from exc
        reference = (reference or "").strip()
        if not reference:
            raise ContentError("Укажите адрес или ссылку источника.")
        existing = await self.sources.find_by_reference(reference)
        if existing is not None:
            return existing
        source = ContentSource(
            kind=kind_enum,
            reference=reference,
            title=(title or "").strip() or reference,
            enabled=enabled,
            channel_id=channel_id,
            account_id=account_id,
        )
        await self.sources.add(source)
        await self.events.info(
            MODULE, f"Добавлен источник «{source.title}».", operation="source_create"
        )
        await self.session.commit()
        return source

    async def delete_source(self, source_id: str) -> None:
        source = await self.sources.get(source_id)
        if source is None:
            raise ContentError("Источник не найден.", status_code=404)
        await self.sources.delete(source)
        await self.session.commit()

    # --- grab ----------------------------------------------------------------
    async def grab(self, source_id: str, *, limit: int = 20) -> GrabOutcome:
        source = await self.sources.get(source_id)
        if source is None:
            raise ContentError("Источник не найден.", status_code=404)
        provider = build_content_provider(
            source.kind.value, resolve_provider=self._resolve
        )
        if provider is None:
            raise ContentError("Для этого типа источника нет обработчика.")
        query = ContentQuery(
            reference=source.reference,
            limit=limit,
            account_id=source.account_id,
        )
        state = {
            "etag": source.etag,
            "last_modified": source.last_modified,
            "last_seen_item": source.last_seen_item,
            "last_message_id": (
                source.last_seen_item
                if source.kind == ContentSourceKind.TELEGRAM
                else ""
            ),
        }
        result = await provider.fetch(query, state=state)
        source.last_fetch = utcnow()
        source.last_fetch_new = 0
        if not result.ok:
            source.status = ContentSourceStatus.ERROR
            source.last_error = result.message
            await self.session.commit()
            return GrabOutcome(
                source_id=source.id,
                ok=False,
                new_items=0,
                duplicates=0,
                protected=result.protected,
                message=result.message,
                how_to_fix=result.how_to_fix,
            )
        if result.protected:
            source.status = ContentSourceStatus.PROTECTED
            source.last_error = result.message
            await self.session.flush()
            await self.session.commit()
            return GrabOutcome(
                source_id=source.id,
                ok=True,
                new_items=0,
                duplicates=0,
                protected=True,
                message=PROTECTED_NOTICE,
                how_to_fix=result.how_to_fix
                or "Сохраните только ссылку на источник.",
            )

        new_ids: list[str] = []
        duplicates = 0
        blocked = 0
        held = 0
        quiet = self._quiet_now(source)
        blocked_keywords = _load_keywords(source.blocked_keywords)
        for fetched in result.items:
            if blocked_keywords and _matches_blocked(fetched.text, blocked_keywords):
                blocked += 1
                continue
            created = await self._store_fetched(source, fetched, held=quiet)
            if created is None:
                duplicates += 1
            else:
                new_ids.append(created.id)
                if created.held:
                    held += 1
        source.status = ContentSourceStatus.OK
        source.last_error = ""
        source.etag = result.etag or source.etag
        source.last_modified = result.last_modified or source.last_modified
        source.last_seen_item = result.last_seen_item or source.last_seen_item
        source.last_fetch_new = len(new_ids)
        note = ""
        if blocked:
            note += f" Отфильтровано по словам: {blocked}."
        if held:
            note += f" Удержано ночной модерацией: {held}."
        await self.events.info(
            MODULE,
            f"Импорт из «{source.title}»: новых {len(new_ids)}, дубликатов {duplicates}.",
            explanation=note.strip(),
            operation="grab",
        )
        await self.session.commit()
        return GrabOutcome(
            source_id=source.id,
            ok=True,
            new_items=len(new_ids),
            duplicates=duplicates,
            protected=False,
            message=(
                f"Новых материалов: {len(new_ids)}. Дубликатов: {duplicates}.{note}"
            ),
            item_ids=new_ids,
            blocked=blocked,
            held=held,
        )

    async def _store_fetched(
        self, source: ContentSource, fetched: FetchedItem, *, held: bool = False
    ) -> ContentItem | None:
        """Persist one fetched item, deduplicating. Returns None on duplicate."""
        guid = str(fetched.extra.get("guid", "") or "")
        shash = source_hash(source.kind.value, source.reference, fetched.source_message_id, guid)
        if fetched.source_message_id and source.id:
            existing = await self.items.find_by_source_message(source.id, fetched.source_message_id)
            if existing is not None:
                return None
        existing = await self.items.find_by_source_hash(shash)
        if existing is not None:
            return None
        chash = content_hash(fetched.text)
        if fetched.text.strip():
            dup = await self.items.find_by_content_hash(chash)
            if dup is not None:
                return None
        item = ContentItem(
            title=fetched.title,
            text=fetched.text,
            entities=json.dumps(fetched.entities, ensure_ascii=False),
            status=ContentItemStatus.IMPORTED,
            mode=MODE_MANUAL,
            source_id=source.id,
            source_message_id=fetched.source_message_id,
            source_url=fetched.source_url,
            source_channel=fetched.source_channel,
            source_author=fetched.source_author,
            imported_at=utcnow(),
            protected=fetched.protected,
            source_hash=shash,
            content_hash=chash,
            rights_status=RightsStatus.UNKNOWN,
            held=held,
            moderation_note="Удержано ночной модерацией." if held else "",
        )
        await self.items.add(item)
        return item

    def _quiet_now(self, source: ContentSource) -> bool:
        """True when ``source`` is inside its quiet hours (local time)."""
        if not source.quiet_hours_enabled:
            return False
        try:
            tz = ZoneInfo(source.quiet_hours_tz or "UTC")
        except Exception:
            tz = UTC
        hour = utcnow().astimezone(tz).hour
        start, end = source.quiet_hours_start, source.quiet_hours_end
        if start == end:
            return False
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    async def set_moderation(
        self,
        source_id: str,
        *,
        blocked_keywords: list[str] | None = None,
        quiet_hours_enabled: bool | None = None,
        quiet_hours_start: int | None = None,
        quiet_hours_end: int | None = None,
        quiet_hours_tz: str | None = None,
    ) -> ContentSource:
        """Update auto-moderation rules for a source (v1.2)."""
        source = await self.sources.get(source_id)
        if source is None:
            raise ContentError("Источник не найден.", status_code=404)
        if blocked_keywords is not None:
            cleaned = sorted({k.strip().lower() for k in blocked_keywords if k.strip()})
            source.blocked_keywords = json.dumps(cleaned, ensure_ascii=False)
        if quiet_hours_enabled is not None:
            source.quiet_hours_enabled = quiet_hours_enabled
        if quiet_hours_start is not None:
            source.quiet_hours_start = max(0, min(23, int(quiet_hours_start)))
        if quiet_hours_end is not None:
            source.quiet_hours_end = max(0, min(23, int(quiet_hours_end)))
        if quiet_hours_tz is not None:
            source.quiet_hours_tz = quiet_hours_tz.strip() or "UTC"
        await self.session.commit()
        return source

    async def release_held(self, item_id: str) -> ContentItem:
        """Release a held item into the active draft queue (v1.2)."""
        item = await self.items.get(item_id)
        if item is None:
            raise ContentError("Материал не найден.", status_code=404)
        item.held = False
        item.moderation_note = ""
        if item.status == ContentItemStatus.IMPORTED:
            item.status = ContentItemStatus.DRAFT
        await self.session.commit()
        return item

    # --- items ---------------------------------------------------------------
    async def list_items(
        self,
        *,
        status: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ContentItem], int]:
        status_enum = None
        if status:
            try:
                status_enum = ContentItemStatus(status)
            except ValueError as exc:
                raise ContentError("Неизвестный статус материала.") from exc
        return await self.items.list(
            status=status_enum, source_id=source_id, limit=limit, offset=offset
        )

    async def get_item(self, item_id: str) -> ContentItem:
        item = await self.items.get(item_id)
        if item is None:
            raise ContentError("Материал не найден.", status_code=404)
        return item

    async def update_item(self, item_id: str, **fields: object) -> ContentItem:
        item = await self.get_item(item_id)
        if "title" in fields and fields["title"] is not None:
            item.title = str(fields["title"])
        if "text" in fields and fields["text"] is not None:
            item.text = str(fields["text"])
            item.content_hash = content_hash(item.text)
        if "note" in fields and fields["note"] is not None:
            item.note = str(fields["note"])
        if fields.get("status"):
            try:
                item.status = ContentItemStatus(str(fields["status"]))
            except ValueError as exc:
                raise ContentError("Неизвестный статус материала.") from exc
        if fields.get("rights_status"):
            try:
                item.rights_status = RightsStatus(str(fields["rights_status"]))
            except ValueError as exc:
                raise ContentError("Неизвестный статус прав.") from exc
        if "attribution_enabled" in fields and fields["attribution_enabled"] is not None:
            item.attribution_enabled = bool(fields["attribution_enabled"])
        if fields.get("mode"):
            mode = str(fields["mode"])
            if mode not in VALID_MODES:
                raise ContentError("Неизвестный режим работы.")
            item.mode = mode
        if "scheduled_at" in fields:
            item.scheduled_at = _parse_dt(fields["scheduled_at"])
        await self.session.flush()
        await self.session.commit()
        return item

    async def delete_item(self, item_id: str) -> None:
        item = await self.get_item(item_id)
        await self.items.delete(item)
        await self.session.commit()

    # --- clean / rewrite -----------------------------------------------------
    async def clean_preview(self, item_id: str) -> CleanResult:
        item = await self.get_item(item_id)
        return clean_text(item.text)

    async def apply_clean(self, item_id: str, *, cleaned: str | None = None) -> ContentItem:
        item = await self.get_item(item_id)
        result = clean_text(item.text)
        item.cleaned_text = cleaned if cleaned is not None else result.cleaned
        item.content_hash = content_hash(item.cleaned_text or item.text)
        await self.events.info(MODULE, "Материал очищен.", operation="clean")
        await self.session.flush()
        await self.session.commit()
        return item

    async def revert_clean(self, item_id: str) -> ContentItem:
        item = await self.get_item(item_id)
        item.cleaned_text = ""
        await self.session.flush()
        await self.session.commit()
        return item

    async def rewrite_preview(self, item_id: str, *, mode: str) -> RewriteResult:
        item = await self.get_item(item_id)
        text = item.cleaned_text or item.text
        service = ContentRewriteService(settings=self.settings)
        return service.rewrite(text, mode=mode)

    async def apply_rewrite(self, item_id: str, *, mode: str) -> tuple[ContentItem, RewriteResult]:
        item = await self.get_item(item_id)
        result = await self.rewrite_preview(item_id, mode=mode)
        if result.ok and result.mode != "none":
            item.cleaned_text = result.text
            item.content_hash = content_hash(result.text)
            await self.events.info(MODULE, "Материал переработан ИИ.", operation="rewrite")
        await self.session.flush()
        await self.session.commit()
        return item, result

    # --- rights --------------------------------------------------------------
    def rights_warning(self, item: ContentItem) -> str:
        """Return a plain-language warning when rights are unknown, else ''."""
        if item.rights_status == RightsStatus.UNKNOWN:
            return UNKNOWN_RIGHTS_WARNING
        return ""

    def effective_text(self, item: ContentItem) -> str:
        """The text that would be published (cleaned if present, else raw)."""
        return item.cleaned_text or item.text

    def attribution_block(self, item: ContentItem) -> str:
        """Build the attribution block (source/author/link), or ''."""
        if not item.attribution_enabled:
            return ""
        parts: list[str] = []
        if item.source_channel:
            parts.append(f"Источник: {item.source_channel}")
        if item.source_author and item.source_author != item.source_channel:
            parts.append(f"Автор: {item.source_author}")
        if item.source_url:
            parts.append(item.source_url)
        return "\n".join(parts)

    def publish_text(self, item: ContentItem, *, override: str = "") -> str:
        """Final publish text: override or effective text + attribution."""
        base = override or self.effective_text(item)
        attribution = self.attribution_block(item)
        if attribution:
            return f"{base}\n\n{attribution}".strip()
        return base

    # --- dashboard -----------------------------------------------------------
    async def dashboard(self) -> dict[str, object]:
        counts = await self.items.status_counts()
        from datetime import timedelta

        day_start = datetime.now(UTC) - timedelta(days=1)
        from backend.app.db.repositories.content import PublicationRepository

        pubs = PublicationRepository(self.session)
        pub_counts = await pubs.counts()
        published_today = len(await pubs.published_since(day_start))
        return {
            "drafts": counts.get(ContentItemStatus.DRAFT.value, 0),
            "imported": counts.get(ContentItemStatus.IMPORTED.value, 0),
            "ready": counts.get(ContentItemStatus.READY.value, 0),
            "scheduled": pub_counts.get("scheduled", 0) + pub_counts.get("planned", 0),
            "published_today": published_today,
            "failed": counts.get(ContentItemStatus.FAILED.value, 0)
            + pub_counts.get("failed", 0),
            "status_counts": counts,
            "publication_counts": pub_counts,
        }

    def status_title(self, status: str) -> str:
        try:
            return STATUS_TITLES[ContentItemStatus(status)]
        except ValueError:
            return status

    def rights_title(self, status: str) -> str:
        try:
            return RIGHTS_TITLES[RightsStatus(status)]
        except ValueError:
            return status


def _parse_dt(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError as exc:
        raise ContentError("Не удалось разобрать дату.") from exc


__all__ = [
    "MODULE",
    "PROTECTED_NOTICE",
    "UNKNOWN_RIGHTS_WARNING",
    "ContentError",
    "ContentService",
    "GrabOutcome",
    "content_hash",
    "media_hash",
    "source_hash",
]
