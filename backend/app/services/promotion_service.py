"""Promotion wizard service (product slice: onboarding).

Turns the scattered setup pages into one guided flow. The wizard is **derived**:
each step's status is computed from the real system state (a channel exists? a
bot is bound and ready? a session is present? campaigns configured?), so it never
lies about progress and never asks the owner to repeat work.

Presets choose which steps are required:

* ``minimal``       — just enough to see the app work (channel + manager bot).
* ``bot_only``      — full reactions/promotion with **no user session**.
* ``basic``         — bot-only plus audience + invites through a session.
* ``advanced``      — basic plus AI and analytics.
* ``professional``  — everything, including remote backups and auto-update.

Adaptive branches: steps that need a session are shown as ``optional`` (not
``todo``) when no session exists, and the bot-only alternative is offered instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.binding import BindingStatus
from backend.app.db.models.onboarding import (
    PRESET_ADVANCED,
    PRESET_BASIC,
    PRESET_BOT_ONLY,
    PRESET_MINIMAL,
    PRESET_PROFESSIONAL,
    PromotionProgress,
)
from backend.app.db.models.session import SessionStatus
from backend.app.db.repositories.bindings import BindingRepository
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.campaigns import CampaignRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.destinations import PromotionRepository
from backend.app.db.repositories.sessions import SessionRepository
from backend.app.services.backup_service import BackupService
from backend.app.services.events_service import EventsService

MODULE = "promotion"

#: Step statuses (shown verbatim in the UI).
STEP_DONE = "done"
STEP_TODO = "todo"
STEP_OPTIONAL = "optional"
STEP_BLOCKED = "blocked"

STEP_STATUS_TITLES = {
    STEP_DONE: "Готово",
    STEP_TODO: "Нужно сделать",
    STEP_OPTIONAL: "Можно пропустить",
    STEP_BLOCKED: "Требует шага выше",
}

#: Preset definitions: id → (title, description, required step keys).
PRESETS: dict[str, dict[str, object]] = {
    PRESET_MINIMAL: {
        "title": "Минимум",
        "description": "Проверить, что программа работает: канал и управляющий бот.",
        "steps": ["channel", "manager_bot"],
        "requires_session": False,
    },
    PRESET_BOT_ONLY: {
        "title": "Только боты (без аккаунта)",
        "description": "Реакции и продвижение ссылками без входа в аккаунт Telegram.",
        "steps": ["channel", "manager_bot", "bind_bot", "reactions", "campaigns"],
        "requires_session": False,
    },
    PRESET_BASIC: {
        "title": "Базовый",
        "description": "Всё для ботов плюс аудитория и приглашения через аккаунт.",
        "steps": [
            "channel",
            "manager_bot",
            "bind_bot",
            "reactions",
            "account",
            "audience",
            "invites",
        ],
        "requires_session": True,
    },
    PRESET_ADVANCED: {
        "title": "Продвинутый",
        "description": "Базовый набор плюс аналитика и мини-ИИ.",
        "steps": [
            "channel",
            "manager_bot",
            "bind_bot",
            "reactions",
            "account",
            "audience",
            "invites",
            "analytics",
            "ai",
            "config_sync",
        ],
        "requires_session": True,
    },
    PRESET_PROFESSIONAL: {
        "title": "Профессиональный",
        "description": "Всё, включая удалённые резервные копии и обновления.",
        "steps": [
            "channel",
            "manager_bot",
            "bind_bot",
            "reactions",
            "account",
            "audience",
            "invites",
            "analytics",
            "ai",
            "config_sync",
            "backup",
            "update",
        ],
        "requires_session": True,
    },
}


@dataclass(slots=True)
class WizardStep:
    key: str
    title: str
    description: str
    status: str
    status_title: str
    how_to_fix: str = ""
    route: str = ""
    requires_session: bool = False


@dataclass(slots=True)
class WizardState:
    preset: str
    preset_title: str
    preset_description: str
    has_session: bool
    mode: str  # "bot_only" | "with_session"
    completed: bool
    dismissed: bool
    current_step: str
    completed_steps: int
    total_steps: int
    steps: list[WizardStep] = field(default_factory=list)
    #: Shown when no account is connected: what still works and why the account
    #: is optional (product requirement: adaptive onboarding).
    session_optional_note: str = ""
    #: Shown when an account is connected: the invite-restriction risk warning.
    session_risk_note: str = ""
    #: Evaluated capability graph (v1.5): the single source of truth for what is
    #: available now and what still needs setup. Keeps the wizard from
    #: re-deriving "does this need a session?" on its own.
    capabilities: list = field(default_factory=list)


class PromotionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PromotionRepository(session)
        self.channels = ChannelRepository(session)
        self.bots = BotRepository(session)
        self.bindings = BindingRepository(session)
        self.sessions = SessionRepository(session)
        self.campaigns = CampaignRepository(session)
        self.events = EventsService(session)

    # --- state ---------------------------------------------------------------
    async def state(self) -> WizardState:
        progress = await self.repo.get_or_create()
        preset = progress.preset if progress.preset in PRESETS else PRESET_BOT_ONLY
        return await self._build(progress, preset)

    async def set_preset(self, preset: str) -> WizardState:
        if preset not in PRESETS:
            preset = PRESET_BOT_ONLY
        progress = await self.repo.get_or_create()
        progress.preset = preset
        await self.session.flush()
        await self.session.commit()
        return await self._build(progress, preset)

    async def set_step(self, step: str) -> WizardState:
        progress = await self.repo.get_or_create()
        progress.current_step = step
        await self.session.flush()
        await self.session.commit()
        return await self._build(progress, progress.preset or PRESET_BOT_ONLY)

    async def finish(self) -> WizardState:
        progress = await self.repo.get_or_create()
        progress.completed = True
        progress.dismissed = False
        from backend.app.db.base import utcnow

        progress.finished_at = utcnow()
        await self.session.flush()
        await self.session.commit()
        await self._event("Мастер настройки завершён.")
        return await self._build(progress, progress.preset or PRESET_BOT_ONLY)

    async def dismiss(self) -> WizardState:
        progress = await self.repo.get_or_create()
        progress.dismissed = True
        await self.session.flush()
        await self.session.commit()
        return await self._build(progress, progress.preset or PRESET_BOT_ONLY)

    # --- builder -------------------------------------------------------------
    async def _build(self, progress: PromotionProgress, preset: str) -> WizardState:
        has_session = await self._has_session()
        mode = "with_session" if has_session else "bot_only"
        required = list(PRESETS[preset]["steps"])  # type: ignore[arg-type]

        steps = await self._steps(required, has_session=has_session)
        done = sum(1 for s in steps if s.status == STEP_DONE)
        total = sum(1 for s in steps if s.status != STEP_OPTIONAL) or len(steps)

        progress.total_steps = total
        progress.completed_steps = done
        if done >= total and not progress.completed:
            progress.completed = True
            from backend.app.db.base import utcnow

            progress.finished_at = utcnow()
        await self.session.flush()

        return WizardState(
            preset=preset,
            preset_title=str(PRESETS[preset]["title"]),
            preset_description=str(PRESETS[preset]["description"]),
            has_session=has_session,
            mode=mode,
            completed=progress.completed,
            dismissed=progress.dismissed,
            current_step=progress.current_step,
            completed_steps=done,
            total_steps=total,
            steps=steps,
            session_optional_note=(
                ""
                if has_session
                else (
                    "Подключить личный Telegram-аккаунт — необязательно. Это откроет "
                    "расширенный доступ к аудитории. Без него доступны: подключение "
                    "ботов, реакции, кампании ссылок, аналитика с момента подключения, "
                    "резервные копии и диагностика."
                )
            ),
            session_risk_note=(
                "Использование пользовательского Telegram-аккаунта для массовых "
                "приглашений может привести к ограничениям или блокировке. Telegram "
                "не предоставляет универсального безопасного лимита."
                if has_session
                else ""
            ),
            capabilities=await self._capabilities(),
        )

    async def _capabilities(self) -> list[dict[str, object]]:
        """Evaluate the capability graph for the wizard (best-effort)."""
        try:
            from backend.app.services.capability_graph import (
                context_from_db,
                evaluate_all,
            )

            context = await context_from_db(self.session)
            return [state.as_dict() for state in evaluate_all(context)]
        except Exception:  # pragma: no cover - never break the wizard
            return []

    async def _steps(self, required: list[str], *, has_session: bool) -> list[WizardStep]:
        builders = {
            "channel": self._step_channel,
            "manager_bot": self._step_manager_bot,
            "bind_bot": self._step_bind_bot,
            "reactions": self._step_reactions,
            "campaigns": self._step_campaigns,
            "account": self._step_account,
            "audience": self._step_audience,
            "invites": self._step_invites,
            "analytics": self._step_analytics,
            "ai": self._step_ai,
            "config_sync": self._step_config_sync,
            "backup": self._step_backup,
            "update": self._step_update,
        }
        steps: list[WizardStep] = []
        for key in required:
            builder = builders.get(key)
            if builder is None:
                continue
            steps.append(await builder(has_session=has_session))
        return steps

    async def _step_channel(self, *, has_session: bool) -> WizardStep:
        _channels, total = await self.channels.list()
        done = total > 0
        return WizardStep(
            key="channel",
            title="Добавить канал",
            description="Один раз добавьте канал или группу — все разделы будут использовать его.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "Откройте «Каналы» → «Добавить канал».",
            route="/channels",
        )

    async def _step_manager_bot(self, *, has_session: bool) -> WizardStep:
        manager = await self.bots.get_manager()
        done = manager is not None and manager.health.value in {"ok", "unknown"}
        return WizardStep(
            key="manager_bot",
            title="Подключить управляющего бота",
            description="Управляющий бот выполняет команды и присылает уведомления.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "Создайте бота в @BotFather и вставьте токен в «Боты».",
            route="/bots",
        )

    async def _step_bind_bot(self, *, has_session: bool) -> WizardStep:
        bindings = await self.bindings.list_all()
        ready = [b for b in bindings if b.status is BindingStatus.READY]
        done = bool(ready)
        return WizardStep(
            key="bind_bot",
            title="Подключить бота к каналу",
            description="После этого бот сможет ставить реакции без входа в аккаунт.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Каналы» → выберите канал → «Подключить бота».",
            route="/channels",
        )

    async def _step_reactions(self, *, has_session: bool) -> WizardStep:
        from backend.app.services.reaction_service import ReactionService

        service = ReactionService(self.session)
        profile = await service.get_active_profile()
        done = bool(profile and profile.enabled)
        return WizardStep(
            key="reactions",
            title="Включить реакции",
            description="Настройте профиль реакций и включите систему.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Реакции» → выберите профиль → включите.",
            route="/reactions",
        )

    async def _step_campaigns(self, *, has_session: bool) -> WizardStep:
        _rows, total = await self.campaigns.list(limit=1)
        done = total > 0
        return WizardStep(
            key="campaigns",
            title="Создать кампанию приглашений",
            description="Продвижение ссылками работает без входа в аккаунт.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Приглашения» → «Кампании» → создайте кампанию.",
            route="/invites",
        )

    async def _step_account(self, *, has_session: bool) -> WizardStep:
        if not has_session:
            return WizardStep(
                key="account",
                title="Добавить аккаунт Telegram (необязательно)",
                description="Аккаунт нужен только для разбора аудитории и приглашений.",
                status=STEP_OPTIONAL,
                status_title=STEP_STATUS_TITLES[STEP_OPTIONAL],
                how_to_fix="Можно пропустить: реакции и продвижение ссылками работают "
                "без аккаунта.",
                route="/sessions",
                requires_session=True,
            )
        sessions, _total = await self.sessions.list()
        online = [s for s in sessions if s.status is SessionStatus.ONLINE]
        done = bool(online)
        return WizardStep(
            key="account",
            title="Добавить аккаунт Telegram",
            description="Аккаунт используется для разбора аудитории и приглашений.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Аккаунты» → «Добавить аккаунт».",
            route="/sessions",
            requires_session=True,
        )

    async def _step_audience(self, *, has_session: bool) -> WizardStep:
        if not has_session:
            return self._session_optional(
                "audience",
                "Собрать аудиторию (необязательно)",
                "Разбор участников требует аккаунта Telegram.",
                "/audience",
            )
        from backend.app.db.repositories.audience import AudienceSourceRepository

        _sources, total = await AudienceSourceRepository(self.session).list(limit=1)
        done = total > 0
        return WizardStep(
            key="audience",
            title="Добавить источник аудитории",
            description="Укажите канал-донор, из которого собирать участников.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Источники» → «Добавить источник».",
            route="/sources",
        )

    async def _step_invites(self, *, has_session: bool) -> WizardStep:
        if not has_session:
            return self._session_optional(
                "invites",
                "Приглашения через аккаунт (необязательно)",
                "Прямые приглашения требуют аккаунта. Без него используйте кампании ссылок.",
                "/invites",
            )
        from backend.app.db.repositories.invites import InviteJobRepository

        _jobs, total = await InviteJobRepository(self.session).list(limit=1)
        done = total > 0
        return WizardStep(
            key="invites",
            title="Настроить приглашения",
            description="Создайте рассылку приглашений по собранной аудитории.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Приглашения» → «Новая рассылка».",
            route="/invites",
        )

    async def _step_analytics(self, *, has_session: bool) -> WizardStep:
        from backend.app.db.repositories.posts import PostRepository

        _rows, total = await PostRepository(self.session).list(limit=1)
        done = total > 0
        return WizardStep(
            key="analytics",
            title="Посмотреть аналитику",
            description="Аналитика наполняется автоматически по мере работы.",
            status=STEP_DONE if done else STEP_OPTIONAL,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_OPTIONAL],
            how_to_fix="" if done else "Загляните в «Аналитику» после первых постов.",
            route="/analytics",
        )

    async def _step_ai(self, *, has_session: bool) -> WizardStep:
        from backend.app.services.ai_service import AiService

        status = await AiService(self.session).status()
        done = status.effective
        return WizardStep(
            key="ai",
            title="Включить мини-ИИ (необязательно)",
            description="Локальная модель улучшает разбор постов, но не обязательна.",
            status=STEP_DONE if done else STEP_OPTIONAL,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_OPTIONAL],
            how_to_fix="" if done else "Можно пропустить: обычные правила работают без ИИ.",
            route="/ai",
        )

    async def _step_config_sync(self, *, has_session: bool) -> WizardStep:
        from backend.app.services.config_sync_service import ConfigSyncService

        status = await ConfigSyncService(self.session).status()
        done = status.state == "available"
        if done:
            status_value = STEP_DONE
        elif status.owner_ready:
            status_value = STEP_OPTIONAL
        else:
            status_value = STEP_TODO
        return WizardStep(
            key="config_sync",
            title="Настроить перенос настроек (необязательно)",
            description=(
                "Профиль владельца и синхронизация перенесут настройки на новый "
                "компьютер. Файлы сессий и база данных не копируются."
            ),
            status=status_value,
            status_title=STEP_STATUS_TITLES[status_value],
            how_to_fix=(
                ""
                if done
                else "Раздел «Владелец»: создайте профиль и подключите синхронизацию."
            ),
            route="/owner",
        )

    async def _step_backup(self, *, has_session: bool) -> WizardStep:
        entries = BackupService(self.session).list_backups()
        done = bool(entries)
        return WizardStep(
            key="backup",
            title="Сделать резервную копию",
            description="Копия защитит данные при сбое или переезде на другой компьютер.",
            status=STEP_DONE if done else STEP_TODO,
            status_title=STEP_STATUS_TITLES[STEP_DONE if done else STEP_TODO],
            how_to_fix="" if done else "«Резервные копии» → «Создать копию».",
            route="/backup",
        )

    async def _step_update(self, *, has_session: bool) -> WizardStep:
        return WizardStep(
            key="update",
            title="Настроить обновления (необязательно)",
            description="Обновления можно проверять вручную или включить автообновление.",
            status=STEP_OPTIONAL,
            status_title=STEP_STATUS_TITLES[STEP_OPTIONAL],
            how_to_fix="Откройте «Система» → «Обновления».",
            route="/system",
        )

    @staticmethod
    def _session_optional(key: str, title: str, description: str, route: str) -> WizardStep:
        return WizardStep(
            key=key,
            title=title,
            description=description,
            status=STEP_OPTIONAL,
            status_title=STEP_STATUS_TITLES[STEP_OPTIONAL],
            how_to_fix="Можно пропустить без аккаунта.",
            route=route,
            requires_session=True,
        )

    async def _has_session(self) -> bool:
        sessions, _ = await self.sessions.list()
        return any(s.enabled and s.status is SessionStatus.ONLINE for s in sessions)

    async def _event(self, message: str) -> None:
        await self.events.info(MODULE, message, operation="wizard", status="ok")
        await self.session.commit()


def preset_list() -> list[dict[str, object]]:
    return [
        {
            "id": key,
            "title": str(value["title"]),
            "description": str(value["description"]),
            "requires_session": bool(value["requires_session"]),
        }
        for key, value in PRESETS.items()
    ]


__all__ = [
    "PRESETS",
    "STEP_BLOCKED",
    "STEP_DONE",
    "STEP_OPTIONAL",
    "STEP_STATUS_TITLES",
    "STEP_TODO",
    "PromotionService",
    "WizardState",
    "WizardStep",
    "preset_list",
]
