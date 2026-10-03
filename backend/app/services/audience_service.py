"""Audience service (PHASE 5): sources, scanning, deduplication, tags, export.

This module owns the whole audience vertical slice's business logic and depends
only on the :class:`AudienceProvider` abstraction (never Telethon, never a raw
account provider — decisions D-001/D-026).

Design guarantees:

* **Streaming scan**: a scan is a durable job whose handler processes one bounded
  page per call (``audience_scan_chunk_size`` rows). The full member list is
  never buffered in memory, which keeps weak Windows machines responsive and
  makes pause/cancel immediate.
* **Honest completeness**: when Telegram exposes only part of an audience the
  source is marked ``PARTIAL`` (or ``NO_ACCESS``), never silently presented as a
  full list. FloodWait/privacy/admin limits are surfaced, never bypassed (D-006).
* **Durable & restart-safe**: progress (``scanned_offset``) lives on the source
  row; a scan left ``SCANNING`` after a crash is safely reset to ``PAUSED`` so it
  can be resumed and cannot wedge the system.
* **Privacy**: full phone numbers are never stored; masked phones only when
  ``AUDIENCE_STORE_PII`` is enabled. Exports are explicit about their PII choice.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import new_id, utcnow
from backend.app.db.models.audience import (
    AudienceSource,
    AudienceUser,
    Completeness,
    MemberStatus,
    ScanStatus,
    SourceType,
    SourceUserLink,
)
from backend.app.db.repositories.audience import (
    AudienceSourceRepository,
    AudienceUserRepository,
    SourceUserLinkRepository,
)
from backend.app.providers.audience_base import AudienceProvider
from backend.app.providers.errors import (
    ChatAdminRequiredError,
    EntityNotFoundError,
    FloodWaitError,
    PrivacyRestrictedError,
    TelegramProviderError,
)
from backend.app.providers.registry import build_audience_provider
from backend.app.providers.session_base import SessionProvider
from backend.app.services.events_service import EventsService
from backend.app.services.queue_service import QueueService
from backend.app.services.session_service import SessionProviderFactory, SessionService

SCAN_JOB_KIND = "audience.scan"
MODULE = "audience.audience_service"

SOURCE_TYPE_LABELS = {
    SourceType.CHANNEL: "Публичный канал",
    SourceType.GROUP: "Группа",
    SourceType.ENTITY: "Telegram-сущность",
    SourceType.UNKNOWN: "Неизвестно",
}

COMPLETENESS_EXPLANATIONS = {
    Completeness.COMPLETE: (
        "Получен полный список участников, который предоставил Telegram."
    ),
    Completeness.PARTIAL: (
        "Telegram не предоставил полный список участников. "
        "Результат считается частичным."
    ),
    Completeness.NO_ACCESS: (
        "Telegram не раскрывает список участников для этого аккаунта. "
        "Данные не получены."
    ),
    Completeness.FAILED: "Сканирование завершилось ошибкой.",
    Completeness.UNKNOWN: "Сканирование ещё не выполнялось.",
}

# Audience provider factory signature (injectable for tests).
AudienceProviderFactory = Callable[..., AudienceProvider]

EXPORT_FIELDS = (
    "telegram_user_id",
    "username",
    "first_name",
    "last_name",
    "display_name",
    "is_bot",
    "is_deleted",
    "is_premium",
    "status",
    "score",
    "tags",
    "sources",
    "first_seen_at",
    "last_seen_at",
)
PII_EXPORT_FIELDS = ("phone_masked",)


class AudienceServiceError(Exception):
    """An audience operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class SourcePreview:
    """What will happen if the operator confirms a scan (dry-run, D-021)."""

    source_id: str
    title: str
    username: str
    source_type: str
    reference: str
    account_id: str
    account_label: str
    mode: str
    batch_size: int
    chunk_size: int
    estimated_total: int | None
    filters: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScanBatchOutcome:
    """Result of processing one scan chunk (persisted to the source row)."""

    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    errors: int = 0
    offset: int = 0
    exhausted: bool = False
    truncated: bool = False
    reported_total: int | None = None
    error: str = ""

    @property
    def done(self) -> bool:
        return self.exhausted or bool(self.error)


@dataclass(slots=True)
class ExportResult:
    """A generated export file (never sent anywhere automatically)."""

    path: str
    filename: str
    format: str
    fields: list[str]
    includes_pii: bool
    row_count: int
    size_bytes: int
    source_id: str = ""


def _json_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(v) for v in value] if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


_FILTER_PRESETS = {
    "active": {
        "label": "Активные пользователи",
        "description": "Не удалённые, не боты.",
        "filters": {"is_bot": False, "is_deleted": False},
    },
    "with_username": {
        "label": "Есть username",
        "description": "Пользователи, у которых указан @username.",
        "filters": {"has_username": True, "is_bot": False},
    },
    "not_bots": {
        "label": "Не боты",
        "description": "Все живые аккаунты, включая удалённые.",
        "filters": {"is_bot": False},
    },
    "premium": {
        "label": "Telegram Premium",
        "description": "Пользователи с Premium (если Telegram раскрыл поле).",
        "filters": {"is_premium": True, "is_bot": False},
    },
}


class AudienceService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        session_provider_factory: SessionProviderFactory | None = None,
        audience_provider: AudienceProvider | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.sources = AudienceSourceRepository(session)
        self.users = AudienceUserRepository(session)
        self.links = SourceUserLinkRepository(session)
        self.queue = QueueService(session)
        self.events = EventsService(session)
        self._session_provider_factory = session_provider_factory
        self._audience_override = audience_provider

    # ------------------------------------------------------------------
    # Provider resolution (account → SessionProvider → AudienceProvider)
    # ------------------------------------------------------------------
    def _session_service(self) -> SessionService:
        kwargs: dict[str, Any] = {"settings": self.settings}
        if self._session_provider_factory is not None:
            kwargs["provider_factory"] = self._session_provider_factory
        return SessionService(self.session, **kwargs)

    async def _resolve_account(self, source: AudienceSource) -> Any:
        """Return a usable user account for scanning ``source``."""
        service = self._session_service()
        account = None
        if source.account_id:
            account = await service.get(source.account_id)
        if account is None:
            for candidate in await service.list_accounts(enabled=True):
                if candidate.status.value == "online":
                    account = candidate
                    break
        if account is None:
            raise AudienceServiceError(
                "Нет доступного Telegram-аккаунта для сканирования.",
                how_to_fix=(
                    "Добавьте аккаунт в разделе «Аккаунты» и проверьте, "
                    "что он в статусе «онлайн»."
                ),
            )
        return service, account

    async def _audience_provider_for(self, source: AudienceSource) -> AudienceProvider:
        if self._audience_override is not None:
            return self._audience_override
        service, account = await self._resolve_account(source)
        session_provider: SessionProvider = service.provider_for(account)
        return build_audience_provider(
            session_provider, provider_name=self.settings.telegram_provider, settings=self.settings
        )

    # ------------------------------------------------------------------
    # Sources CRUD
    # ------------------------------------------------------------------
    async def add_source(
        self,
        *,
        reference: str,
        title: str = "",
        source_type: SourceType | str = SourceType.UNKNOWN,
        account_id: str | None = None,
        enabled: bool = True,
    ) -> AudienceSource:
        reference = (reference or "").strip()
        if not reference:
            raise AudienceServiceError(
                "Укажите username, ссылку или ID источника.",
                how_to_fix="Например: @durov, https://t.me/durov или 123456789.",
            )
        stype = SourceType(source_type) if isinstance(source_type, str) else source_type
        username, telegram_id = self._parse_reference(reference)
        source = AudienceSource(
            reference=reference,
            title=(title or "").strip(),
            username=username,
            telegram_id=telegram_id,
            source_type=stype,
            account_id=account_id or None,
            enabled=enabled,
            scan_status=ScanStatus.IDLE,
            completeness=Completeness.UNKNOWN,
        )
        await self.sources.add(source)
        await self.events.info(
            MODULE,
            f"Источник «{reference}» добавлен.",
            operation="add_source",
            status="ok",
        )
        return source

    @staticmethod
    def _parse_reference(reference: str) -> tuple[str, int | None]:
        """Split an operator reference into (username, telegram_id)."""
        ref = reference.strip()
        if ref.startswith("https://t.me/") or ref.startswith("t.me/"):
            ref = ref.split("t.me/", 1)[1]
        ref = ref.strip("/").lstrip("@")
        if not ref:
            return "", None
        if ref.lstrip("-").isdigit():
            return "", int(ref)
        return ref, None

    async def get_source(self, source_id: str) -> AudienceSource | None:
        return await self.sources.get(source_id)

    async def list_sources(self, **kwargs: Any) -> tuple[list[AudienceSource], int]:
        return await self.sources.list(**kwargs)

    async def update_source(self, source_id: str, **fields: Any) -> AudienceSource:
        source = await self.sources.get(source_id)
        if source is None:
            raise AudienceServiceError("Источник не найден.", status_code=404)
        for key in ("title", "username", "enabled", "account_id"):
            if key in fields and fields[key] is not None:
                setattr(source, key, fields[key])
        if "source_type" in fields and fields["source_type"] is not None:
            source.source_type = SourceType(fields["source_type"])
        await self.session.flush()
        return source

    async def delete_source(self, source_id: str) -> None:
        source = await self.sources.get(source_id)
        if source is None:
            raise AudienceServiceError("Источник не найден.", status_code=404)
        await self.sources.delete(source)

    async def detect_source_type(self, reference: str) -> tuple[str, str, int | None]:
        """Return (detected_type, title/username, telegram_id) without network."""
        username, telegram_id = self._parse_reference(reference)
        if username:
            kind = SourceType.CHANNEL
        elif telegram_id is not None:
            kind = SourceType.ENTITY
        else:
            kind = SourceType.UNKNOWN
        return kind.value, username, telegram_id

    async def check_source(self, source_id: str) -> dict[str, Any]:
        """Resolve the source with Telegram and report reachability (no scan)."""
        source = await self.sources.get(source_id)
        if source is None:
            raise AudienceServiceError("Источник не найден.", status_code=404)
        provider = await self._audience_provider_for(source)
        try:
            ref = source.reference or source.username or str(source.telegram_id or "")
            entity = await provider.resolve_entity(ref)
        except TelegramProviderError as exc:
            source.last_error = exc.message
            await self.session.flush()
            return {
                "ok": False,
                "message": exc.message,
                "how_to_fix": exc.how_to_fix,
                "completeness": source.completeness.value,
            }
        # Persist resolved details.
        if entity.id:
            source.telegram_id = entity.id
        if entity.username:
            source.username = entity.username
        if entity.title:
            source.title = entity.title
        if entity.kind in {"channel", "group"}:
            source.source_type = (
                SourceType.CHANNEL if entity.kind == "channel" else SourceType.GROUP
            )
        source.reported_total = entity.participants_count
        if entity.participants_hidden:
            source.completeness = Completeness.NO_ACCESS
        source.last_error = ""
        await self.session.flush()
        return {
            "ok": True,
            "title": entity.title,
            "username": entity.username,
            "telegram_id": entity.id,
            "kind": entity.kind,
            "participants_count": entity.participants_count,
            "participants_hidden": entity.participants_hidden,
            "message": "Источник доступен." if not entity.participants_hidden else (
                COMPLETENESS_EXPLANATIONS[Completeness.NO_ACCESS]
            ),
            "how_to_fix": "" if not entity.participants_hidden else (
                "Используйте публичный источник или аккаунт с доступом."
            ),
        }

    # ------------------------------------------------------------------
    # Scan preview / dry run
    # ------------------------------------------------------------------
    async def preview_scan(self, source_id: str) -> SourcePreview:
        source = await self.sources.get(source_id)
        if source is None:
            raise AudienceServiceError("Источник не найден.", status_code=404)
        _service, account = await self._resolve_account(source)
        account_label = (
            account.display_name or account.username or (account.phone_masked or account.id)
        )
        notes = [
            "Сканирование идёт порциями и не перегружает компьютер.",
            "Telegram может вернуть только часть списка — это будет явно показано.",
        ]
        if source.reported_total:
            notes.append(
                f"Telegram сообщает о ~{source.reported_total} участниках; "
                "фактически может быть получено меньше."
            )
        return SourcePreview(
            source_id=source.id,
            title=source.title or source.reference,
            username=source.username,
            source_type=SOURCE_TYPE_LABELS.get(source.source_type, "Неизвестно"),
            reference=source.reference,
            account_id=account.id,
            account_label=account_label,
            mode="portable (порциями)",
            batch_size=self.settings.audience_scan_batch_size,
            chunk_size=self.settings.audience_scan_chunk_size,
            estimated_total=source.reported_total,
            filters={},
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Scan job lifecycle
    # ------------------------------------------------------------------
    async def start_scan(self, source_id: str) -> Any:
        """Create a durable scan job and mark the source as scanning."""
        source = await self.sources.get(source_id)
        if source is None:
            raise AudienceServiceError("Источник не найден.", status_code=404)
        if source.scan_status == ScanStatus.SCANNING:
            raise AudienceServiceError(
                "Сканирование уже выполняется.",
                how_to_fix="Дождитесь завершения или поставьте его на паузу.",
            )
        source.scan_status = ScanStatus.SCANNING
        source.scanned_offset = 0
        source.discovered_count = 0
        source.new_count = 0
        source.duplicate_count = 0
        source.error_count = 0
        source.last_error = ""
        source.completeness = Completeness.UNKNOWN
        source.last_scan_at = utcnow()
        job = await self.queue.enqueue(
            kind=SCAN_JOB_KIND,
            payload={"source_id": source.id},
            group_key=source.id,
            max_attempts=1,
        )
        source.scan_job_id = job.id
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Сканирование источника «{source.title or source.reference}» запущено.",
            operation="start_scan",
            status="ok",
        )
        return job

    async def pause_scan(self, source_id: str) -> AudienceSource:
        source = await self._require_source(source_id)
        source.scan_status = ScanStatus.PAUSED
        await self.session.flush()
        return source

    async def resume_scan(self, source_id: str) -> AudienceSource:
        source = await self._require_source(source_id)
        if source.scan_status not in {ScanStatus.PAUSED}:
            raise AudienceServiceError(
                "Сканирование не на паузе.",
                how_to_fix="Поставьте сканирование на паузу, чтобы затем продолжить.",
            )
        source.scan_status = ScanStatus.SCANNING
        # Re-enqueue so the durable queue drives continuation from scanned_offset.
        job = await self.queue.enqueue(
            kind=SCAN_JOB_KIND,
            payload={"source_id": source.id, "resume": True},
            group_key=source.id,
            max_attempts=1,
        )
        source.scan_job_id = job.id
        await self.session.flush()
        return source

    async def cancel_scan(self, source_id: str) -> AudienceSource:
        source = await self._require_source(source_id)
        source.scan_status = ScanStatus.CANCELLED
        await self.session.flush()
        return source

    async def _require_source(self, source_id: str) -> AudienceSource:
        source = await self.sources.get(source_id)
        if source is None:
            raise AudienceServiceError("Источник не найден.", status_code=404)
        return source

    # ------------------------------------------------------------------
    # Scan execution (one bounded batch per call; called by the scheduler)
    # ------------------------------------------------------------------
    async def process_scan_batch(
        self, source_id: str, *, batch_size: int | None = None
    ) -> ScanBatchOutcome:
        """Fetch and persist one page of participants, then update progress."""
        source = await self.sources.get(source_id)
        if source is None:
            return ScanBatchOutcome(error="Источник не найден.")
        if source.scan_status == ScanStatus.PAUSED:
            return ScanBatchOutcome(offset=source.scanned_offset, exhausted=False)
        if source.scan_status in {ScanStatus.CANCELLED, ScanStatus.COMPLETED}:
            return ScanBatchOutcome(offset=source.scanned_offset, exhausted=True)

        provider = await self._audience_provider_for(source)
        ref = source.reference or source.username or str(source.telegram_id or "")
        batch = batch_size or self.settings.audience_scan_batch_size
        offset = source.scanned_offset
        limit = self.settings.audience_scan_max_users

        try:
            pages = await provider.iter_participant_pages(
                ref, offset=offset, batch_size=batch, limit=limit
            )
        except FloodWaitError as exc:
            source.scan_status = ScanStatus.PAUSED
            source.last_error = exc.message
            await self.session.flush()
            await self.events.error(
                MODULE,
                exc.message,
                how_to_fix=exc.how_to_fix,
                operation="scan",
                status="flood_wait",
            )
            return ScanBatchOutcome(offset=offset, exhausted=False, error=exc.message)
        except (PrivacyRestrictedError, ChatAdminRequiredError) as exc:
            source.scan_status = ScanStatus.FAILED
            source.completeness = Completeness.NO_ACCESS
            source.last_error = exc.message
            source.last_scan_finished_at = utcnow()
            await self.session.flush()
            await self.events.error(
                MODULE, exc.message, how_to_fix=exc.how_to_fix, operation="scan",
                status="no_access",
            )
            return ScanBatchOutcome(offset=offset, exhausted=True, error=exc.message)
        except EntityNotFoundError as exc:
            source.scan_status = ScanStatus.FAILED
            source.completeness = Completeness.FAILED
            source.last_error = exc.message
            source.last_scan_finished_at = utcnow()
            await self.session.flush()
            await self.events.error(
                MODULE, exc.message, how_to_fix=exc.how_to_fix, operation="scan",
                status="failed",
            )
            return ScanBatchOutcome(offset=offset, exhausted=True, error=exc.message)
        except TelegramProviderError as exc:
            source.error_count += 1
            source.last_error = exc.message
            source.scan_status = ScanStatus.FAILED
            source.completeness = Completeness.FAILED
            source.last_scan_finished_at = utcnow()
            await self.session.flush()
            return ScanBatchOutcome(offset=offset, exhausted=True, error=exc.message)

        page = pages[0] if pages else None
        if page is None or not page.users:
            # An empty page normally just means the list is exhausted. Telegram
            # only "refuses" the list on the very first page — later empty pages
            # are the natural end of a finite member list.
            if page is not None and page.total and not page.users and offset == 0:
                source.completeness = Completeness.NO_ACCESS
            return ScanBatchOutcome(
                offset=offset,
                exhausted=True,
                reported_total=page.total if page else None,
            )

        outcome = await self._persist_page(source, page.users, offset)
        outcome.reported_total = page.total
        outcome.truncated = page.truncated
        return outcome

    async def _persist_page(
        self, source: AudienceSource, users: list[Any], offset: int
    ) -> ScanBatchOutcome:
        """Deduplicate + upsert one page and record source links."""
        now = utcnow()
        telegram_ids = [int(u.id) for u in users]
        existing = await self.users.get_many_by_telegram_ids(telegram_ids)

        new_users: list[AudienceUser] = []
        for u in users:
            if u.id in existing:
                # Duplicate: refresh volatile fields only; never create a second row.
                row = existing[u.id]
                row.username = u.username or row.username
                row.first_name = u.first_name or row.first_name
                row.last_name = u.last_name or row.last_name
                row.display_name = u.display_name or row.display_name
                row.last_seen_at = now
                if u.is_premium is not None:
                    row.is_premium = u.is_premium
                row.is_bot = bool(u.is_bot)
            else:
                row = AudienceUser(
                    telegram_user_id=int(u.id),
                    username=u.username,
                    first_name=u.first_name,
                    last_name=u.last_name,
                    display_name=self._display_name(u),
                    is_bot=bool(u.is_bot),
                    is_deleted=False,
                    is_premium=u.is_premium,
                    status=self._derive_status(u),
                    first_seen_at=now,
                    last_seen_at=now,
                )
                self._apply_score(row)
                new_users.append(row)
                existing[u.id] = row

        if new_users:
            await self.users.add_many(new_users)
        new_count = len(new_users)
        duplicate_count = len(users) - new_count

        # Link every user (new and existing) to this source (dedup at link level).
        user_ids = [existing[u.id].id for u in users]
        linked = await self.links.existing_user_ids(source.id, user_ids)
        pending: list[SourceUserLink] = []
        for u in users:
            row = existing[u.id]
            if row.id in linked:
                continue
            pending.append(
                SourceUserLink(
                    source_id=source.id,
                    user_id=row.id,
                    first_seen_at=now,
                    last_seen_at=now,
                    discovery_method="participants",
                )
            )
        if pending:
            await self.links.add_many(pending)

        source.scanned_offset = offset + len(users)
        source.discovered_count += len(users)
        source.new_count += new_count
        source.duplicate_count += duplicate_count
        await self.session.flush()
        return ScanBatchOutcome(
            fetched=len(users),
            new=new_count,
            duplicates=duplicate_count,
            offset=source.scanned_offset,
            exhausted=False,
        )

    # ------------------------------------------------------------------
    # Job handler + completion bookkeeping
    # ------------------------------------------------------------------
    async def run_scan_chunk(self) -> None:
        """Process up to ``chunk_size`` users for a scanning source (one tick).

        Called by the scheduler handler on the *same* session. The handler owns
        commits between chunks so partial progress survives a crash.
        """
        rows, _ = await self.sources.list(status=ScanStatus.SCANNING, limit=1)
        if not rows:
            return
        source = rows[0]
        remaining = self.settings.audience_scan_chunk_size
        batch = self.settings.audience_scan_batch_size
        while remaining > 0:
            outcome = await self.process_scan_batch(
                source.id, batch_size=min(batch, remaining)
            )
            remaining -= max(outcome.fetched, 1)
            if outcome.error and outcome.exhausted:
                break
            if outcome.exhausted:
                await self._finish_scan(source, outcome)
                break
            # A paused scan (FloodWait) leaves the loop without completing.
            if source.scan_status == ScanStatus.PAUSED:
                break
            await self.session.commit()

    async def _finish_scan(self, source: AudienceSource, outcome: ScanBatchOutcome) -> None:
        if source.completeness == Completeness.NO_ACCESS:
            source.scan_status = ScanStatus.FAILED
        else:
            source.scan_status = ScanStatus.COMPLETED
            source.completeness = self._completeness_for(source, outcome)
        source.last_scan_finished_at = utcnow()
        if source.completeness in {Completeness.PARTIAL}:
            source.last_error = COMPLETENESS_EXPLANATIONS[Completeness.PARTIAL]
        await self.session.flush()
        await self.session.commit()
        await self.events.info(
            MODULE,
            self.explain_scan_result(source),
            operation="scan_finished",
            status=source.scan_status.value,
        )

    def _completeness_for(
        self, source: AudienceSource, outcome: ScanBatchOutcome
    ) -> Completeness:
        total = outcome.reported_total or source.reported_total
        collected = source.discovered_count
        if source.completeness == Completeness.NO_ACCESS:
            return Completeness.NO_ACCESS
        if total is not None and collected < total:
            return Completeness.PARTIAL
        if outcome.truncated:
            return Completeness.PARTIAL
        return Completeness.COMPLETE

    def explain_scan_result(self, source: AudienceSource) -> str:
        """Human sentence for the UI, honest about partial results (D-026)."""
        if source.completeness == Completeness.NO_ACCESS:
            return (
                "Telegram не предоставил список участников. "
                "Результат получить не удалось."
            )
        base = f"Получено {source.discovered_count} пользователей."
        if source.completeness == Completeness.PARTIAL:
            extra = " Telegram не предоставил полный список участников. "
            extra += "Результат считается частичным."
            return base + extra
        if source.completeness == Completeness.COMPLETE:
            return base + " Получен полный список, доступный Telegram."
        return base

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------
    async def recover(self) -> int:
        """Reset scans left mid-flight by a crash to a safe, resumable state.

        A ``SCANNING`` source becomes ``PAUSED`` (progress preserved) so it never
        wedges the system and the operator can resume it (decision D-028).
        """
        rows, _ = await self.sources.list(status=ScanStatus.SCANNING, limit=1000)
        for source in rows:
            source.scan_status = ScanStatus.PAUSED
            source.last_error = (
                "Сканирование было прервано перезапуском. Его можно продолжить."
            )
        if rows:
            await self.session.flush()
        return len(rows)

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------
    async def list_tags(self) -> list[dict[str, Any]]:
        users, _ = await self.users.list(limit=1000000)
        counts: dict[str, int] = {}
        for u in users:
            for tag in _json_list(u.tags):
                counts[tag] = counts.get(tag, 0) + 1
        return [
            {"name": name, "count": counts[name]}
            for name in sorted(counts)
        ]

    async def add_tags(self, user_ids: list[str], tags: list[str]) -> int:
        tags = [t.strip() for t in tags if t and t.strip()]
        if not tags:
            return 0
        updated = 0
        for user_id in user_ids:
            user = await self.users.get(user_id)
            if user is None:
                continue
            current = _json_list(user.tags)
            for tag in tags:
                if tag not in current:
                    current.append(tag)
            user.tags = json.dumps(current)
            updated += 1
        await self.session.flush()
        return updated

    async def remove_tags(self, user_ids: list[str], tags: list[str]) -> int:
        updated = 0
        for user_id in user_ids:
            user = await self.users.get(user_id)
            if user is None:
                continue
            current = [t for t in _json_list(user.tags) if t not in set(tags)]
            user.tags = json.dumps(current)
            updated += 1
        await self.session.flush()
        return updated

    async def rename_tag(self, old: str, new: str) -> int:
        users, _ = await self.users.list(tag=old, limit=1000000)
        updated = 0
        for user in users:
            current = _json_list(user.tags)
            current = [new if t == old else t for t in current]
            # De-dup in case the user already had the new tag.
            seen: list[str] = []
            for t in current:
                if t not in seen:
                    seen.append(t)
            user.tags = json.dumps(seen)
            updated += 1
        await self.session.flush()
        return updated

    async def delete_tag(self, tag: str) -> int:
        return await self.remove_tags(
            [u.id for u in (await self.users.list(tag=tag, limit=1000000))[0]], [tag]
        )

    # ------------------------------------------------------------------
    # Score (transparent, explainable components)
    # ------------------------------------------------------------------
    @staticmethod
    def score_components(user: AudienceUser) -> list[dict[str, Any]]:
        """Return the explainable parts of a user's score."""
        return [
            {"key": "username", "ok": bool(user.username), "weight": 1.0,
             "label": "Есть @username"},
            {"key": "name", "ok": bool(user.first_name or user.last_name),
             "weight": 0.5, "label": "Указано имя"},
            {"key": "not_bot", "ok": not user.is_bot, "weight": 1.0,
             "label": "Не бот"},
            {"key": "premium", "ok": bool(user.is_premium), "weight": 0.5,
             "label": "Telegram Premium"},
        ]

    def _apply_score(self, user: AudienceUser) -> None:
        parts = self.score_components(user)
        user.score = round(
            sum(p["weight"] for p in parts if p["ok"]) / sum(p["weight"] for p in parts) * 100,
            1,
        )
        missing = [p["label"] for p in parts if not p["ok"]]
        user.score_reason = (
            "Все доступные признаки присутствуют."
            if not missing
            else "Не учтено: " + ", ".join(missing)
        )

    # ------------------------------------------------------------------
    # Statistics / dashboard
    # ------------------------------------------------------------------
    async def dashboard(self) -> dict[str, Any]:
        total_users = await self.users.count()
        unique_users = await self.users.count_unique()
        since = utcnow() - timedelta(days=7)
        sources_total = await self.sources.count()
        status_counts = await self.sources.count_by_status()
        completeness = await self.sources.count_completeness()
        overlap = await self.links.source_overlap(limit=10)
        return {
            "sources_total": sources_total,
            "unique_users": unique_users,
            "total_records": total_users,
            "new_users_7d": await self.users.count_new_since(since),
            "scans_total": sum(status_counts.values()),
            "partial_sources": await self.sources.partial_count(),
            "errors_total": status_counts.get(ScanStatus.FAILED.value, 0),
            "by_scan_status": status_counts,
            "by_completeness": completeness,
            "bots": await self.users.count_bots(),
            "source_overlap": [
                {"source_id": sid, "count": n} for sid, n in overlap
            ],
            "discovered_per_day": [
                {"date": d, "count": n} for d, n in await self.users.discovered_per_day(30)
            ],
        }

    async def source_statistics(self, source_id: str) -> dict[str, Any]:
        source = await self._require_source(source_id)
        linked = await self.links.count_for_source(source.id)
        users, _ = await self.users.list(source_id=source.id, limit=1)
        return {
            "source": source,
            "linked_users": linked,
            "discovered": source.discovered_count,
            "new": source.new_count,
            "duplicates": source.duplicate_count,
            "errors": source.error_count,
            "completeness": source.completeness.value,
            "explanation": self.explain_scan_result(source),
            "sample_size": len(users),
        }

    # ------------------------------------------------------------------
    # Export / import
    # ------------------------------------------------------------------
    def export_fields(self, *, include_pii: bool = False) -> list[str]:
        fields = list(EXPORT_FIELDS)
        if include_pii:
            fields.extend(PII_EXPORT_FIELDS)
        return fields

    async def _user_export_row(
        self, user: AudienceUser, *, include_pii: bool
    ) -> dict[str, Any]:
        sources = await self.sources_of_user(user.id)
        row: dict[str, Any] = {
            "telegram_user_id": user.telegram_user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "display_name": user.display_name,
            "is_bot": user.is_bot,
            "is_deleted": user.is_deleted,
            "is_premium": user.is_premium,
            "status": user.status.value,
            "score": user.score,
            "tags": _json_list(user.tags),
            "sources": sources,
            "first_seen_at": _iso(user.first_seen_at),
            "last_seen_at": _iso(user.last_seen_at),
        }
        if include_pii:
            row["phone_masked"] = user.phone_masked
        return row

    async def sources_of_user(self, user_id: str) -> list[str]:
        ids = await self.links.source_ids_for_user(user_id)
        titles: list[str] = []
        for sid in ids:
            src = await self.sources.get(sid)
            titles.append((src.title or src.username or sid) if src else sid)
        return titles

    async def export_audience(
        self,
        *,
        fmt: str = "csv",
        source_id: str | None = None,
        tag: str | None = None,
        include_pii: bool = False,
        limit: int = 0,
    ) -> ExportResult:
        """Stream users to a CSV/JSON file under the exports directory.

        The file is written locally only — it is never uploaded or sent anywhere.
        """
        if include_pii and not self.settings.audience_store_pii:
            raise AudienceServiceError(
                "Хранение персональных данных отключено в настройках.",
                how_to_fix=(
                    "Включите «Хранить персональные данные» в настройках, "
                    "если это действительно необходимо."
                ),
            )
        fmt = (fmt or "csv").lower()
        if fmt not in {"csv", "json"}:
            raise AudienceServiceError(
                "Формат экспорта должен быть CSV или JSON.",
                how_to_fix="Выберите CSV или JSON.",
            )
        out_dir = self.settings.resolve_exports_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"audience_{utcnow().strftime('%Y%m%d_%H%M%S')}_{new_id()[:6]}.{fmt}"
        path = out_dir / filename
        fields = self.export_fields(include_pii=include_pii)
        row_count = 0

        if fmt == "csv":
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                async for user in self._iter_export_users(source_id, tag, limit):
                    row = await self._user_export_row(user, include_pii=include_pii)
                    row["tags"] = ",".join(row["tags"])
                    row["sources"] = ",".join(row["sources"])
                    writer.writerow({k: row.get(k, "") for k in fields})
                    row_count += 1
        else:
            with path.open("w", encoding="utf-8") as fh:
                fh.write("[")
                first = True
                async for user in self._iter_export_users(source_id, tag, limit):
                    row = await self._user_export_row(user, include_pii=include_pii)
                    if not first:
                        fh.write(",")
                    fh.write(json.dumps(row, ensure_ascii=False))
                    first = False
                    row_count += 1
                fh.write("]")

        size = path.stat().st_size if path.exists() else 0
        await self.events.info(
            MODULE,
            f"Экспорт аудитории: {row_count} записей в {filename}.",
            operation="export",
            status="ok",
        )
        return ExportResult(
            path=str(path),
            filename=filename,
            format=fmt,
            fields=fields,
            includes_pii=include_pii,
            row_count=row_count,
            size_bytes=size,
            source_id=source_id or "",
        )

    async def _iter_export_users(
        self, source_id: str | None, tag: str | None, limit: int
    ) -> AsyncIterator[AudienceUser]:
        emitted = 0
        async for user in self.users.iter_all(source_id=source_id, tag=tag):
            if limit and emitted >= limit:
                break
            emitted += 1
            yield user

    async def import_audience(
        self, *, data: str, fmt: str = "csv", source_id: str | None = None
    ) -> dict[str, Any]:
        """Import users from CSV/JSON text; dedup by telegram_user_id.

        Invalid rows are skipped and counted, never silently merged wrongly.
        """
        fmt = (fmt or "csv").lower()
        invalid = 0
        if fmt == "json":
            try:
                parsed = json.loads(data)
            except ValueError:
                raise AudienceServiceError(
                    "Файл JSON повреждён.",
                    how_to_fix="Проверьте, что это корректный JSON-экспорт.",
                ) from None
            if isinstance(parsed, dict):
                parsed = parsed.get("users", [])
            if not isinstance(parsed, list):
                raise AudienceServiceError("Ожидался список пользователей.")
            candidates = parsed
        else:
            reader = csv.DictReader(io.StringIO(data))
            candidates = list(reader)

        now = utcnow()
        seen_ids: set[int] = set()
        created = 0
        merged = 0
        for raw in candidates:
            try:
                tid = int(str(raw.get("telegram_user_id") or raw.get("user_id") or "").strip())
            except (TypeError, ValueError):
                invalid += 1
                continue
            if tid in seen_ids:
                invalid += 1
                continue
            seen_ids.add(tid)
            existing = await self.users.get_by_telegram_id(tid)
            if existing is None:
                user = AudienceUser(
                    telegram_user_id=tid,
                    username=str(raw.get("username") or ""),
                    first_name=str(raw.get("first_name") or ""),
                    last_name=str(raw.get("last_name") or ""),
                    display_name=str(raw.get("display_name") or ""),
                    is_bot=_as_bool(raw.get("is_bot")),
                    is_deleted=_as_bool(raw.get("is_deleted")),
                    tags=json.dumps(_split_tags(raw.get("tags"))),
                    first_seen_at=now,
                    last_seen_at=now,
                    status=MemberStatus.UNKNOWN,
                )
                self._apply_score(user)
                await self.users.add(user)
                created += 1
            else:
                existing.last_seen_at = now
                if raw.get("username"):
                    existing.username = str(raw.get("username"))
                merged += 1
            if source_id:
                target = existing or user
                if await self.links.get(source_id, target.id) is None:
                    await self.links.add(
                        SourceUserLink(
                            source_id=source_id,
                            user_id=target.id,
                            first_seen_at=now,
                            last_seen_at=now,
                            discovery_method="import",
                        )
                    )
        await self.session.flush()
        return {"created": created, "merged": merged, "invalid": invalid}

    # ------------------------------------------------------------------
    # User listing helpers
    # ------------------------------------------------------------------
    async def list_users(self, **kwargs: Any) -> tuple[list[AudienceUser], int]:
        return await self.users.list(**kwargs)

    async def get_user(self, user_id: str) -> AudienceUser | None:
        return await self.users.get(user_id)

    async def bulk_status(self, user_ids: list[str], status: MemberStatus) -> int:
        return await self.users.bulk_update_status(user_ids, status)

    # ------------------------------------------------------------------
    # Filters metadata
    # ------------------------------------------------------------------
    @staticmethod
    def filter_presets() -> list[dict[str, Any]]:
        return [
            {"key": key, **value} for key, value in _FILTER_PRESETS.items()
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _display_name(u: Any) -> str:
        return u.display_name if hasattr(u, "display_name") else (
            f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
            or getattr(u, "username", "")
            or str(getattr(u, "id", ""))
        )

    @staticmethod
    def _derive_status(u: Any) -> MemberStatus:
        if getattr(u, "is_bot", False):
            return MemberStatus.UNKNOWN
        if getattr(u, "is_deleted", False):
            return MemberStatus.DELETED
        return MemberStatus.ACTIVE


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "да"}


def _split_tags(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [t.strip() for t in str(value).replace(";", ",").split(",") if t.strip()]


__all__ = [
    "SCAN_JOB_KIND",
    "AudienceProviderFactory",
    "AudienceService",
    "AudienceServiceError",
    "ExportResult",
    "ScanBatchOutcome",
    "SourcePreview",
]
