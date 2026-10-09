"""Content Studio posting service (v1.2).

Publishes prepared content items to registry channels through a
:class:`PostingProvider` (bot by default; user account only in the expanded
mode). Handles:

* planning (draft → one publication per channel) and scheduling;
* a multi-channel calendar/grid view;
* inline buttons and a Telegram-like preview;
* markup validation before publishing (never publish broken markup silently);
* auto-delete of a post after a delay (durable, restart-safe);
* first comments into a channel's linked discussion group;
* idempotency: a lost connection is never silently retried (``uncertain``);
* night moderation: a held item is not published until the owner releases it.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.content import (
    VALID_MODES,
    ButtonSet,
    CommentPlan,
    ContentItem,
    ContentItemStatus,
    ContentSource,
    Publication,
    PublicationStatus,
)
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.content import (
    ButtonSetRepository,
    CommentPlanRepository,
    ContentItemRepository,
    ContentSourceRepository,
    MediaAssetRepository,
    PublicationRepository,
)
from backend.app.db.repositories.content_ops import ContentOperationRepository
from backend.app.providers.posting_base import PostingProvider, PostRequest
from backend.app.providers.types import InlineButton, OutgoingMedia
from backend.app.services.content_markup import (
    MAX_ALBUM_ITEMS,
    TelegramPreview,
    render_preview,
    validate_markup,
)
from backend.app.services.events_service import EventsService

MODULE = "content"

#: Durable job kind that drives due publications, auto-deletions and comments.
POSTING_JOB_KIND = "content.posting"

#: Comment-plan states.
COMMENT_PLANNED = "planned"
COMMENT_SENT = "sent"
COMMENT_FAILED = "failed"

#: Publication-level comment outcomes (Content Operations 2.0, D-116). Tracked
#: separately from the post so a lost comment never marks the post as failed.
COMMENT_NOT_PLANNED = "post"
COMMENT_POSTED = "comment_posted"
COMMENT_NOT_SUPPORTED = "comment_not_supported"

_BUTTON_ACTIONS = frozenset({"url", "callback", "webapp", "copy"})


class PostingError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class PublishOutcome:
    publication_id: str
    ok: bool
    status: str
    message_ids: list[int] = field(default_factory=list)
    message: str = ""
    how_to_fix: str = ""
    uncertain: bool = False


@dataclass(slots=True)
class TargetSpec:
    """One planned target channel (from the API).

    Each target may carry its own text override, AI profile and instructions so
    one source item can be published to several channels in different ways
    (Content Operations 2.0, requirement 6).
    """

    channel_id: str
    scheduled_at: datetime | None = None
    text_override: str = ""
    profile_key: str = ""
    ai_instructions: str = ""
    target_language: str = ""


def _parse_json(raw: str, default: object) -> object:
    try:
        return json.loads(raw or "")
    except (ValueError, TypeError):
        return default


def _operation(
    *,
    stage: str,
    status: str,
    item_id: str = "",
    publication_id: str = "",
    channel_id: str = "",
    detail: str = "",
):
    """Build a secret-free pipeline record (analytics/audit, requirement 11)."""
    from backend.app.db.base import utcnow
    from backend.app.db.models.content_ops import ContentOperation

    return ContentOperation(
        item_id=item_id,
        publication_id=publication_id,
        stage=stage,
        status=status,
        channel_id=channel_id,
        detail=detail,
        occurred_at=utcnow(),
    )


def _buttons_from(raw: object) -> list[list[InlineButton]]:
    rows: list[list[InlineButton]] = []
    for row in raw if isinstance(raw, list) else []:
        out_row: list[InlineButton] = []
        for btn in row if isinstance(row, list) else []:
            if not isinstance(btn, dict):
                continue
            action = str(btn.get("action", "url") or "url")
            out_row.append(
                InlineButton(
                    text=str(btn.get("text", "") or ""),
                    action=action if action in _BUTTON_ACTIONS else "url",
                    value=str(btn.get("value", "") or ""),
                )
            )
        out_row = [b for b in out_row if b.text]
        if out_row:
            rows.append(out_row)
    return rows


def validate_buttons(rows: list[list[InlineButton]]) -> list[str]:
    """Return human-readable button problems (empty list = valid)."""
    problems: list[str] = []
    if len(rows) > 8:
        problems.append("Слишком много рядов кнопок (максимум 8).")
    for i, row in enumerate(rows, start=1):
        if len(row) > 8:
            problems.append(f"В ряду {i} слишком много кнопок (максимум 8).")
        for btn in row:
            if not btn.text.strip():
                problems.append(f"В ряду {i} есть кнопка без текста.")
            if btn.action == "url" and not btn.value.lower().startswith(
                ("http://", "https://", "tg://")
            ):
                problems.append(f"Кнопка «{btn.text}»: ссылка должна начинаться с https:// или tg://.")
            if btn.action in {"callback", "webapp"} and not btn.value:
                problems.append(f"Кнопка «{btn.text}»: не задано значение.")
    return problems


class PostingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        resolve_bot_provider: Callable[..., object] | None = None,
        resolve_user_provider: Callable[..., object] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.items = ContentItemRepository(session)
        self.sources = ContentSourceRepository(session)
        self.media = MediaAssetRepository(session)
        self.publications = PublicationRepository(session)
        self.buttons = ButtonSetRepository(session)
        self.comments = CommentPlanRepository(session)
        self.channels = ChannelRepository(session)
        self.operations = ContentOperationRepository(session)
        self.events = EventsService(session)
        self._resolve_bot = resolve_bot_provider
        self._resolve_user = resolve_user_provider

    # --- provider selection --------------------------------------------------
    async def _provider_for(
        self, channel_id: str, *, prefer_user: bool = False
    ) -> tuple[PostingProvider, str, str]:
        """Return ``(provider, mode, note)`` for a registry channel.

        ``mode`` is ``"bot"`` (verified/legacy bot), ``"user"`` (expanded mode) or
        ``"none"``. The note explains any honesty caveat for the UI.
        """
        if prefer_user and self._resolve_user is not None:
            provider, account_id = await self._resolve_user(channel_id)
            if provider is not None:
                return provider, "user", f"Расширенный режим (аккаунт {account_id})."
        if self._resolve_bot is not None:
            provider, note = await self._resolve_bot(channel_id)
            if provider is not None:
                return provider, "bot", note
        return _NullPostingProvider(), "none", "Нет доступного способа публикации."

    # --- calendar / grid -----------------------------------------------------
    async def calendar(self, start: datetime, end: datetime) -> dict[str, object]:
        """Multi-channel calendar: publications in ``[start, end)`` by channel."""
        rows = await self.publications.list_range(start, end)
        channels, _total = await self.channels.list(limit=500)
        by_id = {c.id: c for c in channels}
        entries: list[dict[str, object]] = []
        for pub in rows:
            item = await self.items.get(pub.item_id)
            channel = by_id.get(pub.channel_id)
            entries.append(
                {
                    "publication_id": pub.id,
                    "item_id": pub.item_id,
                    "title": (item.title if item else "") or (item.text[:60] if item else ""),
                    "channel_id": pub.channel_id,
                    "channel_title": (channel.title if channel else "") or pub.channel_username,
                    "status": pub.status.value if hasattr(pub.status, "value") else str(pub.status),
                    "status_title": _PUBLICATION_TITLES.get(str(pub.status), str(pub.status)),
                    "scheduled_at": pub.scheduled_at.isoformat() if pub.scheduled_at else "",
                    "published_at": pub.published_at.isoformat() if pub.published_at else "",
                    "delete_at": pub.delete_at.isoformat() if pub.delete_at else "",
                }
            )
        entries.sort(key=lambda e: str(e["scheduled_at"] or e["published_at"]))
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "channels": [
                {"channel_id": c.id, "title": c.title or c.reference, "reference": c.reference}
                for c in channels
            ],
            "entries": entries,
        }

    # --- planning ------------------------------------------------------------
    async def plan(
        self,
        item_id: str,
        targets: list[TargetSpec],
        *,
        mode: str | None = None,
    ) -> list[Publication]:
        """Create one publication per target channel (draft → planned)."""
        item = await self._require_item(item_id)
        if not targets:
            raise PostingError("Не выбран ни один канал для публикации.")
        chosen_mode = mode or item.mode
        if chosen_mode not in VALID_MODES:
            raise PostingError("Неизвестный режим публикации.")

        created: list[Publication] = []
        for target in targets:
            channel = await self.channels.get(target.channel_id)
            if channel is None:
                raise PostingError(
                    f"Канал не найден: {target.channel_id}.", status_code=404
                )
            pub = await self.publications.find_by_idempotency(f"{item_id}:{channel.id}")
            if pub is not None and pub.status not in (
                PublicationStatus.CANCELLED,
                PublicationStatus.FAILED,
            ):
                if target.scheduled_at is not None:
                    pub.scheduled_at = target.scheduled_at
                    pub.status = PublicationStatus.SCHEDULED
                created.append(pub)
                continue
            pub = pub or Publication(item_id=item_id)
            pub.channel_id = channel.id
            pub.channel_username = channel.username or channel.reference
            pub.telegram_channel_id = channel.telegram_id
            pub.text_override = target.text_override
            pub.profile_key = target.profile_key
            pub.ai_instructions = target.ai_instructions
            pub.target_language = target.target_language
            pub.idempotency_key = f"{item_id}:{channel.id}"
            pub.scheduled_at = target.scheduled_at
            pub.status = (
                PublicationStatus.SCHEDULED
                if target.scheduled_at is not None
                else PublicationStatus.PLANNED
            )
            if not pub.id:
                await self.publications.add(pub)
            created.append(pub)

        item.mode = chosen_mode
        if item.status in (ContentItemStatus.IMPORTED, ContentItemStatus.DRAFT):
            item.status = (
                ContentItemStatus.SCHEDULED
                if any(p.scheduled_at for p in created)
                else ContentItemStatus.READY
            )
        for pub in created:
            await self.operations.add(
                _operation(
                    stage="schedule",
                    status=pub.status.value,
                    item_id=item_id,
                    publication_id=pub.id,
                    channel_id=pub.channel_id,
                )
            )
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Запланировано публикаций: {len(created)}.",
            explanation="Публикации появятся в календаре по каждому каналу.",
            operation="plan",
        )
        await self.session.commit()
        return created

    async def schedule(self, publication_id: str, when: datetime | None) -> Publication:
        pub = await self._require_publication(publication_id)
        pub.scheduled_at = when
        pub.status = PublicationStatus.SCHEDULED if when else PublicationStatus.PLANNED
        await self.session.commit()
        return pub

    async def cancel(self, publication_id: str) -> Publication:
        pub = await self._require_publication(publication_id)
        if pub.status == PublicationStatus.PUBLISHED:
            raise PostingError("Опубликованное сообщение нельзя отменить — используйте удаление.")
        pub.status = PublicationStatus.CANCELLED
        pub.enabled = False
        await self.session.commit()
        return pub

    # --- buttons -------------------------------------------------------------
    async def set_buttons(self, item_id: str, rows: list[list[dict[str, object]]]) -> ButtonSet:
        await self._require_item(item_id)
        parsed = _buttons_from(rows)
        problems = validate_buttons(parsed)
        if problems:
            raise PostingError("; ".join(problems))
        record = await self.buttons.for_item(item_id)
        if record is None:
            record = ButtonSet(item_id=item_id)
            await self.buttons.add(record)
        record.rows = json.dumps(
            [
                [{"text": b.text, "action": b.action, "value": b.value} for b in row]
                for row in parsed
            ],
            ensure_ascii=False,
        )
        await self.session.commit()
        return record

    # --- validation & preview ------------------------------------------------
    async def validate(self, item_id: str, channel_id: str = "") -> dict[str, object]:
        item = await self._require_item(item_id)
        text = self._effective_text(item)
        entities = _parse_json(item.entities, [])
        result = validate_markup(text, entities=entities if isinstance(entities, list) else [])
        buttons = await self._buttons_for(item)
        button_problems = validate_buttons(buttons)
        media = await self.media.list_for_item(item_id)
        if len(media) > MAX_ALBUM_ITEMS:
            result.issues.append(
                type(result.issues[0])(
                    kind="too_many_media",
                    message=f"В альбоме максимум {MAX_ALBUM_ITEMS} файлов.",
                )
            )
            result.ok = False
        return {
            "ok": result.ok and not button_problems,
            "issues": [
                {"kind": i.kind, "message": i.message, "line": i.line} for i in result.issues
            ],
            "button_problems": button_problems,
            "first_error": result.first_error,
            "fixed_text": result.fixed_text,
        }

    async def preview(self, item_id: str, channel_id: str = "") -> TelegramPreview:
        item = await self._require_item(item_id)
        text = self._effective_text(item)
        entities = _parse_json(item.entities, [])
        buttons = await self._buttons_for(item)
        media = await self.media.list_for_item(item_id)
        media_rows = [
            {"kind": _media_kind(m.kind), "filename": m.filename, "caption": ""} for m in media
        ]
        rows = [
            [{"text": b.text, "action": b.action, "value": b.value} for b in row]
            for row in buttons
        ]
        return render_preview(
            text,
            entities=entities if isinstance(entities, list) else [],
            buttons=rows,
            media=media_rows,
            is_album=len(media) > 1,
        )

    # --- publishing ----------------------------------------------------------
    async def publish(self, publication_id: str, *, force: bool = False) -> PublishOutcome:
        pub = await self._require_publication(publication_id)
        if pub.status == PublicationStatus.PUBLISHED and not force:
            return PublishOutcome(
                publication_id=pub.id,
                ok=True,
                status=pub.status.value,
                message_ids=_parse_json(pub.telegram_message_ids, []),  # type: ignore[arg-type]
                message="Уже опубликовано.",
            )
        item = await self._require_item(pub.item_id)
        if item.held and not force:
            return PublishOutcome(
                publication_id=pub.id,
                ok=False,
                status="held",
                message="Материал удерживается ночной модерацией.",
                how_to_fix="Снимите удержание в карточке материала.",
            )

        validation = await self.validate(item.id, pub.channel_id)
        if not validation["ok"] and not force:
            return PublishOutcome(
                publication_id=pub.id,
                ok=False,
                status="invalid",
                message=f"Сообщение не прошло проверку: {validation['first_error']}",
                how_to_fix="Исправьте текст или нажмите «Опубликовать принудительно».",
            )

        provider, mode, note = await self._provider_for(pub.channel_id)
        request = await self._build_request(item, pub)
        try:
            result = await provider.send(request)
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    await close()

        pub.attempts += 1
        if result.ok:
            pub.status = PublicationStatus.PUBLISHED
            pub.published_at = utcnow()
            pub.telegram_message_ids = json.dumps(result.message_ids)
            pub.error = ""
            item.status = ContentItemStatus.PUBLISHED
            await self.events.info(
                MODULE,
                f"Опубликовано в «{pub.channel_username}».",
                explanation=note,
                operation="publish",
            )
            await self.operations.add(
                _operation(
                    stage="publish",
                    status=pub.status.value,
                    item_id=item.id,
                    publication_id=pub.id,
                    channel_id=pub.channel_id,
                    detail=note,
                )
            )
            # A lost comment must never make the post itself fail (D-116).
            await self._after_publish(item, pub, provider, mode)
        else:
            pub.status = PublicationStatus.FAILED
            pub.error = result.message
            if result.uncertain:
                pub.error = (
                    result.message
                    + " Связь прервалась: сообщение могло быть доставлено. "
                    "Проверьте канал перед повтором."
                )
            await self.operations.add(
                _operation(
                    stage="publish",
                    status="failed",
                    item_id=item.id,
                    publication_id=pub.id,
                    channel_id=pub.channel_id,
                    detail=result.message,
                )
            )
            await self.events.record(
                level="error",
                module=MODULE,
                operation="publish",
                message="Не удалось опубликовать материал.",
                how_to_fix=result.how_to_fix or "Проверьте права бота в канале.",
                status="failed",
            )
        await self.session.commit()
        return PublishOutcome(
            publication_id=pub.id,
            ok=result.ok,
            status=pub.status.value,
            message_ids=result.message_ids,
            message=result.message,
            how_to_fix=result.how_to_fix,
            uncertain=result.uncertain,
        )

    async def _after_publish(
        self,
        item: ContentItem,
        pub: Publication,
        provider: PostingProvider,
        mode: str,
    ) -> None:
        # Auto-delete is durable: the tick loop deletes when due.
        if pub.delete_at is None and pub.channel_id:
            pub.delete_status = ""
        # First comment into the linked discussion group (if planned + enabled).
        plan = await self.comments.for_publication(pub.id)
        if plan is None or not plan.enabled or not plan.text:
            pub.comment_status = COMMENT_NOT_PLANNED
            return
        if mode != "bot":
            plan.status = COMMENT_FAILED
            plan.error = "Комментарии доступны только через бота канала."
            pub.comment_status = COMMENT_NOT_SUPPORTED
            await self.operations.add(
                _operation(
                    stage="comment",
                    status=COMMENT_NOT_SUPPORTED,
                    item_id=pub.item_id,
                    publication_id=pub.id,
                    channel_id=pub.channel_id,
                    detail="только через бота канала",
                )
            )
            return
        message_ids = _parse_json(pub.telegram_message_ids, [])
        if not message_ids:
            return
        due = utcnow() + timedelta(seconds=max(0, plan.delay_seconds))
        # Publish the comment immediately when the delay is zero, else on a tick.
        if plan.delay_seconds <= 0:
            await self._send_comment(plan, provider, pub, int(message_ids[0]))
        else:
            plan.status = COMMENT_PLANNED
            plan.telegram_message_id = None
            plan.discussion_chat_id = None
            plan.error = f"due:{due.isoformat()}"
            pub.comment_status = COMMENT_PLANNED

    async def _send_comment(
        self,
        plan: CommentPlan,
        provider: PostingProvider,
        pub: Publication,
        post_message_id: int,
    ) -> None:
        buttons = _buttons_from(_parse_json(plan.buttons, []))
        result = await provider.send_comment(
            pub.channel_username or str(pub.telegram_channel_id or ""),
            post_message_id,
            plan.text,
            buttons=buttons,
        )
        if result.ok:
            plan.status = COMMENT_SENT
            plan.telegram_message_id = result.message_ids[0] if result.message_ids else None
            plan.error = ""
            pub.comment_status = COMMENT_POSTED
            await self.operations.add(
                _operation(
                    stage="comment",
                    status=COMMENT_POSTED,
                    item_id=pub.item_id,
                    publication_id=pub.id,
                    channel_id=pub.channel_id,
                )
            )
        else:
            plan.status = COMMENT_FAILED
            plan.error = result.message
            pub.comment_status = COMMENT_FAILED
            await self.operations.add(
                _operation(
                    stage="comment",
                    status=COMMENT_FAILED,
                    item_id=pub.item_id,
                    publication_id=pub.id,
                    channel_id=pub.channel_id,
                    detail=result.message,
                )
            )

    async def retry(self, publication_id: str) -> PublishOutcome:
        return await self.publish(publication_id, force=True)

    # --- scheduled tick ------------------------------------------------------
    async def tick(self) -> dict[str, int]:
        """Process due publications, auto-deletions and comments (durable)."""
        now = utcnow()
        published = 0
        deleted = 0
        comments = 0

        for pub in await self.publications.due(now):
            outcome = await self.publish(pub.id)
            if outcome.ok:
                published += 1

        for pub in await self.publications.due_deletions(now):
            provider, _mode, _note = await self._provider_for(pub.channel_id)
            ids = _parse_json(pub.telegram_message_ids, [])
            try:
                result = await provider.delete(
                    pub.channel_username or str(pub.telegram_channel_id or ""),
                    [int(i) for i in ids],  # type: ignore[union-attr]
                )
            finally:
                close = getattr(provider, "close", None)
                if close is not None:
                    with contextlib.suppress(Exception):
                        await close()
            if result.ok:
                pub.deleted_at = utcnow()
                pub.status = PublicationStatus.CANCELLED
                pub.delete_status = "deleted"
                deleted += 1
                await self.operations.add(
                    _operation(
                        stage="delete",
                        status="deleted",
                        item_id=pub.item_id,
                        publication_id=pub.id,
                        channel_id=pub.channel_id,
                    )
                )
            else:
                # A delete error must never corrupt the publication history.
                pub.delete_status = "delete_failed"
                await self.operations.add(
                    _operation(
                        stage="delete",
                        status="delete_failed",
                        item_id=pub.item_id,
                        publication_id=pub.id,
                        channel_id=pub.channel_id,
                        detail=result.message,
                    )
                )

        for plan in await self.comments.due(now):
            pub = await self.publications.get(plan.publication_id)
            if pub is None or pub.status != PublicationStatus.PUBLISHED:
                continue
            provider, mode, _note = await self._provider_for(pub.channel_id)
            if mode != "bot":
                plan.status = COMMENT_FAILED
                plan.error = "Комментарии доступны только через бота канала."
                continue
            ids = _parse_json(pub.telegram_message_ids, [])
            if ids:
                await self._send_comment(plan, provider, pub, int(ids[0]))  # type: ignore[index]
                if plan.status == COMMENT_SENT:
                    comments += 1
            close = getattr(provider, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    await close()

        if published or deleted or comments:
            await self.session.commit()
        return {"published": published, "deleted": deleted, "comments": comments}

    async def due_count(self) -> int:
        now = utcnow()
        return len(await self.publications.due(now))

    # --- helpers -------------------------------------------------------------
    async def _build_request(self, item: ContentItem, pub: Publication) -> PostRequest:
        text = pub.text_override or self._effective_text(item)
        entities = _parse_json(item.entities, [])
        buttons = await self._buttons_for(item, pub)
        media_assets = await self.media.list_for_item(item.id)
        media = [
            OutgoingMedia(
                kind=_media_kind(m.kind),
                path=m.path,
                filename=m.filename,
                mime=m.mime,
            )
            for m in media_assets
        ]
        return PostRequest(
            channel=pub.channel_username or str(pub.telegram_channel_id or ""),
            text=text,
            entities=entities if isinstance(entities, list) else [],
            media=media,
            buttons=buttons,
        )

    async def _buttons_for(
        self, item: ContentItem, pub: Publication | None = None
    ) -> list[list[InlineButton]]:
        if pub is not None and pub.buttons_override:
            rows = _buttons_from(_parse_json(pub.buttons_override, []))
            if rows:
                return rows
        record = await self.buttons.for_item(item.id)
        if record is None or not record.enabled:
            rows = _buttons_from(_parse_json(item.buttons, []))
            return rows
        return _buttons_from(_parse_json(record.rows, []))

    def _effective_text(self, item: ContentItem) -> str:
        from backend.app.services.content_service import ContentService

        return ContentService(self.session).publish_text(item)

    async def _require_item(self, item_id: str) -> ContentItem:
        item = await self.items.get(item_id)
        if item is None:
            raise PostingError("Материал не найден.", status_code=404)
        return item

    async def _require_publication(self, publication_id: str) -> Publication:
        pub = await self.publications.get(publication_id)
        if pub is None:
            raise PostingError("Публикация не найдена.", status_code=404)
        return pub

    # --- night moderation helpers -------------------------------------------
    def quiet_now(self, source: ContentSource, *, now: datetime | None = None) -> bool:
        """True when ``source`` is currently inside its quiet hours."""
        if not source.quiet_hours_enabled:
            return False
        try:
            tz = ZoneInfo(source.quiet_hours_tz or "UTC")
        except Exception:
            tz = UTC
        local = (now or utcnow()).astimezone(tz)
        hour = local.hour
        start, end = source.quiet_hours_start, source.quiet_hours_end
        if start == end:
            return False
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end


class _NullPostingProvider:
    """Honest no-op provider used when no posting route is available."""

    kind = "none"

    async def capabilities(self, channel: str):  # type: ignore[no-untyped-def]
        from backend.app.providers.posting_base import PostCapability

        return PostCapability(text=False, message="Нет доступного способа публикации.")

    async def send(self, request: PostRequest):  # type: ignore[no-untyped-def]
        from backend.app.providers.types import PostSendResult

        return PostSendResult(
            ok=False,
            message="Нет доступного способа публикации.",
            how_to_fix="Подключите бота к каналу в разделе «Боты».",
        )

    async def send_comment(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        from backend.app.providers.types import PostSendResult

        return PostSendResult(ok=False, message="Нет доступного способа публикации.")

    async def edit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        from backend.app.providers.types import PostSendResult

        return PostSendResult(ok=False, message="Нет доступного способа публикации.")

    async def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        from backend.app.providers.types import PostSendResult

        return PostSendResult(ok=False, message="Нет доступного способа публикации.")

    async def pin(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        from backend.app.providers.types import PostSendResult

        return PostSendResult(ok=False, message="Нет доступного способа публикации.")

    async def linked_discussion(self, channel: str) -> int | None:
        return None

    async def close(self) -> None:
        return None


_PUBLICATION_TITLES = {
    PublicationStatus.PLANNED: "Запланировано",
    PublicationStatus.SCHEDULED: "В расписании",
    PublicationStatus.PUBLISHING: "Публикуется",
    PublicationStatus.PUBLISHED: "Опубликовано",
    PublicationStatus.FAILED: "Ошибка",
    PublicationStatus.CANCELLED: "Отменено",
}


def _media_kind(raw: str) -> str:
    value = (raw or "").lower()
    if value in {"video", "audio", "document", "photo"}:
        return value
    if value in {"image", "picture"}:
        return "photo"
    return "document"


__all__ = [
    "COMMENT_FAILED",
    "COMMENT_NOT_PLANNED",
    "COMMENT_NOT_SUPPORTED",
    "COMMENT_PLANNED",
    "COMMENT_POSTED",
    "COMMENT_SENT",
    "MODULE",
    "POSTING_JOB_KIND",
    "PostingError",
    "PostingService",
    "PublishOutcome",
    "TargetSpec",
    "validate_buttons",
]
