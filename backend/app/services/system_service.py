"""System service: setup checks and health verification.

Produces beginner-friendly checks consumed by the Setup Wizard (see docs/UI.md).
Messages are deliberately human-readable; raw error codes are avoided.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import paths
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_engine

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_UNKNOWN = "unknown"


@dataclass
class Check:
    key: str
    title: str
    status: str
    meaning: str
    how_to_fix: str = ""


class SystemService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def database_check(self) -> Check:
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return Check(
                "database",
                "База данных",
                STATUS_OK,
                "Хранилище данных работает и доступно.",
            )
        except Exception:  # pragma: no cover - depends on environment
            return Check(
                "database",
                "База данных",
                STATUS_ERROR,
                "Не удалось подключиться к хранилищу данных.",
                "Проверьте папку data/ и права на запись.",
            )

    def filesystem_check(self) -> Check:
        dirs = {
            "data": paths.data_dir(),
            "sessions": paths.sessions_dir(),
            "backups": paths.backups_dir(),
            "logs": paths.logs_dir(),
            "exports": paths.exports_dir(),
        }
        bad = [name for name, path in dirs.items() if not paths.is_writable(path)]
        if bad:
            return Check(
                "filesystem",
                "Файловая система",
                STATUS_ERROR,
                "Некоторые папки недоступны для записи: " + ", ".join(bad) + ".",
                "Запустите программу из папки, куда есть права на запись.",
            )
        return Check(
            "filesystem",
            "Файловая система",
            STATUS_OK,
            "Папки для данных, сессий, резервных копий и журналов доступны.",
        )

    def secret_key_check(self) -> Check:
        key = self.settings.app_secret_key.get_secret_value()
        if len(key) >= 16:
            return Check(
                "secret_key",
                "Ключ безопасности",
                STATUS_OK,
                "Ключ безопасности настроен.",
            )
        status = STATUS_ERROR if self.settings.is_production else STATUS_WARNING
        return Check(
            "secret_key",
            "Ключ безопасности",
            status,
            "Ключ безопасности не настроен или слишком короткий.",
            'Сгенерируйте ключ: python -c "import secrets; '
            'print(secrets.token_urlsafe(48))" и укажите его в файле .env (APP_SECRET_KEY).',
        )

    def manager_bot_check(self) -> Check:
        token = self.settings.manager_bot_token.get_secret_value()
        if token:
            return Check(
                "manager_bot",
                "Управляющий бот",
                STATUS_OK,
                "Управляющий бот подключён.",
            )
        return Check(
            "manager_bot",
            "Управляющий бот",
            STATUS_WARNING,
            "Управляющий бот ещё не подключён.",
            "Создайте бота через @BotFather и добавьте его токен в разделе «Боты».",
        )

    async def manager_bot_db_check(self, session: AsyncSession) -> Check:
        """DB-backed manager bot check with a plain-language result and hint."""
        from backend.app.db.models.bot import BotHealth
        from backend.app.db.repositories.bots import BotRepository

        manager = await BotRepository(session).get_manager()
        if manager is None:
            return Check(
                "manager_bot",
                "Управляющий бот",
                STATUS_WARNING,
                "Управляющий бот ещё не подключён.",
                "Создайте бота через @BotFather и добавьте его токен в разделе «Боты».",
            )
        if not manager.enabled:
            return Check(
                "manager_bot",
                "Управляющий бот",
                STATUS_WARNING,
                f"Управляющий бот @{manager.username} отключён.",
                "Включите бота в разделе «Боты», чтобы система могла им управлять.",
            )
        if manager.health == BotHealth.ERROR:
            return Check(
                "manager_bot",
                "Управляющий бот",
                STATUS_ERROR,
                f"Управляющий бот @{manager.username} не отвечает.",
                manager.health_hint
                or "Проверьте токен бота и повторите проверку в разделе «Боты».",
            )
        if manager.health == BotHealth.OK:
            return Check(
                "manager_bot",
                "Управляющий бот",
                STATUS_OK,
                f"Управляющий бот @{manager.username} подключён и отвечает.",
            )
        return Check(
            "manager_bot",
            "Управляющий бот",
            STATUS_WARNING,
            f"Управляющий бот @{manager.username} добавлен, но ещё не проверялся.",
            "Нажмите «Проверить» в разделе «Боты».",
        )

    async def managed_bots_check(self, session: AsyncSession) -> Check:
        """Report how many Telegram managed bots are registered locally."""
        from backend.app.db.models.bot import BotKind
        from backend.app.db.repositories.bots import BotRepository

        bots, count = await BotRepository(session).list(kind=BotKind.MANAGED)
        if count == 0:
            return Check(
                "managed_bots",
                "Управляемые боты",
                STATUS_OK,
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
        )

    def telegram_api_check(self) -> Check:
        if self.settings.telegram_api_id and self.settings.telegram_api_hash.get_secret_value():
            return Check(
                "telegram_api",
                "Доступ к Telegram API",
                STATUS_OK,
                "API ID и API Hash указаны.",
            )
        return Check(
            "telegram_api",
            "Доступ к Telegram API",
            STATUS_WARNING,
            "Не указаны API ID и API Hash (нужны для работы с аккаунтами).",
            "Получите их на https://my.telegram.org и добавьте в разделе «Аккаунты».",
        )

    def telethon_check(self) -> Check:
        """Check that the MTProto library is importable (PHASE 4)."""
        try:
            import telethon  # noqa: F401

            return Check(
                "telethon",
                "Библиотека для аккаунтов",
                STATUS_OK,
                "Компонент для работы с пользовательскими аккаунтами установлен.",
            )
        except Exception:  # pragma: no cover - depends on environment
            return Check(
                "telethon",
                "Библиотека для аккаунтов",
                STATUS_ERROR,
                "Компонент для работы с аккаунтами не установлен.",
                "Установите зависимости: pip install -r backend/requirements.txt.",
            )

    def sessions_dir_check(self) -> Check:
        """Check the sessions directory is present and writable (PHASE 4)."""
        session_dir = self.settings.resolve_sessions_dir()
        if paths.is_writable(session_dir):
            return Check(
                "sessions_dir",
                "Папка сессий",
                STATUS_OK,
                "Папка для файлов аккаунтов доступна.",
            )
        return Check(
            "sessions_dir",
            "Папка сессий",
            STATUS_ERROR,
            "Папка для файлов аккаунтов недоступна для записи.",
            "Запустите программу из папки, куда есть права на запись.",
        )

    async def accounts_check(self, session: AsyncSession) -> Check:
        """Report the user-account state in plain language (PHASE 4)."""
        from backend.app.services.session_service import SessionService

        service = SessionService(session, settings=self.settings)
        accounts = await service.list_accounts()
        if not accounts:
            return Check(
                "accounts",
                "Пользовательские аккаунты",
                STATUS_WARNING,
                "Пользовательские аккаунты ещё не добавлены.",
                "Добавьте аккаунт в разделе «Аккаунты» (нужно для парсинга и приглашений).",
            )
        online = sum(1 for a in accounts if a.status.value == "online")
        need_auth = sum(1 for a in accounts if a.status.value == "auth_required")
        missing_files = 0
        for account in accounts:
            if account.has_session and not service.session_file_info(account).exists:
                missing_files += 1
        if missing_files:
            return Check(
                "accounts",
                "Пользовательские аккаунты",
                STATUS_WARNING,
                f"Аккаунтов: {len(accounts)}. У {missing_files} отсутствует файл сессии.",
                "Проверьте аккаунты в разделе «Аккаунты» и при необходимости добавьте заново.",
            )
        if online == 0:
            return Check(
                "accounts",
                "Пользовательские аккаунты",
                STATUS_WARNING,
                f"Аккаунтов: {len(accounts)}, но ни один не авторизован.",
                "Проверьте аккаунты в разделе «Аккаунты» (кнопка «Проверить»).",
            )
        if need_auth:
            return Check(
                "accounts",
                "Пользовательские аккаунты",
                STATUS_WARNING,
                f"Аккаунтов: {len(accounts)}, требуется авторизация: {need_auth}.",
                "Запустите мастер повторной авторизации в разделе «Аккаунты».",
            )
        return Check(
            "accounts",
            "Пользовательские аккаунты",
            STATUS_OK,
            f"Готовых аккаунтов: {online} из {len(accounts)}.",
        )

    async def audience_check(self, session: AsyncSession) -> Check:
        """Report the audience subsystem state in plain language (PHASE 5)."""
        from backend.app.services.audience_service import AudienceService

        service = AudienceService(session, settings=self.settings)
        sources_total = await service.sources.count()
        users_total = await service.users.count()
        partial = await service.sources.partial_count()
        if sources_total == 0:
            return Check(
                "audience",
                "Аудитория",
                STATUS_WARNING,
                "Источники аудитории ещё не добавлены.",
                "Откройте раздел «Аудитория» и добавьте канал или группу для анализа.",
            )
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
        )

    def ai_check(self) -> Check:
        if not self.settings.ai_enabled:
            return Check(
                "ai",
                "Мини-ИИ (необязательно)",
                STATUS_OK,
                "ИИ выключен. Система использует только правила — это нормально.",
            )
        if self.settings.ai_model_path:
            return Check(
                "ai",
                "Мини-ИИ",
                STATUS_OK,
                "ИИ включён и модель указана.",
            )
        return Check(
            "ai",
            "Мини-ИИ",
            STATUS_WARNING,
            "ИИ включён, но путь к модели не указан.",
            "Укажите путь к модели .gguf в разделе «AI» или выключите ИИ.",
        )

    async def reactions_check(self, session: AsyncSession) -> Check:
        """Report the Reaction Manager state in plain language (PHASE 3)."""
        from backend.app.services.reaction_service import ReactionService

        service = ReactionService(session, settings=self.settings)
        enabled = await service.reactions_enabled()
        active_bots = len(await service.active_bots())
        if not enabled:
            return Check(
                "reactions",
                "Автоматические реакции",
                STATUS_OK,
                "Реакции выключены — система ничего не ставит автоматически.",
                "Включите реакции в разделе «Реакции», если хотите автоматические реакции.",
            )
        if active_bots == 0:
            return Check(
                "reactions",
                "Автоматические реакции",
                STATUS_WARNING,
                "Реакции включены, но нет подходящих ботов.",
                "Добавьте обычного бота с действующим токеном в разделе «Боты».",
            )
        return Check(
            "reactions",
            "Автоматические реакции",
            STATUS_OK,
            f"Реакции включены. Готовых ботов: {active_bots}.",
        )

    async def invites_check(self, session: AsyncSession) -> Check:
        """Report the Invite Manager state in plain language (PHASE 6)."""
        from backend.app.services.invite_service import InviteService

        service = InviteService(session, settings=self.settings)
        summary = await service.summary()
        counts = summary.get("by_status", {})
        active = counts.get("running", 0) + counts.get("paused", 0)
        total = sum(int(v) for v in counts.values())
        waiting = counts.get("paused", 0)
        if total == 0:
            return Check(
                "invites",
                "Приглашения",
                STATUS_OK,
                "Задания приглашений ещё не создавались.",
                "Раздел «Приглашения» позволяет приглашать людей из аудитории в канал.",
            )
        if waiting:
            return Check(
                "invites",
                "Приглашения",
                STATUS_WARNING,
                f"Всего заданий: {total}, на паузе: {waiting}.",
                "Откройте «Приглашения»: возможно, Telegram попросил подождать.",
            )
        if active:
            return Check(
                "invites",
                "Приглашения",
                STATUS_OK,
                f"Выполняется заданий: {active}.",
            )
        return Check(
            "invites",
            "Приглашения",
            STATUS_OK,
            f"Заданий приглашений: {total}.",
        )

    async def setup_checks(self, session: AsyncSession | None = None) -> list[Check]:
        checks: list[Check] = [
            Check("runtime", "Среда выполнения", STATUS_OK, "Программа запущена правильно."),
            await self.database_check(),
            self.filesystem_check(),
            self.secret_key_check(),
            self.telegram_api_check(),
            self.telethon_check(),
            self.sessions_dir_check(),
        ]
        if session is not None:
            checks.append(await self.manager_bot_db_check(session))
            checks.append(await self.managed_bots_check(session))
            checks.append(await self.reactions_check(session))
            checks.append(await self.accounts_check(session))
            checks.append(await self.audience_check(session))
            checks.append(await self.invites_check(session))
        else:
            checks.append(self.manager_bot_check())
        checks.append(self.ai_check())
        return checks

    @staticmethod
    def overall_status(checks: list[Check]) -> str:
        statuses = {c.status for c in checks}
        if STATUS_ERROR in statuses:
            return STATUS_ERROR
        if STATUS_WARNING in statuses:
            return STATUS_WARNING
        return STATUS_OK
