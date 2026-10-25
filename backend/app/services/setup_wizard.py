"""End-to-end Setup Wizard (D-128).

A single, resumable flow that takes the owner from a fresh install to a working
existing Telegram channel: app checks → channel → bots and rights → modules →
a minimal content process → queue health → a final readiness gate and an
explicitly-confirmed test publication.

Design rules (D-128):

* **Data-confirmed readiness.** A step is ``verified`` only after the server
  actually ran its check (:meth:`SetupWizardService.run_step`) and it passed. The
  result is stored, so opening a page or pressing a button never marks a step
  done; a re-run is required after a fix.
* **Honest, never optimistic.** Missing data or an un-runnable check reports
  ``unchecked`` (or ``failed``), never ``ready``. A channel is not "ready" unless
  a real verification was recorded and a bot binding is verified with rights.
* **D-127 is the single channel-state source.** The final readiness gate reads
  :class:`ChannelOverviewService`; the wizard does not invent a second status
  system.
* **Read-only until the owner confirms.** The wizard performs no Telegram
  operation on its own. It never creates a channel, never enables a personal
  MTProto account, and the only publish is the explicit test publication.

Only non-secret, display-safe data is stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.binding import BindingStatus
from backend.app.db.models.channel import Channel, ChannelStatus
from backend.app.db.models.content import (
    ContentItem,
    ContentItemStatus,
    Publication,
    PublicationStatus,
)
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.setup_wizard import SetupWizardRepository
from backend.app.services.channel_modules import KNOWN_MODULE_IDS, parse_modules
from backend.app.services.channel_overview import (
    ATTENTION_ERROR,
    ATTENTION_INFO,
    ATTENTION_OK,
    ATTENTION_WARNING,
    ChannelOverviewService,
)
from backend.app.services.events_service import EventsService

MODULE = "setup_wizard"

#: Step statuses (shown verbatim in the UI).
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"
STATUS_FAILED = "failed"
STATUS_UNCHECKED = "unchecked"

STATUS_TITLES = {
    STATUS_VERIFIED: "Проверено",
    STATUS_PENDING: "Нужно выполнить",
    STATUS_FAILED: "Есть проблема",
    STATUS_UNCHECKED: "Не проверено",
}

#: The ordered end-to-end steps.
STEP_KEYS = (
    "app",
    "channel",
    "bot",
    "modules",
    "content",
    "queue",
    "readiness",
)

#: Item states that mean "a material is genuinely ready to publish".
_READY_ITEM_STATUSES = {
    ContentItemStatus.READY,
    ContentItemStatus.APPROVED,
    ContentItemStatus.SCHEDULED,
    ContentItemStatus.PUBLISHING,
    ContentItemStatus.PUBLISHED,
}

#: Publication states that mean "a publication exists and is not a dead end".
_LIVE_PUBLICATION_STATUSES = {
    PublicationStatus.PLANNED,
    PublicationStatus.SCHEDULED,
    PublicationStatus.PUBLISHING,
    PublicationStatus.PUBLISHED,
}

_STEP_META: dict[str, dict[str, str]] = {
    "app": {
        "title": "Проверить программу",
        "description": "Среда, база данных, ключ безопасности и папки для данных.",
        "route": "/system",
    },
    "channel": {
        "title": "Подключить существующий канал",
        "description": "Добавьте канал и подтвердите доступ проверкой.",
        "route": "/channels",
    },
    "bot": {
        "title": "Подключить бота и права",
        "description": "Бот добавлен в канал, и Telegram подтвердил нужные права.",
        "route": "/bot-onboarding",
    },
    "modules": {
        "title": "Выбрать модули канала",
        "description": "Отметьте модули — сервер применяет ровно этот набор.",
        "route": "/channels",
    },
    "content": {
        "title": "Настроить минимальный контент-процесс",
        "description": "Источник, язык и готовый к публикации материал.",
        "route": "/content",
    },
    "queue": {
        "title": "Проверить очередь и задачи",
        "description": "Очередь без ошибок; ошибки видны и их можно повторить.",
        "route": "/queue",
    },
    "readiness": {
        "title": "Итоговая проверка готовности",
        "description": "Канал реально работает: есть публикация и нет проблем.",
        "route": "/channel-overview",
    },
}


class SetupWizardError(Exception):
    """A wizard operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class StepView:
    key: str
    title: str
    description: str
    status: str
    status_title: str
    verified: bool
    message: str
    how_to_fix: str
    route: str
    verified_at: str | None
    attempts: int


@dataclass(slots=True)
class WizardView:
    steps: list[StepView]
    completed_steps: int
    total_steps: int
    ready: bool
    progress_percent: int
    current_step: str
    test_publication_available: bool
    test_publication_hint: str
    notes: list[str] = field(default_factory=list)


class SetupWizardService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        content_service: object | None = None,
        posting_service: object | None = None,
        session_provider_factory: object | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.channels = ChannelRepository(session)
        self.steps = SetupWizardRepository(session)
        self.events = EventsService(session)
        self._content = content_service
        self._posting = posting_service
        self._session_provider_factory = session_provider_factory

    # --- state ---------------------------------------------------------------
    async def state(self) -> WizardView:
        """Build the current view from the *stored* verification results."""
        rows = {row.key: row for row in await self.steps.list_all()}
        steps: list[StepView] = []
        for key in STEP_KEYS:
            row = rows.get(key)
            meta = _STEP_META[key]
            steps.append(
                StepView(
                    key=key,
                    title=meta["title"],
                    description=meta["description"],
                    status=row.status if row is not None else STATUS_UNCHECKED,
                    status_title=STATUS_TITLES[
                        row.status if row is not None else STATUS_UNCHECKED
                    ],
                    verified=bool(row.verified) if row is not None else False,
                    message=row.message if row is not None else "",
                    how_to_fix=row.how_to_fix if row is not None else "",
                    route=meta["route"],
                    verified_at=row.verified_at.isoformat() if row and row.verified_at else None,
                    attempts=row.attempts if row is not None else 0,
                )
            )

        total = len(STEP_KEYS)
        done = sum(1 for s in steps if s.verified)
        current = next((s.key for s in steps if not s.verified), "readiness")
        ready = done == total
        content_step = next((s for s in steps if s.key == "content"), None)
        bot_step = next((s for s in steps if s.key == "bot"), None)
        test_ok = bool(
            content_step
            and content_step.verified
            and bot_step
            and bot_step.verified
        )
        return WizardView(
            steps=steps,
            completed_steps=done,
            total_steps=total,
            ready=ready,
            progress_percent=round(done / total * 100) if total else 0,
            current_step=current,
            test_publication_available=test_ok,
            test_publication_hint=(
                "Готово к тестовой публикации."
                if test_ok
                else "Сначала проверьте шаги «Бот и права» и «Контент-процесс»."
            ),
            notes=await self._notes(),
        )

    async def _notes(self) -> list[str]:
        notes: list[str] = []
        if not await self._has_account():
            notes.append(
                "Личный аккаунт Telegram не подключён — это необязательно. Без него "
                "доступны боты, реакции, кампании ссылок и публикации через бота."
            )
        return notes

    # --- run a step (the real check) -----------------------------------------
    async def run_step(self, key: str, *, account_id: str = "") -> WizardView:
        if key not in STEP_KEYS:
            raise SetupWizardError(
                "Неизвестный шаг настройки.",
                how_to_fix="Выберите шаг из списка мастера.",
                status_code=404,
            )
        position = STEP_KEYS.index(key)
        row = await self.steps.get_or_create(key, position=position)
        row.position = position
        row.attempts += 1

        verified, status, message, how_to_fix, channel_id = await self._check(key, account_id)
        row.verified = verified
        row.status = status
        row.message = message
        row.how_to_fix = how_to_fix
        row.channel_id = channel_id
        row.verified_at = utcnow()
        await self.session.flush()
        await self.session.commit()
        await self.events.info(
            MODULE,
            f"Шаг «{_STEP_META[key]['title']}»: {STATUS_TITLES[status]}.",
            operation="run_step",
            status="ok" if verified else "warn",
        )
        return await self.state()

    async def _check(
        self, key: str, account_id: str
    ) -> tuple[bool, str, str, str, str]:
        if key == "app":
            return await self._check_app()
        if key == "channel":
            return await self._check_channel(account_id)
        if key == "bot":
            return await self._check_bot()
        if key == "modules":
            return await self._check_modules()
        if key == "content":
            return await self._check_content()
        if key == "queue":
            return await self._check_queue()
        return await self._check_readiness()

    async def _check_app(self) -> tuple[bool, str, str, str, str]:
        from backend.app.services.system_service import STATUS_ERROR, SystemService

        checks = await SystemService(self.settings).setup_checks(self.session)
        problems = [c for c in checks if c.status == STATUS_ERROR]
        if problems:
            titles = ", ".join(c.title for c in problems)
            hint = " ".join(c.how_to_fix for c in problems if c.how_to_fix)
            return (
                False,
                STATUS_FAILED,
                f"Есть проблемы: {titles}.",
                hint or "Откройте «Система» и исправьте отмеченные пункты.",
                "",
            )
        return (
            True,
            STATUS_VERIFIED,
            f"Проверено пунктов: {len(checks)}. Проблем нет.",
            "",
            "",
        )

    async def _default_channel(self) -> Channel | None:
        channel = await self.channels.get_default()
        if channel is not None:
            return channel
        rows, _ = await self.channels.list(limit=1)
        return rows[0] if rows else None

    async def _check_channel(self, account_id: str) -> tuple[bool, str, str, str, str]:
        channel = await self._default_channel()
        if channel is None:
            return (
                False,
                STATUS_PENDING,
                "Канал ещё не добавлен.",
                "В Telegram создайте канал вручную (программа не создаёт каналы через "
                "Bot API), затем добавьте его в разделе «Каналы».",
                "",
            )
        # If the owner supplied an account, run a *real* verification now.
        if account_id and self._session_provider_factory is not None:
            from backend.app.services.channel_service import (
                ChannelService,
                ChannelServiceError,
            )

            service = ChannelService(
                self.session,
                settings=self.settings,
                session_provider_factory=self._session_provider_factory,  # type: ignore[arg-type]
            )
            try:
                result = await service.verify(channel.id, account_id)
            except ChannelServiceError as exc:
                return (False, STATUS_FAILED, exc.message, exc.how_to_fix, channel.id)
            if result.status in {"ok", "partial"}:
                return (
                    True,
                    STATUS_VERIFIED,
                    f"Доступ к каналу подтверждён: {result.status_label}.",
                    "",
                    channel.id,
                )
            return (
                False,
                STATUS_FAILED,
                f"Проверка канала: {result.status_label}.",
                result.how_to_fix or "Проверьте, что аккаунт добавлен в канал.",
                channel.id,
            )

        if channel.status is ChannelStatus.VERIFIED and channel.last_verified_at is not None:
            return (
                True,
                STATUS_VERIFIED,
                f"Канал «{self._label(channel)}» проверен.",
                "",
                channel.id,
            )
        if channel.status is ChannelStatus.ERROR:
            return (
                False,
                STATUS_FAILED,
                channel.verification_message or "Последняя проверка канала не удалась.",
                channel.verification_hint or "Откройте «Каналы» и нажмите «Проверить».",
                channel.id,
            )
        return (
            False,
            STATUS_PENDING,
            f"Канал «{self._label(channel)}» добавлен, но ещё не проверен.",
            "Откройте «Каналы» → выберите канал → «Проверить доступ».",
            channel.id,
        )

    async def _check_bot(self) -> tuple[bool, str, str, str, str]:
        from backend.app.db.models.binding import BotChannelBinding

        channel = await self._default_channel()
        channel_id = channel.id if channel else ""
        stmt = select(BotChannelBinding.status, func.count()).group_by(
            BotChannelBinding.status
        )
        if channel_id:
            stmt = stmt.where(BotChannelBinding.channel_id == channel_id)
        rows = (await self.session.execute(stmt)).all()
        counts = {str(status): int(count) for status, count in rows}
        ready = counts.get(str(BindingStatus.READY), 0)
        if ready:
            return (
                True,
                STATUS_VERIFIED,
                f"Готовых привязок бота: {ready}.",
                "",
                channel_id,
            )
        if counts.get(str(BindingStatus.NEEDS_PERMISSION), 0):
            return (
                False,
                STATUS_FAILED,
                "Бот добавлен в канал, но прав не хватает.",
                "Откройте «Подключение ботов» и выдайте боту нужные права, затем "
                "повторите проверку.",
                channel_id,
            )
        if counts:
            return (
                False,
                STATUS_PENDING,
                "Привязка бота есть, но права ещё не подтверждены.",
                "Откройте «Подключение ботов» и нажмите «Проверить».",
                channel_id,
            )
        return (
            False,
            STATUS_PENDING,
            "Бот ещё не привязан к каналу.",
            "Добавьте бота в канал и подтвердите права в разделе «Подключение ботов».",
            channel_id,
        )

    async def _check_modules(self) -> tuple[bool, str, str, str, str]:
        channel = await self._default_channel()
        if channel is None:
            return (
                False,
                STATUS_PENDING,
                "Сначала добавьте канал.",
                "Модули настраиваются для конкретного канала.",
                "",
            )
        configured = parse_modules(channel.modules)
        if not any(name in configured for name in KNOWN_MODULE_IDS):
            return (
                False,
                STATUS_PENDING,
                "Модули канала ещё не выбраны (пока включены все).",
                "Откройте «Каналы» → выберите канал → «Модули» и отметьте нужные.",
                channel.id,
            )
        enabled = [name for name in KNOWN_MODULE_IDS if configured.get(name)]
        return (
            True,
            STATUS_VERIFIED,
            "Выбраны модули: " + (", ".join(enabled) if enabled else "нет"),
            "",
            channel.id,
        )

    async def _check_content(self) -> tuple[bool, str, str, str, str]:
        from backend.app.db.models.content import ContentSource

        sources = (
            await self.session.execute(
                select(func.count()).select_from(ContentSource).where(
                    ContentSource.enabled.is_(True)
                )
            )
        ).scalar_one()
        if not sources:
            return (
                False,
                STATUS_PENDING,
                "Источник контента ещё не добавлен.",
                "Откройте «Content Studio» → «Источники» и добавьте источник.",
                "",
            )
        ready_items = (
            await self.session.execute(
                select(func.count()).select_from(ContentItem).where(
                    ContentItem.status.in_(list(_READY_ITEM_STATUSES))
                )
            )
        ).scalar_one()
        live_pubs = (
            await self.session.execute(
                select(func.count()).select_from(Publication).where(
                    Publication.status.in_(list(_LIVE_PUBLICATION_STATUSES))
                )
            )
        ).scalar_one()
        if ready_items or live_pubs:
            return (
                True,
                STATUS_VERIFIED,
                f"Источников: {sources}, готовых материалов: {ready_items}, "
                f"публикаций: {live_pubs}.",
                "",
                "",
            )
        return (
            False,
            STATUS_PENDING,
            f"Источник есть ({sources}), но готового материала пока нет.",
            "Откройте «Content Studio», соберите материал и подготовьте его к публикации.",
            "",
        )

    async def _check_queue(self) -> tuple[bool, str, str, str, str]:
        from backend.app.db.models.job import Job, JobStatus

        rows = (
            await self.session.execute(
                select(Job.status, func.count()).group_by(Job.status)
            )
        ).all()
        counts = {str(status): int(count) for status, count in rows}
        failed = counts.get(str(JobStatus.FAILED), 0)
        if failed:
            return (
                False,
                STATUS_FAILED,
                f"Заданий с ошибкой: {failed}.",
                "Откройте «Очередь», посмотрите ошибку и нажмите «Повторить».",
                "",
            )
        total = sum(counts.values())
        return (
            True,
            STATUS_VERIFIED,
            f"Очередь в порядке. Заданий: {total}.",
            "",
            "",
        )

    async def _check_readiness(self) -> tuple[bool, str, str, str, str]:
        overview = await ChannelOverviewService(self.session).build()
        channel = await self._default_channel()
        channel_id = channel.id if channel else ""
        channel_item = next(
            (c for c in overview.get("channels", []) if c.get("id") == channel_id), None
        )
        attention = str(
            (channel_item or {}).get("attention", {}).get("level", ATTENTION_INFO)
        )
        attention_reason = str(
            (channel_item or {}).get("attention", {}).get("reason", "")
        )
        published = (
            await self.session.execute(
                select(func.count()).select_from(Publication).where(
                    Publication.status == PublicationStatus.PUBLISHED
                )
            )
        ).scalar_one()

        if published == 0:
            return (
                False,
                STATUS_PENDING,
                "Успешных публикаций пока нет.",
                "Выполните тестовую публикацию с явным подтверждением.",
                channel_id,
            )
        if attention in {ATTENTION_ERROR, ATTENTION_WARNING}:
            return (
                False,
                STATUS_FAILED,
                f"Состояние канала: {attention_reason or 'требуется внимание'}",
                "Устраните проблему и повторите проверку готовности.",
                channel_id,
            )
        if attention not in {ATTENTION_OK, ATTENTION_INFO}:
            return (
                False,
                STATUS_UNCHECKED,
                "Состояние канала проверить не удалось.",
                "Откройте «Сводка по каналам» и обновите проверку.",
                channel_id,
            )
        return (
            True,
            STATUS_VERIFIED,
            f"Канал готов: публикаций {published}, состояние «{attention}».",
            "",
            channel_id,
        )

    # --- explicit test publication -------------------------------------------
    async def test_publication(self, *, confirmed: bool) -> dict[str, object]:
        """Publish one prepared material to the default channel — only on confirm.

        This is the single place the wizard touches Telegram, and it requires the
        owner's explicit ``confirmed=true``. It refuses unless the *stored* bot
        and content checks passed, so it can never run on unverified data.
        """
        if not confirmed:
            raise SetupWizardError(
                "Тестовая публикация требует явного подтверждения.",
                how_to_fix="Подтвердите действие — иначе публикация не выполняется.",
                status_code=400,
            )
        bot_row = await self.steps.get("bot")
        content_row = await self.steps.get("content")
        if not (bot_row and bot_row.verified):
            raise SetupWizardError(
                "Не подтверждены права бота.",
                how_to_fix="Сначала выполните шаг «Бот и права».",
                status_code=409,
            )
        if not (content_row and content_row.verified):
            raise SetupWizardError(
                "Не подтверждён контент-процесс.",
                how_to_fix="Сначала выполните шаг «Контент-процесс».",
                status_code=409,
            )
        channel = await self._default_channel()
        if channel is None:
            raise SetupWizardError(
                "Канал не выбран.",
                how_to_fix="Добавьте канал в разделе «Каналы».",
                status_code=409,
            )
        if self._content is None or self._posting is None:
            raise SetupWizardError(
                "Публикация недоступна.",
                how_to_fix="Повторите позже.",
                status_code=503,
            )

        from backend.app.db.models.content import ContentSource
        from backend.app.services.posting_service import TargetSpec

        source = (
            await self.session.execute(
                select(ContentSource)
                .where(ContentSource.enabled.is_(True))
                .order_by(ContentSource.created_at)
            )
        ).scalars().first()
        if source is None:
            raise SetupWizardError(
                "Нет источника для тестовой публикации.",
                how_to_fix="Добавьте источник в «Content Studio».",
                status_code=409,
            )

        grab = await self._content.grab(source.id, limit=5)  # type: ignore[attr-defined]
        item_id = await self._pick_publishable_item(grab.item_ids)
        if item_id is None:
            # A source that is already up to date yields no *new* material on a
            # re-grab, but an already-prepared material must still be publishable:
            # otherwise the wizard asks the owner to prepare content and then
            # refuses its own test publication on a duplicate.
            if not grab.ok and not grab.duplicates:
                raise SetupWizardError(
                    grab.message or "Источник не дал материала.",
                    how_to_fix=grab.how_to_fix or "Проверьте источник в «Content Studio».",
                    status_code=409,
                )
            raise SetupWizardError(
                "Нет подготовленного материала для тестовой публикации.",
                how_to_fix=(
                    "Соберите материал в «Content Studio» и переведите его в статус "
                    "«Готов» (или «Одобрено»)."
                ),
                status_code=409,
            )
        pubs = await self._posting.plan(  # type: ignore[attr-defined]
            item_id, [TargetSpec(channel_id=channel.id)]
        )

        if not pubs:
            raise SetupWizardError(
                "Не удалось подготовить публикацию.",
                how_to_fix="Проверьте материал в «Content Studio».",
                status_code=409,
            )
        outcome = await self._posting.publish(pubs[0].id)  # type: ignore[attr-defined]
        ok = bool(outcome.ok)
        await self.events.info(
            MODULE,
            "Тестовая публикация выполнена." if ok else "Тестовая публикация не удалась.",
            operation="test_publication",
            status="ok" if ok else "error",
        )
        return {
            "ok": ok,
            "message": outcome.message or ("Опубликовано." if ok else "Не опубликовано."),
            "how_to_fix": outcome.how_to_fix,
            "publication_id": pubs[0].id,
            "channel_id": channel.id,
            "channel_label": self._label(channel),
        }

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _label(channel: Channel) -> str:
        return channel.title or channel.username or channel.reference or channel.id

    async def _pick_publishable_item(self, item_ids: list[str]) -> str | None:
        """Return the first freshly grabbed material, else an existing prepared one.

        The first choice is the newest grabbed item; the fallback keeps the test
        publication usable when the source is already up to date (a re-grab then
        returns no new items) but a prepared material exists.
        """
        if item_ids:
            return item_ids[0]
        prepared = (
            await self.session.execute(
                select(ContentItem.id)
                .where(ContentItem.status.in_(list(_READY_ITEM_STATUSES)))
                .order_by(ContentItem.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return prepared

    async def _has_account(self) -> bool:
        from backend.app.db.models.session import SessionStatus
        from backend.app.db.repositories.sessions import SessionRepository

        sessions, _ = await SessionRepository(self.session).list()
        return any(
            s.enabled and s.status is SessionStatus.ONLINE for s in sessions
        )


__all__ = [
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_TITLES",
    "STATUS_UNCHECKED",
    "STATUS_VERIFIED",
    "STEP_KEYS",
    "SetupWizardError",
    "SetupWizardService",
    "StepView",
    "WizardView",
]
