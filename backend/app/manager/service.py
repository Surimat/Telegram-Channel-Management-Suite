"""Manager-bot command handling and notification routing (post-1.0 hardening).

Turns the registered manager bot into a real control surface: it answers a small
set of plain-language RU commands and forwards important events as
notifications. All Telegram access goes through :class:`TelegramBotProvider`
(D-001); this module never imports aiogram and never touches tokens, session
files or the filesystem.

Security posture (see docs/SECURITY.md):
- Only Telegram **user ids** in the admin allow-list may run commands. A
  username is never sufficient.
- Unknown users get a neutral refusal; the attempt is logged but no system state
  is revealed and nothing administrative runs.
- Messages never contain secrets, tokens, API hashes or stack traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.db.models.bot import BotHealth
from backend.app.db.repositories.bots import BotRepository
from backend.app.manager.bus import (
    CATEGORIES,
    CATEGORY_LABELS,
    Notification,
    get_notification_bus,
)
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.events_service import EventsService

logger = get_logger(__name__)

MODULE = "manager.bot"

# Commands exposed to the owner. Descriptions are also registered as the bot's
# command menu (best effort).
COMMANDS: list[tuple[str, str]] = [
    ("start", "Начало работы и краткая справка"),
    ("help", "Список команд"),
    ("status", "Состояние системы"),
    ("bots", "Боты и их состояние"),
    ("accounts", "Telegram-аккаунты"),
    ("queue", "Очередь заданий"),
    ("reactions", "Автоматические реакции"),
    ("audience", "Аудитория и источники"),
    ("invites", "Приглашения"),
    ("backup", "Резервные копии"),
]

ADMIN_ONLY_HINT = "Команды доступны только владельцу системы."


@dataclass(slots=True)
class CommandResult:
    """Outcome of handling one command (for tests and logging)."""

    handled: bool
    authorized: bool
    command: str
    reply: str = ""
    refused: bool = False


class ManagerBotService:
    """Builds command replies and routes notifications for the manager bot."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: Any = build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.bots = BotRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory

    # --- authorization -------------------------------------------------------
    def is_admin(self, user_id: int | None) -> bool:
        """True only when ``user_id`` is in the configured admin allow-list."""
        if user_id is None:
            return False
        return user_id in self.settings.admin_ids

    # --- command dispatch ----------------------------------------------------
    async def handle_update(self, update: Any) -> CommandResult:
        """Handle one incoming update; returns what happened (never raises)."""
        text = (getattr(update, "text", "") or "").strip()
        user_id = getattr(update, "user_id", None)
        username = getattr(update, "username", "") or ""
        if not text.startswith("/"):
            return CommandResult(handled=False, authorized=False, command="")

        command = text[1:].split()[0].split("@")[0].lower()
        known = {name for name, _ in COMMANDS}
        if command not in known:
            return CommandResult(handled=False, authorized=False, command=command)

        if not self.is_admin(user_id):
            await self._log_refusal(user_id, username, command)
            return CommandResult(
                handled=True,
                authorized=False,
                command=command,
                reply=ADMIN_ONLY_HINT,
                refused=True,
            )

        reply = await self._reply_for(command)
        return CommandResult(handled=True, authorized=True, command=command, reply=reply)

    async def _reply_for(self, command: str) -> str:
        handler = getattr(self, f"_cmd_{command}", None)
        if handler is None:  # pragma: no cover - COMMANDS and handlers stay in sync
            return "Неизвестная команда."
        try:
            return await handler()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Manager command %s failed: %s", command, exc)
            return "Не удалось получить данные. Подробности — в разделе «Логи»."

    async def _log_refusal(self, user_id: int | None, username: str, command: str) -> None:
        await self.events.warning(
            MODULE,
            "Отклонена команда управляющего бота от неизвестного пользователя.",
            explanation="Этот Telegram-пользователь не входит в список владельцев.",
            how_to_fix="Добавьте его ID в «Владельцы» в настройках, если это нужно.",
            actor=f"@{username}" if username else str(user_id),
            operation=command,
            status="refused",
        )
        await self.session.commit()

    # --- commands ------------------------------------------------------------
    async def _cmd_start(self) -> str:
        return (
            "Здравствуйте! Это управляющий бот Telegram Channel Management Suite.\n\n"
            "Он присылает важные уведомления и показывает состояние системы.\n\n"
            + await self._help_text()
        )

    async def _cmd_help(self) -> str:
        return await self._help_text()

    async def _help_text(self) -> str:
        lines = ["Доступные команды:"]
        for name, desc in COMMANDS:
            lines.append(f"/{name} — {desc}")
        return "\n".join(lines)

    async def _cmd_status(self) -> str:
        from backend.app.services.system_service import SystemService

        checks = await SystemService(self.settings).setup_checks(self.session)
        overall = SystemService.overall_status(checks)
        title = {
            "ok": "Всё в порядке",
            "warning": "Требуется внимание",
            "error": "Есть проблемы",
        }.get(overall, "Состояние неизвестно")
        problems = [c for c in checks if c.status in ("warning", "error")]
        lines = [f"Состояние системы: {title}."]
        if problems:
            lines.append("")
            for check in problems[:6]:
                lines.append(f"• {check.title}: {check.meaning}")
                if check.how_to_fix:
                    lines.append(f"  Что сделать: {check.how_to_fix}")
        else:
            lines.append("Проблем не обнаружено.")
        return "\n".join(lines)

    async def _cmd_bots(self) -> str:
        bots, total = await self.bots.list()
        if total == 0:
            return (
                "Боты ещё не подключены.\n"
                "Добавьте управляющего бота в разделе «Боты»."
            )
        lines = [f"Ботов: {total}."]
        for bot in bots[:15]:
            label = f"@{bot.username}" if bot.username else str(bot.telegram_id or bot.id)
            state = {
                BotHealth.OK: "работает",
                BotHealth.WARNING: "нужно внимание",
                BotHealth.ERROR: "ошибка",
                BotHealth.UNKNOWN: "не проверен",
            }.get(bot.health, "неизвестно")
            lines.append(f"• {label} ({bot.kind.value}): {state}")
        return "\n".join(lines)

    async def _cmd_accounts(self) -> str:
        from backend.app.services.session_service import SessionService

        summary = await SessionService(self.session, settings=self.settings).summary()
        total = int(summary.get("total", 0))
        if total == 0:
            return (
                "Пользовательские аккаунты ещё не добавлены.\n"
                "Добавьте аккаунт в разделе «Аккаунты» (нужно для парсинга и приглашений)."
            )
        return (
            f"Аккаунтов: {total}.\n"
            f"• Готовы: {summary.get('online', 0)}\n"
            f"• Требуется авторизация: {summary.get('auth_required', 0)}\n"
            f"• Выключены: {summary.get('disabled', 0)}"
        )

    async def _cmd_queue(self) -> str:
        from backend.app.db.models.job import JobStatus
        from backend.app.services.queue_service import QueueService

        service = QueueService(self.session)
        _, total = await service.list(limit=1)
        if total == 0:
            return "Очередь пуста."
        active = 0
        for status in (
            JobStatus.PENDING,
            JobStatus.SCHEDULED,
            JobStatus.RUNNING,
            JobStatus.PAUSED,
        ):
            _, count = await service.list(status=status, limit=1)
            active += count
        return f"Заданий в очереди: {active} (всего записей: {total})."

    async def _cmd_reactions(self) -> str:
        from backend.app.services.reaction_service import ReactionService

        stats = await ReactionService(self.session, settings=self.settings).stats()
        if not stats.get("enabled"):
            return "Автоматические реакции выключены."
        return (
            f"Автоматические реакции включены.\n"
            f"• Ботов: {stats.get('active_bots', 0)}\n"
            f"• В очереди: {stats.get('queue_total', 0)}\n"
            f"• Выполнено за сутки: {stats.get('done_today', 0)}"
        )

    async def _cmd_audience(self) -> str:
        from backend.app.services.audience_service import AudienceService

        data = await AudienceService(self.session, settings=self.settings).dashboard()
        if not data.get("sources_total"):
            return "Источники аудитории ещё не добавлены (раздел «Аудитория»)."
        return (
            f"Источников: {data.get('sources_total', 0)}.\n"
            f"• Уникальных пользователей: {data.get('unique_users', 0)}\n"
            f"• Частичных результатов: {data.get('partial_sources', 0)}"
        )

    async def _cmd_invites(self) -> str:
        from backend.app.services.invite_service import InviteService

        summary = await InviteService(self.session, settings=self.settings).summary()
        counts = summary.get("by_status", {})
        total = sum(int(v) for v in counts.values())
        if total == 0:
            return "Задания приглашений ещё не создавались."
        running = counts.get("running", 0)
        paused = counts.get("paused", 0)
        return (
            f"Заданий приглашений: {total}.\n"
            f"• Выполняется: {running}\n"
            f"• На паузе: {paused}"
        )

    async def _cmd_backup(self) -> str:
        from backend.app.services.backup_service import BackupService

        entries = BackupService(self.session, settings=self.settings).list_backups()
        if not entries:
            return "Резервных копий пока нет. Создать можно в разделе «Резервные копии»."
        latest = entries[0]
        when = latest.created_at.strftime("%d.%m.%Y %H:%M") if latest.created_at else "—"
        return (
            f"Резервных копий: {len(entries)}.\n"
            f"Последняя: {when}."
        )

    # --- notifications -------------------------------------------------------
    async def notifications_enabled(self) -> bool:
        from backend.app.services.settings_service import SettingsService

        value = await SettingsService(self.session).get_typed(
            "notifications_enabled", True
        )
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    async def category_enabled(self, category: str) -> bool:
        from backend.app.services.settings_service import SettingsService

        value = await SettingsService(self.session).get_typed(
            f"notifications_{category}", True
        )
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def format_notification(self, notification: Notification) -> str:
        """Render a notification as a plain-language RU message (no secrets)."""
        label = CATEGORY_LABELS.get(notification.category, notification.category)
        lines = [f"[{label}] {notification.message}"]
        if notification.how_to_fix:
            lines.append(f"Что сделать: {notification.how_to_fix}")
        return "\n".join(lines)

    async def deliver_pending(self, provider: TelegramBotProvider, limit: int = 20) -> int:
        """Drain the bus and send the notifications the owner enabled.

        Never raises on delivery failure: a Telegram problem must not affect the
        main task. Returns the number of messages actually sent.
        """
        if not await self.notifications_enabled():
            get_notification_bus().drain(limit=1000)
            return 0
        chat_id = await self._owner_chat_id()
        if chat_id is None:
            get_notification_bus().drain(limit=1000)
            return 0
        sent = 0
        for notification in get_notification_bus().drain(limit=limit):
            if not await self.category_enabled(notification.category):
                continue
            try:
                await provider.send_message(chat_id, self.format_notification(notification))
                sent += 1
            except TelegramProviderError as exc:
                logger.warning("Notification delivery failed: %s", exc.message)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Notification delivery failed: %s", type(exc).__name__)
        return sent

    async def _owner_chat_id(self) -> int | None:
        """The admin user id notifications are sent to (first allow-listed id)."""
        admins = self.settings.admin_ids
        if admins:
            return admins[0]
        return None

    async def notification_settings(self) -> dict[str, Any]:
        """Return the current notification toggles for the UI."""
        enabled = await self.notifications_enabled()
        categories = {
            c: await self.category_enabled(c) for c in CATEGORIES
        }
        return {"enabled": enabled, "categories": categories}

    async def update_notification_settings(
        self, *, enabled: bool | None = None, categories: dict[str, bool] | None = None
    ) -> dict[str, Any]:
        from backend.app.services.settings_service import SettingsService

        service = SettingsService(self.session)
        if enabled is not None:
            await service.set("notifications_enabled", bool(enabled))
        for name, value in (categories or {}).items():
            if name in CATEGORIES:
                await service.set(f"notifications_{name}", bool(value))
        await self.session.flush()
        return await self.notification_settings()

    # --- provider / command menu --------------------------------------------
    async def manager_provider(self) -> TelegramBotProvider | None:
        """Build a provider for the enabled manager bot, or ``None``."""
        manager = await self.bots.get_manager()
        if manager is None or not manager.enabled or not manager.token_encrypted:
            return None
        from backend.app.core.security import open_secret

        try:
            token = open_secret(manager.token_encrypted, self.settings)
        except ValueError:
            return None
        return self._provider_factory(
            token, provider_name=manager.provider_name, settings=self.settings
        )

    async def register_commands(self, provider: TelegramBotProvider) -> bool:
        """Best-effort: publish the command menu to Telegram."""
        try:
            return await provider.set_commands(list(COMMANDS))
        except TelegramProviderError as exc:
            logger.info("Could not register manager commands: %s", exc.message)
            return False
        except Exception:  # pragma: no cover - defensive
            return False

    async def publish_event_notification(
        self,
        *,
        module: str,
        event_key: str,
        message: str,
        level: str,
        how_to_fix: str = "",
    ) -> None:
        """Publish an event-derived notification onto the bus (never raises)."""
        from backend.app.manager.bus import category_for_module

        get_notification_bus().publish(
            Notification(
                category=category_for_module(module),
                event_key=event_key,
                message=message,
                level=level,
                how_to_fix=how_to_fix,
            )
        )


def manager_bot_status_label(health: str) -> str:
    return {
        BotHealth.OK.value: "подключён",
        BotHealth.WARNING.value: "нужно внимание",
        BotHealth.ERROR.value: "ошибка",
    }.get(health, "не подключён")


__all__ = [
    "ADMIN_ONLY_HINT",
    "COMMANDS",
    "CommandResult",
    "ManagerBotService",
    "manager_bot_status_label",
]
