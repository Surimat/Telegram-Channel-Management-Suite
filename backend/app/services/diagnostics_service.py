"""Diagnostics service: aggregate system state and produce a redacted report.

The goal is beginner-friendly self-service: the Diagnostics page shows one row
per subsystem with a plain-language status ("Готово", "Внимание", "Ошибка",
"Не настроено") plus what it means and what to do. The owner can then download a
**redacted** report (JSON/TXT/ZIP) to attach to a bug report without hunting for
logs.

Security is the primary constraint: the report never contains bot tokens,
``api_hash``/``api_id``, session data, phone numbers, passwords, database
contents, audience records or private logs. Every payload passes through
:mod:`backend.app.core.redaction` and a final safety scan before export.
"""

from __future__ import annotations

import io
import json
import platform
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import __version__
from backend.app.api.schemas.diagnostics import (
    DiagnosticItem,
    DiagnosticsReport,
    MaintenanceAction,
    MaintenanceResult,
)
from backend.app.core import paths
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.core.redaction import REDACTED, redact_and_verify, redact_text
from backend.app.db import migrate
from backend.app.db.models.backup_destination import DestinationStatus
from backend.app.db.models.binding import BindingStatus
from backend.app.db.models.bot import BotKind
from backend.app.db.models.capability import CAPABILITY_OK, CAPABILITY_UNAVAILABLE
from backend.app.db.models.channel import ChannelStatus
from backend.app.db.models.event import EventLevel
from backend.app.db.models.proxy import ProxyStatus
from backend.app.db.models.session import SessionStatus
from backend.app.db.models.update_state import UPDATE_AVAILABLE, UPDATE_ERROR, UPDATE_FAILED
from backend.app.db.repositories.bindings import BindingRepository
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.jobs import JobRepository
from backend.app.db.session import get_engine
from backend.app.services.system_service import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_UNKNOWN,
    STATUS_WARNING,
    SystemService,
)

STATUS_NOT_CONFIGURED = "not_configured"

STATUS_LABELS = {
    STATUS_OK: "Готово",
    STATUS_WARNING: "Внимание",
    STATUS_ERROR: "Ошибка",
    STATUS_NOT_CONFIGURED: "Не настроено",
    STATUS_UNKNOWN: "Неизвестно",
}

# Dependencies whose versions help diagnose environment problems.
_DEPENDENCIES = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "SQLAlchemy",
    "aiosqlite",
    "alembic",
    "aiogram",
    "telethon",
    "cryptography",
)

# Safe maintenance actions exposed to the owner.
ACTION_RESTART_SCHEDULER = "restart_scheduler"
ACTION_RECHECK_TELEGRAM = "recheck_telegram"
ACTION_RECHECK_CHANNELS = "recheck_channels"
ACTION_CLEANUP_JOBS = "cleanup_jobs"

# Titles for guarded checks, so a failed check still shows a friendly name.
_CHECK_TITLES = {
    "database": "База данных",
    "manager_bot": "Управляющий бот",
    "managed_bots": "Управляемые боты",
    "bot_factory": "Фабрика ботов",
    "bot_onboarding": "Подключение ботов к каналу",
    "sessions": "Аккаунты Telegram",
    "channels": "Каналы",
    "bindings": "Подключения ботов к каналам",
    "capabilities": "Реакции каналов",
    "audience": "Аудитория",
    "reactions": "Реакции",
    "invites": "Приглашения",
    "campaigns": "Кампании приглашений",
    "donors": "Качество источников",
    "ai": "Мини-ИИ",
    "owner_auth": "Владелец",
    "config_sync": "Синхронизация конфигурации",
    "scheduler": "Планировщик и очередь",
    "backup_destinations": "Места хранения копий",
    "update": "Обновления",
    "tray": "Значок в трее",
}

logger = get_logger(__name__)


@dataclass
class _ActionContext:
    """Runtime handles a maintenance action may need (never secrets)."""

    app_state: object | None = None


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, STATUS_LABELS[STATUS_UNKNOWN])


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _DEPENDENCIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:  # pragma: no cover - optional dep
            versions[name] = "not installed"
        except Exception:  # pragma: no cover - defensive
            versions[name] = "unknown"
    return versions


class DiagnosticsService:
    """Collect diagnostics and build safe maintenance actions/reports."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.system = SystemService(self.settings)
        self.jobs = JobRepository(session)
        self.bots = BotRepository(session)
        self.channels = ChannelRepository(session)

    # ------------------------------------------------------------------
    # Status aggregation
    # ------------------------------------------------------------------
    async def collect(self, app_state: object | None = None) -> DiagnosticsReport:
        # Each check is guarded so one failing subsystem (most importantly an
        # unreadable/corrupt database) cannot take down the whole page. This is
        # the page the user is told to open when something is wrong, so it must
        # always render — degrading individual rows instead of raising.
        items = [
            self._application_item(),
            await self._guarded("database", self.system.database_check),
            self._telegram_api_item(),
            await self._guarded(
                "manager_bot", lambda: self.system.manager_bot_db_check(self.session)
            ),
            await self._guarded("managed_bots", self._managed_bots_item),
            await self._guarded("bot_factory", self._bot_factory_item),
            await self._guarded("bot_onboarding", self._bot_onboarding_item),
            await self._guarded("owner_auth", self._owner_auth_item),
            await self._guarded("config_sync", self._config_sync_item),
            await self._guarded("sessions", self._sessions_item),
            await self._guarded("proxies", self._proxies_item),
            await self._guarded("channels", self._channels_item),
            await self._guarded("bindings", self._bindings_item),
            await self._guarded("capabilities", self._capabilities_item),
            await self._guarded("audience", self._audience_item),
            await self._guarded("donors", self._donors_item),
            await self._guarded("donor_candidates", self._donor_candidates_item),
            await self._guarded("reactions", lambda: self.system.reactions_check(self.session)),
            await self._guarded("invites", lambda: self.system.invites_check(self.session)),
            await self._guarded("campaigns", self._campaigns_item),
            await self._guarded("ai", self._ai_item),
            await self._guarded("scheduler", lambda: self._scheduler_item(app_state)),
            self._storage_item(),
            self._tray_item(),
            await self._guarded("backup_destinations", self._backup_destinations_item),
            await self._guarded("update", self._update_item),
            self._portable_item(),
        ]
        diagnostic_items = [
            DiagnosticItem(
                key=c.key,
                title=c.title,
                status=c.status,
                status_label=_status_label(c.status),
                meaning=c.meaning,
                how_to_fix=c.how_to_fix,
            )
            for c in items
        ]
        overall = self.system.overall_status(items)
        return DiagnosticsReport(
            version=__version__,
            environment=self.settings.app_env,
            overall=overall,
            overall_label=_status_label(overall),
            generated_at=datetime.now(UTC).isoformat(),
            items=diagnostic_items,
        )

    def _application_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        return Check(
            "application",
            "Приложение",
            STATUS_OK,
            f"Программа запущена. Версия {__version__}, режим «{self.settings.app_env}».",
            "",
        )

    async def _guarded(self, key: str, fn: object):  # type: ignore[no-untyped-def]
        """Run one check; on failure return a DB-unavailable row instead of raising.

        Used for every check that touches the database so the Diagnostics page
        still renders when the database is corrupt or unreachable.
        """
        try:
            return await fn()  # type: ignore[operator]
        except Exception as exc:
            from backend.app.services.system_service import Check

            logger.warning("Diagnostics check %r failed: %s", key, exc)
            return Check(
                key,
                _CHECK_TITLES.get(key, key),
                STATUS_ERROR,
                "Не удалось прочитать данные из базы.",
                (
                    "База данных повреждена или недоступна. Проверьте папку data/ "
                    "и раздел «Резервные копии»; подробности — в «Журнале»."
                ),
            )

    async def _safe(self, fn: object, fallback: object):  # type: ignore[no-untyped-def]
        """Await ``fn`` for the report; return ``fallback`` if the DB is unreadable."""
        try:
            return await fn()  # type: ignore[operator]
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Diagnostics report section failed: %s", exc)
            return fallback

    def _telegram_api_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        if self.settings.telegram_api_id and self.settings.telegram_api_hash.get_secret_value():
            return Check(
                "telegram_api",
                "Доступ к Telegram API",
                STATUS_OK,
                "API ID и API Hash указаны.",
                "",
            )
        return Check(
            "telegram_api",
            "Доступ к Telegram API",
            STATUS_NOT_CONFIGURED,
            "Не указаны API ID и API Hash (нужны для работы с аккаунтами).",
            "Получите их на https://my.telegram.org и добавьте в разделе «Аккаунты».",
        )

    async def _managed_bots_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        bots, count = await self.bots.list(kind=BotKind.MANAGED)
        if count == 0:
            return Check(
                "managed_bots",
                "Управляемые боты",
                STATUS_NOT_CONFIGURED,
                "Управляемые боты не добавлены — это необязательно.",
                "Создать нового бота можно в разделе «Боты» → «Управляемые боты».",
            )
        without_token = sum(1 for b in bots if not b.has_token)
        if without_token:
            return Check(
                "managed_bots",
                "Управляемые боты",
                STATUS_WARNING,
                f"Зарегистрировано ботов: {count}. Без токена: {without_token}.",
                "Нажмите «Получить токен» для ботов без токена.",
            )
        return Check(
            "managed_bots",
            "Управляемые боты",
            STATUS_OK,
            f"Управляемых ботов готово: {count}.",
            "",
        )

    async def _bot_factory_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.bot_factory import (
            BotBatchRepository,
            BotCandidateRepository,
        )
        from backend.app.services.system_service import Check

        batches, total = await BotBatchRepository(self.session).list_all(limit=100)
        if total == 0:
            return Check(
                "bot_factory",
                "Фабрика ботов",
                STATUS_NOT_CONFIGURED,
                "Пакеты ботов не создавались — это необязательно.",
                "Чтобы подготовить несколько ботов сразу, откройте «Фабрика ботов».",
            )
        # Count not-yet-finished operations across the most recent batches.
        queued = 0
        failed = 0
        for batch in batches:
            counts = await BotCandidateRepository(self.session).count_by_queue_state(
                batch.id
            )
            queued += counts.get("queued", 0) + counts.get("running", 0)
            failed += counts.get("failed", 0)
        if failed:
            return Check(
                "bot_factory",
                "Фабрика ботов",
                STATUS_WARNING,
                f"Пакетов: {total}. Незавершённых операций: {queued}. С ошибкой: {failed}.",
                "Откройте «Фабрика ботов» и повторите неудачные операции.",
            )
        return Check(
            "bot_factory",
            "Фабрика ботов",
            STATUS_OK,
            f"Пакетов: {total}. Незавершённых операций: {queued}.",
            "",
        )

    async def _bot_onboarding_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.bot_onboarding import (
            OnboardingBatchRepository,
            OnboardingCandidateRepository,
        )
        from backend.app.services.system_service import Check

        batches, total = await OnboardingBatchRepository(self.session).list_all(limit=100)
        if total == 0:
            return Check(
                "bot_onboarding",
                "Подключение ботов к каналу",
                STATUS_NOT_CONFIGURED,
                "Очереди массового подключения ботов не создавались — это необязательно.",
                "Откройте «Боты» и выберите «Подключить к каналу».",
            )
        active = 0
        failed = 0
        ready = 0
        for batch in batches:
            counts = await OnboardingCandidateRepository(self.session).count_by_status(
                batch.id
            )
            active += (
                counts.get("queued", 0)
                + counts.get("waiting_confirmation", 0)
                + counts.get("verifying", 0)
            )
            failed += counts.get("failed", 0)
            ready += counts.get("ready", 0)
        if failed:
            return Check(
                "bot_onboarding",
                "Подключение ботов к каналу",
                STATUS_WARNING,
                f"Очередей: {total}. Готово: {ready}. Активных: {active}. С ошибкой: {failed}.",
                "Откройте «Боты» → «Подключить к каналу» и повторите неудачные.",
            )
        return Check(
            "bot_onboarding",
            "Подключение ботов к каналу",
            STATUS_OK,
            f"Очередей: {total}. Готово: {ready}. Активных: {active}.",
            "",
        )

    async def _owner_auth_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.owner_auth_service import OwnerAuthService
        from backend.app.services.system_service import Check

        status = await OwnerAuthService(self.session).status()
        if not status.exists:
            return Check(
                "owner_auth",
                "Владелец",
                STATUS_NOT_CONFIGURED,
                "Профиль владельца не создан — приложение открыто без входа.",
                "Создайте профиль владельца в разделе «Владелец», чтобы защитить настройки.",
            )
        if not status.enabled:
            return Check(
                "owner_auth",
                "Владелец",
                STATUS_WARNING,
                "Профиль владельца есть, но защита выключена.",
                "Включите защиту в разделе «Владелец», если компьютером пользуются другие.",
            )
        if status.locked:
            return Check(
                "owner_auth",
                "Владелец",
                STATUS_WARNING,
                "Вход временно заблокирован после нескольких неудачных попыток.",
                "Подождите или перезапустите приложение.",
            )
        return Check(
            "owner_auth",
            "Владелец",
            STATUS_OK,
            "Профиль владельца создан, защита включена.",
            "",
        )

    async def _config_sync_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.config_sync_service import ConfigSyncService
        from backend.app.services.system_service import Check

        status = await ConfigSyncService(self.session).status()
        if status.state == "available":
            return Check(
                "config_sync",
                "Синхронизация конфигурации",
                STATUS_OK,
                f"Провайдер: {status.provider_label}. Ревизия: {status.cloud_revision}.",
                "",
            )
        if status.state == "error":
            return Check(
                "config_sync",
                "Синхронизация конфигурации",
                STATUS_ERROR,
                status.message or "Провайдер синхронизации требует повторного входа.",
                "Переподключите Google Drive в разделе «Владелец» → «Синхронизация».",
            )
        return Check(
            "config_sync",
            "Синхронизация конфигурации",
            STATUS_NOT_CONFIGURED,
            "Синхронизация не настроена — это необязательно.",
            "Подключите Google Drive или локальную папку в разделе «Владелец».",
        )

    async def _sessions_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.session_service import SessionService
        from backend.app.services.system_service import Check

        service = SessionService(self.session, settings=self.settings)
        accounts = await service.list_accounts()
        if not accounts:
            return Check(
                "sessions",
                "Аккаунты Telegram",
                STATUS_NOT_CONFIGURED,
                "Пользовательские аккаунты ещё не добавлены.",
                "Добавьте аккаунт в разделе «Аккаунты» (нужно для парсинга и приглашений).",
            )
        online = sum(1 for a in accounts if a.status == SessionStatus.ONLINE)
        need_auth = sum(1 for a in accounts if a.status == SessionStatus.AUTH_REQUIRED)
        if need_auth:
            return Check(
                "sessions",
                "Аккаунты Telegram",
                STATUS_WARNING,
                f"Аккаунтов: {len(accounts)}, требуется авторизация: {need_auth}.",
                "Запустите мастер повторной авторизации в разделе «Аккаунты».",
            )
        if online == 0:
            return Check(
                "sessions",
                "Аккаунты Telegram",
                STATUS_WARNING,
                f"Аккаунтов: {len(accounts)}, но ни один не авторизован.",
                "Проверьте аккаунты в разделе «Аккаунты» (кнопка «Проверить»).",
            )
        return Check(
            "sessions",
            "Аккаунты Telegram",
            STATUS_OK,
            f"Готовых аккаунтов: {online} из {len(accounts)}.",
            "",
        )

    async def _channels_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        channels, total = await self.channels.list()
        if total == 0:
            return Check(
                "channels",
                "Каналы",
                STATUS_NOT_CONFIGURED,
                "Каналы ещё не добавлены в реестр.",
                "Добавьте канал в разделе «Каналы», чтобы связать реакции, "
                "аудиторию и приглашения.",
            )
        verified = sum(1 for c in channels if c.status == ChannelStatus.VERIFIED)
        failed = sum(
            1 for c in channels if c.status in {ChannelStatus.ERROR, ChannelStatus.WARNING}
        )
        default = await self.channels.get_default()
        if failed:
            return Check(
                "channels",
                "Каналы",
                STATUS_WARNING,
                f"Каналов: {total}, проверено: {verified}, с замечаниями: {failed}.",
                "Откройте «Каналы» и нажмите «Проверить» для проблемных каналов.",
            )
        default_label = (default.title or default.username or default.reference) if default else ""
        suffix = f" Основной: {default_label}." if default_label else ""
        return Check(
            "channels",
            "Каналы",
            STATUS_OK,
            f"Каналов: {total}, проверено: {verified}.{suffix}",
            "",
        )

    async def _bindings_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        bindings = await BindingRepository(self.session).list_all()
        if not bindings:
            return Check(
                "bindings",
                "Подключения ботов к каналам",
                STATUS_NOT_CONFIGURED,
                "Боты пока не подключены к каналам. Это нужно для реакций без аккаунта.",
                "Откройте «Каналы» → выберите канал → «Подключить бота».",
            )
        ready = sum(1 for b in bindings if b.status == BindingStatus.READY)
        problem = sum(
            1
            for b in bindings
            if b.status in {BindingStatus.NEEDS_PERMISSION, BindingStatus.ERROR}
        )
        if problem:
            return Check(
                "bindings",
                "Подключения ботов к каналам",
                STATUS_WARNING,
                f"Подключений: {len(bindings)}, готово: {ready}, требуют внимания: {problem}.",
                "Проверьте проблемные подключения и выдайте боту права администратора.",
            )
        return Check(
            "bindings",
            "Подключения ботов к каналам",
            STATUS_OK,
            f"Готовых подключений: {ready} из {len(bindings)}.",
            "",
        )

    async def _capabilities_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.capabilities import CapabilityRepository
        from backend.app.services.system_service import Check

        rows = await CapabilityRepository(self.session).list_all()
        if not rows:
            return Check(
                "capabilities",
                "Реакции каналов",
                STATUS_NOT_CONFIGURED,
                "Наборы реакций каналов ещё не проверялись.",
                "Это необязательно: реакции работают, пока не заданы ограничения.",
            )
        known = sum(1 for r in rows if r.status == CAPABILITY_OK)
        unavailable = sum(1 for r in rows if r.status == CAPABILITY_UNAVAILABLE)
        if unavailable and not known:
            return Check(
                "capabilities",
                "Реакции каналов",
                STATUS_WARNING,
                f"Проверено каналов: {len(rows)}, недоступны: {unavailable}.",
                "Подключите бота к каналу, чтобы узнать доступные реакции.",
            )
        return Check(
            "capabilities",
            "Реакции каналов",
            STATUS_OK,
            f"Проверено каналов: {len(rows)}, известен набор реакций: {known}.",
            "",
        )

    async def _proxies_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.proxies import ProxyRepository
        from backend.app.services.system_service import Check

        profiles = await ProxyRepository(self.session).list_all()
        if not profiles:
            return Check(
                "proxies",
                "Сетевые маршруты (прокси)",
                STATUS_NOT_CONFIGURED,
                "Прокси не настроены — все аккаунты подключаются напрямую. Это нормально.",
                "Прокси нужен, только если Telegram недоступен напрямую. Он не обходит лимиты.",
            )
        enabled = sum(1 for p in profiles if p.enabled)
        broken_statuses = {ProxyStatus.ERROR, ProxyStatus.TIMEOUT}
        broken = sum(
            1 for p in profiles if p.enabled and p.status in broken_statuses
        )
        if broken:
            return Check(
                "proxies",
                "Сетевые маршруты (прокси)",
                STATUS_WARNING,
                f"Прокси: {len(profiles)}, включено: {enabled}, с проблемами: {broken}.",
                "Проверьте проблемные прокси кнопкой «Проверить» на странице «Аккаунты».",
            )
        return Check(
            "proxies",
            "Сетевые маршруты (прокси)",
            STATUS_OK,
            f"Прокси: {len(profiles)}, включено: {enabled}.",
            "",
        )

    async def _donor_candidates_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.proxies import DonorCandidateRepository
        from backend.app.services.system_service import Check

        rows = await DonorCandidateRepository(self.session).list_all()
        if not rows:
            return Check(
                "donor_candidates",
                "Автопоиск доноров",
                STATUS_NOT_CONFIGURED,
                "Кандидаты-доноры ещё не искались — это необязательно.",
                "Поиск доноров доступен на странице «Источники» (кандидаты добавляются вручную).",
            )
        added = sum(1 for c in rows if c.added)
        return Check(
            "donor_candidates",
            "Автопоиск доноров",
            STATUS_OK,
            f"Кандидатов: {len(rows)}, добавлено в источники: {added}.",
            "",
        )

    async def _donors_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.donors import DonorRepository
        from backend.app.services.system_service import Check

        rows = await DonorRepository(self.session).list_all()
        if not rows:
            return Check(
                "donors",
                "Качество источников",
                STATUS_NOT_CONFIGURED,
                "Источники ещё не оценивались.",
                "Откройте «Аудитория» → «Качество источников» и запустите оценку.",
            )
        suspect = sum(1 for r in rows if r.quality == "suspect")
        if suspect:
            return Check(
                "donors",
                "Качество источников",
                STATUS_WARNING,
                f"Оценено источников: {len(rows)}. С признаками накрутки: {suspect}.",
                "Проверьте источники со статусом «Подозрительный» перед закупкой рекламы.",
            )
        return Check(
            "donors",
            "Качество источников",
            STATUS_OK,
            f"Оценено источников: {len(rows)}. Явных проблем не найдено.",
            "",
        )

    async def _campaigns_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.campaigns import CampaignRepository
        from backend.app.services.system_service import Check

        _rows, total = await CampaignRepository(self.session).list(limit=1)
        if total == 0:
            return Check(
                "campaigns",
                "Кампании приглашений",
                STATUS_NOT_CONFIGURED,
                "Кампаний приглашений нет — это необязательно.",
                "Продвижение ссылками доступно без входа в аккаунт: «Приглашения» → «Кампании».",
            )
        return Check(
            "campaigns",
            "Кампании приглашений",
            STATUS_OK,
            f"Кампаний: {total}.",
            "",
        )

    async def _backup_destinations_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.destinations import DestinationRepository
        from backend.app.services.system_service import Check

        rows = await DestinationRepository(self.session).list_all()
        if not rows:
            return Check(
                "backup_destinations",
                "Места хранения копий",
                STATUS_NOT_CONFIGURED,
                "Места хранения ещё не настроены.",
                "Откройте «Резервные копии»: локальное место создаётся автоматически.",
            )
        enabled = [r for r in rows if r.enabled]
        broken = [
            r
            for r in enabled
            if r.status in {DestinationStatus.ERROR, DestinationStatus.WARNING}
        ]
        if broken:
            return Check(
                "backup_destinations",
                "Места хранения копий",
                STATUS_WARNING,
                f"Мест хранения: {len(rows)}, включено: {len(enabled)}, "
                f"с проблемами: {len(broken)}.",
                "Проверьте проблемные места хранения кнопкой «Проверить».",
            )
        return Check(
            "backup_destinations",
            "Места хранения копий",
            STATUS_OK,
            f"Мест хранения: {len(rows)}, включено: {len(enabled)}.",
            "",
        )

    async def _update_item(self):  # type: ignore[no-untyped-def]
        from backend.app.db.repositories.destinations import UpdateStateRepository
        from backend.app.services.system_service import Check

        row = await UpdateStateRepository(self.session).get()
        if row is None or not row.auto_update_enabled:
            return Check(
                "update",
                "Обновления",
                STATUS_NOT_CONFIGURED,
                "Автоматическая проверка обновлений выключена — это нормально.",
                "Включить можно в разделе «Система» → «Обновления».",
            )
        if row.state == UPDATE_AVAILABLE:
            return Check(
                "update",
                "Обновления",
                STATUS_WARNING,
                f"Доступна новая версия {row.latest_version}.",
                "Откройте «Система» → «Обновления», чтобы скачать и установить её.",
            )
        if row.state in {UPDATE_ERROR, UPDATE_FAILED}:
            return Check(
                "update",
                "Обновления",
                STATUS_ERROR,
                "Не удалось проверить или установить обновление.",
                "Проверьте подключение к интернету и повторите проверку.",
            )
        return Check(
            "update",
            "Обновления",
            STATUS_OK,
            row.message or "Обновления проверяются автоматически.",
            "",
        )

    async def _audience_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.audience_service import AudienceService
        from backend.app.services.system_service import Check

        service = AudienceService(self.session, settings=self.settings)
        sources_total = await service.sources.count()
        users_total = await service.users.count()
        if sources_total == 0:
            return Check(
                "audience",
                "Аудитория",
                STATUS_NOT_CONFIGURED,
                "Источники аудитории ещё не добавлены.",
                "Откройте раздел «Аудитория» и добавьте канал или группу для анализа.",
            )
        partial = await service.sources.partial_count()
        if partial:
            return Check(
                "audience",
                "Аудитория",
                STATUS_WARNING,
                f"Источников: {sources_total}, пользователей: {users_total}. "
                f"Частичных результатов: {partial}.",
                "Откройте источники со статусом «Частично»: Telegram не отдал полный список.",
            )
        return Check(
            "audience",
            "Аудитория",
            STATUS_OK,
            f"Источников: {sources_total}, уникальных пользователей: {users_total}.",
            "",
        )

    async def _ai_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        check = await self.system.ai_check_async(self.session)
        if check.status == STATUS_OK and "выключ" in check.meaning.lower():
            return Check(
                check.key,
                check.title,
                STATUS_NOT_CONFIGURED,
                "Мини-ИИ не используется — это нормально, система работает на правилах.",
                check.how_to_fix,
            )
        return check

    async def _scheduler_item(self, app_state: object | None):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        if not self.settings.scheduler_enabled:
            return Check(
                "scheduler",
                "Планировщик",
                STATUS_NOT_CONFIGURED,
                "Планировщик выключен в настройках.",
                "Включите SCHEDULER_ENABLED=true, если нужны запланированные действия.",
            )
        runtime = getattr(app_state, "scheduler", None) if app_state is not None else None
        running = runtime is not None and getattr(runtime, "_task", None) is not None
        counts = await self.jobs.status_counts()
        pending = counts.get("pending", 0) + counts.get("scheduled", 0)
        if not running:
            return Check(
                "scheduler",
                "Планировщик",
                STATUS_WARNING,
                "Планировщик включён, но не запущен в этой сессии.",
                "Нажмите «Перезапустить планировщик» в разделе «Диагностика».",
            )
        return Check(
            "scheduler",
            "Планировщик",
            STATUS_OK,
            f"Планировщик работает. Заданий в ожидании: {pending}.",
            "",
        )

    def _tray_item(self):  # type: ignore[no-untyped-def]
        """Report the TCMS Tray Agent state (from its secret-free snapshot)."""
        from backend.app.services.system_service import Check
        from backend.app.tray.state import pid_alive, read_snapshot

        snapshot = read_snapshot()
        if snapshot.state == "stopped" and not snapshot.updated_at:
            return Check(
                "tray",
                "Значок в трее",
                STATUS_NOT_CONFIGURED,
                "Приложение запущено напрямую (без значка в трее).",
                "Запустите run.bat в портативной сборке, чтобы получить значок в трее.",
            )
        alive = snapshot.running or pid_alive(snapshot.pid)
        if snapshot.state == "restart_limit":
            return Check(
                "tray",
                "Значок в трее",
                STATUS_ERROR,
                "Автоматические перезапуски приостановлены из-за частых сбоев.",
                "Проверьте «Журнал», затем запустите приложение вручную.",
            )
        if snapshot.state in ("crashed", "stopped") and not alive:
            return Check(
                "tray",
                "Значок в трее",
                STATUS_WARNING,
                snapshot.last_error or "Основной процесс не запущен.",
                "Откройте значок в трее и нажмите «Запустить».",
            )
        return Check(
            "tray",
            "Значок в трее",
            STATUS_OK,
            f"Значок в трее активен. Состояние: {snapshot.state_title}.",
            "",
        )

    def _storage_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        check = self.system.filesystem_check()
        return Check(
            "storage",
            "Хранилище",
            check.status,
            check.meaning,
            check.how_to_fix,
        )

    def _portable_item(self):  # type: ignore[no-untyped-def]
        from backend.app.services.system_service import Check

        runtime = _portable_runtime_label()
        if runtime is None:
            return Check(
                "portable_runtime",
                "Портативный режим",
                STATUS_NOT_CONFIGURED,
                "Обычный запуск (не портативная сборка). Данные хранятся в папке проекта.",
                "",
            )
        return Check(
            "portable_runtime",
            "Портативный режим",
            STATUS_OK,
            f"Портативная сборка: {runtime}. Данные хранятся рядом с программой.",
            "",
        )

    # ------------------------------------------------------------------
    # Report payload + export
    # ------------------------------------------------------------------
    async def build_report_payload(self, app_state: object | None = None) -> dict[str, object]:
        report = await self.collect(app_state)
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "report": {
                "app": "Telegram Channel Management Suite",
                "kind": "diagnostics",
                "version": __version__,
                "generated_at": now.isoformat(),
                "redaction": (
                    "Отчёт безопасно очищен от секретов: токены, ключи доступа, "
                    "данные сессий, номера телефонов, пароли и содержимое базы "
                    "не включаются."
                ),
            },
            "application": {
                "version": __version__,
                "environment": self.settings.app_env,
                "language": self.settings.app_language,
                "debug": self.settings.app_debug,
                "offline_mode": self.settings.offline_mode,
            },
            "os": {
                "platform": platform.platform(),
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "portable_runtime": _portable_runtime_label(),
            },
            "database": await self._safe(self._database_payload, {}),
            "modules": {
                "scheduler_enabled": self.settings.scheduler_enabled,
                "manager_runtime_enabled": self.settings.manager_runtime_enabled,
                "ai_enabled": self.settings.ai_enabled,
                "miniapp_enabled": self.settings.miniapp_enabled,
                "telegram_provider": self._provider_label(),
                "backup_include_sessions": self.settings.backup_include_sessions,
            },
            "telegram": {
                "api_configured": bool(
                    self.settings.telegram_api_id
                    and self.settings.telegram_api_hash.get_secret_value()
                ),
                "provider": self._provider_label(),
                "bots": await self._safe(self._bots_payload, []),
                "sessions": await self._safe(self._sessions_payload, []),
                "channels": await self._safe(self._channels_payload, []),
            },
            "queue": await self._safe(self._queue_payload, {"unavailable": True}),
            "owner": await self._safe(self._owner_payload, {"unavailable": True}),
            "config_sync": await self._safe(self._config_sync_payload, {"unavailable": True}),
            "bindings": await self._safe(self._bindings_payload, []),
            "capabilities": await self._safe(self._capabilities_payload, []),
            "proxies": await self._safe(self._proxies_payload, []),
            "donor_candidates": await self._safe(self._donor_candidates_payload, []),
            "campaigns": await self._safe(self._campaigns_payload, []),
            "donors": await self._safe(self._donors_payload, []),
            "backup_destinations": await self._safe(self._destinations_payload, []),
            "update": await self._safe(self._update_payload, {}),
            "ai": await self._ai_payload(),
            "dependencies": _dependency_versions(),
            "last_errors": await self._safe(self._last_errors_payload, []),
            "paths": self._paths_payload(),
            "checks": [item.model_dump() for item in report.items],
            "overall": report.overall,
        }
        return payload

    async def build_report(
        self, fmt: str = "json", app_state: object | None = None
    ) -> tuple[bytes, str, str]:
        """Return ``(content, filename, media_type)`` for a redacted report."""
        fmt = (fmt or "json").strip().lower()
        payload = await self.build_report_payload(app_state)
        result = redact_and_verify(payload)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        base = f"tcms-diagnostics-{__version__}-{stamp}"
        if not result.clean:  # pragma: no cover - safety net, should not happen
            # Never export a payload the scan is unsure about.
            raise DiagnosticsError(
                "Отчёт не прошёл проверку безопасности и не был создан. "
                "Повторите попытку после перезапуска приложения."
            )
        if fmt == "json":
            content = json.dumps(result.payload, ensure_ascii=False, indent=2, default=str)
            return content.encode("utf-8"), f"{base}.json", "application/json"
        if fmt == "txt":
            return _render_text(result.payload).encode("utf-8"), f"{base}.txt", "text/plain"
        if fmt == "zip":
            return _render_zip(result.payload), f"{base}.zip", "application/zip"
        raise DiagnosticsError("Неизвестный формат отчёта. Доступно: json, txt, zip.")

    def _provider_label(self) -> str:
        if self.settings.offline_mode:
            return "offline (тестовый режим, без сети)"
        if self.settings.telegram_provider in {"fake", "aiogram"}:
            return self.settings.telegram_provider
        return "auto (обычный режим)"

    async def _database_payload(self) -> dict[str, object]:
        status = await migrate.database_status()
        tables: list[str] = []
        db_size = None
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                tables = sorted(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        except Exception:  # pragma: no cover - defensive
            tables = []
        db_path = self._database_path()
        if db_path is not None and db_path.is_file():
            db_size = db_path.stat().st_size
        return {
            "state": status.state,
            "message": status.message,
            "current_revision": status.current_revision,
            "head_revision": status.head_revision,
            "pending_count": len(status.pending),
            "error": status.error,
            "tables": tables,
            "size_bytes": db_size,
        }

    def _database_path(self) -> Path | None:
        url = self.settings.resolve_database_url()
        prefix = "sqlite+aiosqlite:///"
        if not url.startswith(prefix):
            return None
        raw = url[len(prefix) :]
        if raw.startswith(":") or not raw:
            return None
        return Path(raw)

    async def _bots_payload(self) -> list[dict[str, object]]:
        bots, _ = await self.bots.list(limit=500)
        return [
            {
                "kind": str(bot.kind),
                "username": bot.username,
                "title": bot.title,
                "enabled": bot.enabled,
                "health": str(bot.health),
                "has_token": bot.has_token,
                "last_error": redact_text(bot.last_error or ""),
            }
            for bot in bots
        ]

    async def _sessions_payload(self) -> list[dict[str, object]]:
        from backend.app.services.session_service import SessionService

        accounts = await SessionService(self.session, settings=self.settings).list_accounts()
        return [
            {
                "username": account.username,
                "display_name": account.display_name,
                "status": str(account.status),
                "enabled": account.enabled,
                "has_session": account.has_session,
                "has_api_credentials": account.has_api_hash,
            }
            for account in accounts
        ]

    async def _channels_payload(self) -> list[dict[str, object]]:
        channels, _ = await self.channels.list(limit=500)
        return [
            {
                "username": channel.username,
                "title": channel.title,
                "kind": str(channel.kind),
                "status": str(channel.status),
                "is_default": channel.is_default,
                "verification_status": channel.verification_status,
                "verification_message": redact_text(channel.verification_message or ""),
            }
            for channel in channels
        ]

    async def _owner_payload(self) -> dict[str, object]:
        """Non-secret owner status for the report (never a password/verifier)."""
        from backend.app.services.owner_auth_service import OwnerAuthService

        status = await OwnerAuthService(self.session).status()
        return {
            "exists": status.exists,
            "enabled": status.enabled,
            "locked": status.locked,
            "method": status.method,
            "last_login_at": status.last_login_at,
        }

    async def _config_sync_payload(self) -> dict[str, object]:
        """Non-secret config-sync status (never a token or plaintext config)."""
        from backend.app.services.config_sync_service import ConfigSyncService

        status = await ConfigSyncService(self.session).status()
        return {
            "state": status.state,
            "provider": status.provider,
            "connected": status.connected,
            "enabled": status.enabled,
            "local_revision": status.local_revision,
            "cloud_revision": status.cloud_revision,
            "device_id": status.device_id,
            "cloud_device": status.cloud_device,
            "last_sync_at": status.last_sync_at,
            "last_status": status.last_status,
            "needs_reconnect": status.needs_reconnect,
        }

    async def _bindings_payload(self) -> list[dict[str, object]]:
        bindings = await BindingRepository(self.session).list_all()
        return [
            {
                "function": b.function,
                "channel_label": redact_text(b.channel_label or ""),
                "status": str(b.status),
                "role": str(b.role),
                "can_set_reactions": b.can_set_reactions,
                "can_invite_users": b.can_invite_users,
                "can_post_messages": b.can_post_messages,
                "last_checked": _iso(b.last_checked),
                "last_error": redact_text(b.last_error or ""),
            }
            for b in bindings
        ]

    async def _capabilities_payload(self) -> list[dict[str, object]]:
        from backend.app.db.repositories.capabilities import CapabilityRepository

        rows = await CapabilityRepository(self.session).list_all()
        return [
            {
                "channel_id": r.channel_id,
                "status": r.status,
                "reactions_limit": r.reactions_limit,
                "paid_reactions_available": r.paid_reactions_available,
                "available_reactions_count": len(_load_list(r.available_reactions)),
                "bot_reactions_count": len(_load_list(r.bot_reactions)),
                "last_checked": _iso(r.last_checked),
            }
            for r in rows
        ]

    async def _proxies_payload(self) -> list[dict[str, object]]:
        from backend.app.db.repositories.proxies import ProxyRepository

        rows = await ProxyRepository(self.session).list_all()
        # Never a password: only presence, kind, host and last status.
        return [
            {
                "name": redact_text(p.name or ""),
                "kind": p.kind,
                "host": p.host,
                "port": p.port,
                "username_present": bool(p.username),
                "has_password": bool(p.password_encrypted),
                "enabled": p.enabled,
                "status": str(p.status),
                "last_checked": _iso(p.last_checked),
            }
            for p in rows
        ]

    async def _donor_candidates_payload(self) -> list[dict[str, object]]:
        from backend.app.db.repositories.proxies import DonorCandidateRepository

        rows = await DonorCandidateRepository(self.session).list_all()
        return [
            {
                "query": redact_text(c.query or ""),
                "provider": c.provider,
                "username": c.username,
                "title": redact_text(c.title or ""),
                "kind": c.kind,
                "subscribers": c.subscribers,
                "fit": c.fit,
                "fit_score": c.fit_score,
                "confidence": c.confidence,
                "added": c.added,
                "created_at": _iso(c.created_at),
            }
            for c in rows
        ]

    async def _campaigns_payload(self) -> list[dict[str, object]]:
        from backend.app.db.repositories.campaigns import CampaignRepository

        rows, _ = await CampaignRepository(self.session).list(limit=500)
        return [
            {
                "name": redact_text(c.name or ""),
                "status": str(c.status),
                "risk_mode": c.risk_mode,
                "links_count": c.links_count,
                "joins_count": c.joins_count,
                "requests_count": c.requests_count,
            }
            for c in rows
        ]

    async def _donors_payload(self) -> list[dict[str, object]]:
        from backend.app.db.repositories.donors import DonorRepository

        rows = await DonorRepository(self.session).list_all()
        return [
            {
                "title": redact_text(r.title or ""),
                "quality": r.quality,
                "quality_score": r.quality_score,
                "bot_probability": r.bot_probability,
                "confidence": r.confidence,
                "participant_data": r.participant_data,
                "subscribers": r.subscribers,
                "last_analyzed": _iso(r.last_analyzed),
            }
            for r in rows
        ]

    async def _destinations_payload(self) -> list[dict[str, object]]:
        from backend.app.db.repositories.destinations import DestinationRepository

        rows = await DestinationRepository(self.session).list_all()
        return [
            {
                "kind": str(r.kind),
                "label": redact_text(r.label or ""),
                "enabled": r.enabled,
                "status": str(r.status),
                "has_credentials": bool(r.credentials_encrypted),
                "last_backup_at": _iso(r.last_backup_at),
                "last_error": redact_text(r.last_error or ""),
            }
            for r in rows
        ]

    async def _update_payload(self) -> dict[str, object]:
        from backend.app.db.repositories.destinations import UpdateStateRepository

        row = await UpdateStateRepository(self.session).get()
        if row is None:
            return {"enabled": False, "state": "idle"}
        return {
            "enabled": row.auto_update_enabled,
            "state": row.state,
            "current_version": row.current_version,
            "latest_version": row.latest_version,
            "staged": bool(row.staged_file),
            "last_checked_at": _iso(row.last_checked_at),
            "last_error": redact_text(row.last_error or ""),
        }

    async def _queue_payload(self) -> dict[str, object]:
        counts = await self.jobs.status_counts()
        kinds = await self.jobs.kind_counts()
        stuck = await self.jobs.list_stuck_running()
        overdue = await self.jobs.list_overdue(grace_seconds=300)
        return {
            "by_status": counts,
            "by_kind": kinds,
            "stuck_running": len(stuck),
            "overdue": len(overdue),
            "oldest_pending_at": _iso(await self.jobs.oldest_pending_at()),
        }

    async def _ai_payload(self) -> dict[str, object]:
        from backend.app.services.ai_service import AiService

        try:
            status = await AiService(self.session, settings=self.settings).status()
        except Exception as exc:  # pragma: no cover - defensive
            return {"available": False, "error": redact_text(str(exc))}
        return {
            "enabled": status.enabled,
            "backend": status.backend,
            "runtime_available": status.runtime_available,
            "model_configured": bool(status.model_path),
            "model_exists": status.model_exists,
            "model_size_bytes": status.model_size_bytes,
            "model_loaded": status.model_loaded,
            "effective": status.effective,
            "reason": redact_text(status.reason),
        }

    async def _last_errors_payload(self) -> list[dict[str, object]]:
        from backend.app.services.events_service import EventsService

        events, _ = await EventsService(self.session).list(limit=20)
        errors = [
            e
            for e in events
            if e.level in {EventLevel.ERROR, EventLevel.CRITICAL} or not e.resolved
        ][:20]
        return [
            {
                "created_at": _iso(e.created_at),
                "level": str(e.level),
                "module": e.module,
                "status": e.status,
                "message": redact_text(e.message or ""),
                "how_to_fix": redact_text(e.how_to_fix or ""),
            }
            for e in errors
        ]

    def _paths_payload(self) -> dict[str, object]:
        root = paths.project_root()
        safe: dict[str, object] = {"root": root.name}
        for name, path in (
            ("data", paths.data_dir()),
            ("sessions", paths.sessions_dir()),
            ("backups", paths.backups_dir()),
            ("logs", paths.logs_dir()),
            ("exports", paths.exports_dir()),
        ):
            safe[name] = {
                "folder": path.name,
                "writable": paths.is_writable(path),
            }
        return safe

    # ------------------------------------------------------------------
    # Safe maintenance actions
    # ------------------------------------------------------------------
    def list_actions(self, app_state: object | None = None) -> list[MaintenanceAction]:
        scheduler_running = _scheduler_running(app_state)
        return [
            MaintenanceAction(
                key=ACTION_RESTART_SCHEDULER,
                title="Перезапустить планировщик",
                description=(
                    "Безопасно перезапускает обработчик запланированных действий. "
                    "Данные и очередь не удаляются; незавершённые задания продолжатся."
                ),
                destructive=False,
                requires_confirmation=False,
                available=True,
            ),
            MaintenanceAction(
                key=ACTION_RECHECK_TELEGRAM,
                title="Перепроверить Telegram",
                description=(
                    "Повторно проверяет связь с добавленными ботами. Токены не "
                    "показываются и не меняются."
                ),
                destructive=False,
                requires_confirmation=False,
                available=True,
            ),
            MaintenanceAction(
                key=ACTION_RECHECK_CHANNELS,
                title="Перепроверить каналы",
                description=(
                    "Повторно проверяет доступ к каналам через первый готовый аккаунт. "
                    "Ничего не изменяет и не удаляет."
                ),
                destructive=False,
                requires_confirmation=False,
                available=True,
            ),
            MaintenanceAction(
                key=ACTION_CLEANUP_JOBS,
                title="Очистить зависшие локальные задания",
                description=(
                    "Сбрасывает задания, зависшие в состоянии «выполняется», и отменяет "
                    "задания, срок которых давно прошёл. Пользовательские данные "
                    "не удаляются."
                ),
                destructive=False,
                requires_confirmation=True,
                available=not scheduler_running,
            ),
        ]

    async def run_action(
        self, key: str, app_state: object | None = None
    ) -> MaintenanceResult:
        if key == ACTION_RESTART_SCHEDULER:
            return await self._restart_scheduler(app_state)
        if key == ACTION_RECHECK_TELEGRAM:
            return await self._recheck_telegram()
        if key == ACTION_RECHECK_CHANNELS:
            return await self._recheck_channels()
        if key == ACTION_CLEANUP_JOBS:
            return await self._cleanup_jobs()
        return MaintenanceResult(
            action=key, ok=False, message="Неизвестное действие обслуживания."
        )

    async def _restart_scheduler(self, app_state: object | None) -> MaintenanceResult:
        if app_state is None:
            return MaintenanceResult(
                action=ACTION_RESTART_SCHEDULER,
                ok=False,
                message="Планировщик недоступен в этом режиме запуска.",
            )
        from backend.app.scheduler.handlers import register_handlers
        from backend.app.scheduler.scheduler import Scheduler

        scheduler = getattr(app_state, "scheduler", None)
        try:
            if scheduler is None:
                scheduler = Scheduler()
                register_handlers(scheduler)
                app_state.scheduler = scheduler  # type: ignore[attr-defined]
            else:
                await scheduler.stop()
            await scheduler.start()
        except Exception as exc:  # pragma: no cover - defensive
            return MaintenanceResult(
                action=ACTION_RESTART_SCHEDULER,
                ok=False,
                message="Не удалось перезапустить планировщик.",
                detail=redact_text(str(exc)),
            )
        return MaintenanceResult(
            action=ACTION_RESTART_SCHEDULER,
            ok=True,
            message="Планировщик перезапущен. Очередь сохранена.",
        )

    async def _recheck_telegram(self) -> MaintenanceResult:
        from backend.app.services.bot_service import BotService

        service = BotService(self.session, settings=self.settings)
        bots, _ = await self.bots.list(limit=500)
        checked = 0
        healthy = 0
        for bot in bots:
            if not bot.has_token:
                continue
            try:
                result = await service.health_check(bot.id)
            except Exception:  # pragma: no cover - defensive
                continue
            checked += 1
            if result.ok:
                healthy += 1
        return MaintenanceResult(
            action=ACTION_RECHECK_TELEGRAM,
            ok=True,
            affected=checked,
            message=(
                f"Проверено ботов: {checked}. Отвечают: {healthy}."
                if checked
                else "Нет ботов с токеном для проверки."
            ),
        )

    async def _recheck_channels(self) -> MaintenanceResult:
        from backend.app.services.channel_service import ChannelService, ChannelServiceError
        from backend.app.services.session_service import SessionService

        accounts = await SessionService(
            self.session, settings=self.settings
        ).list_accounts()
        ready = [a for a in accounts if a.enabled and a.status == SessionStatus.ONLINE]
        channels, _ = await self.channels.list(limit=500)
        if not channels:
            return MaintenanceResult(
                action=ACTION_RECHECK_CHANNELS,
                ok=True,
                message="Каналы не добавлены — проверять нечего.",
            )
        if not ready:
            return MaintenanceResult(
                action=ACTION_RECHECK_CHANNELS,
                ok=False,
                message="Нет готового аккаунта для проверки каналов.",
                detail="Добавьте и авторизуйте аккаунт в разделе «Аккаунты».",
            )
        account = ready[0]
        service = ChannelService(self.session, settings=self.settings)
        checked = 0
        ok_count = 0
        for channel in channels:
            try:
                result = await service.verify(channel.id, account.id)
            except ChannelServiceError:
                continue
            except Exception:  # pragma: no cover - defensive
                continue
            checked += 1
            if result.status in {"ok", "partial"}:
                ok_count += 1
        return MaintenanceResult(
            action=ACTION_RECHECK_CHANNELS,
            ok=True,
            affected=checked,
            message=f"Проверено каналов: {checked}. Доступны: {ok_count}.",
        )

    async def _cleanup_jobs(self) -> MaintenanceResult:
        overdue = await self.jobs.list_overdue(grace_seconds=300)
        reset = await self.jobs.recover_stuck_running()
        cancelled = await self.jobs.cancel_many([job.id for job in overdue])
        return MaintenanceResult(
            action=ACTION_CLEANUP_JOBS,
            ok=True,
            affected=reset + cancelled,
            message=(
                f"Сброшено зависших заданий: {reset}. Отменено устаревших: {cancelled}."
            ),
        )


class DiagnosticsError(RuntimeError):
    """Raised when a diagnostics report cannot be produced safely."""


def _scheduler_running(app_state: object | None) -> bool:
    if app_state is None:
        return False
    runtime = getattr(app_state, "scheduler", None)
    return runtime is not None and getattr(runtime, "_task", None) is not None


def _portable_runtime_label() -> str | None:
    """Return a label when running from a bundled runtime, else ``None``."""
    if getattr(sys, "frozen", False):
        return "собранное приложение"
    prefix = Path(sys.prefix)
    if "runtime" in prefix.parts:
        return "встроенный Python"
    return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _load_list(raw: str) -> list[str]:
    """Decode a JSON string list; never raises."""
    import json as _json

    try:
        value = _json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _render_text(payload: object) -> str:
    lines: list[str] = []
    lines.append("Отчёт диагностики Telegram Channel Management Suite")
    lines.append("=" * 56)
    lines.append("")
    _render_lines(payload, lines, indent=0)
    lines.append("")
    lines.append("Отчёт безопасно очищен от секретов.")
    return "\n".join(lines)


def _render_lines(value: object, lines: list[str], indent: int) -> None:
    pad = "  " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                _render_lines(item, lines, indent + 1)
            else:
                lines.append(f"{pad}{key}: {item}")
    elif isinstance(value, list):
        if not value:
            lines.append(f"{pad}(пусто)")
            return
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                _render_lines(item, lines, indent + 1)
            else:
                lines.append(f"{pad}- {item}")
    else:
        lines.append(f"{pad}{value}")


def _render_zip(payload: object) -> bytes:
    buffer = io.BytesIO()
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    text = _render_text(payload)
    readme = (
        "Отчёт диагностики Telegram Channel Management Suite.\n\n"
        "report.json — полный отчёт в машинном виде.\n"
        "report.txt  — тот же отчёт для чтения.\n\n"
        "Отчёт безопасно очищен от секретов: токены, api_hash/api_id, данные сессий,\n"
        "номера телефонов, пароли и содержимое базы данных не включаются.\n"
    )
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.json", json_text)
        archive.writestr("report.txt", text)
        archive.writestr("README.txt", readme)
    return buffer.getvalue()


__all__ = [
    "ACTION_CLEANUP_JOBS",
    "ACTION_RECHECK_CHANNELS",
    "ACTION_RECHECK_TELEGRAM",
    "ACTION_RESTART_SCHEDULER",
    "REDACTED",
    "STATUS_NOT_CONFIGURED",
    "DiagnosticsError",
    "DiagnosticsService",
]
