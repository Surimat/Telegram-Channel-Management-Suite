"""Bot service: the bot inventory and manager-bot workflow.

Coordinates the bot repository, the Telegram provider abstraction, secret
sealing and the event log. No Telegram library types and no tokens ever leave
this layer (decision D-001, D-010).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret, seal_secret
from backend.app.db.base import utcnow
from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.repositories.bots import BotRepository
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.events_service import EventsService

ProviderFactory = Callable[..., TelegramBotProvider]

MANAGER_BOT_LINK = "https://t.me/newbot/{manager}/{username}?name={name}"


class BotServiceError(Exception):
    """A bot operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class BotHealthResult:
    bot_id: str
    ok: bool
    status: str
    message: str
    how_to_fix: str = ""
    username: str = ""
    telegram_id: int | None = None


class BotService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = BotRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory

    # --- provider helpers ----------------------------------------------------
    def _provider_for(self, token: str, provider_name: str) -> TelegramBotProvider:
        return self._provider_factory(
            token, provider_name=provider_name, settings=self.settings
        )

    def provider_for(self, bot: Bot) -> TelegramBotProvider:
        """Build a provider for a stored bot (raises if it has no token)."""
        return self._provider_for(self._token_of(bot), bot.provider_name)

    def _token_of(self, bot: Bot) -> str:
        if not bot.token_encrypted:
            raise BotServiceError(
                "У этого бота нет сохранённого токена.",
                how_to_fix="Получите токен через управляющего бота (см. «Управляемые боты»).",
            )
        try:
            return open_secret(bot.token_encrypted, self.settings)
        except ValueError as exc:
            raise BotServiceError(
                "Не удалось прочитать сохранённый токен бота.",
                how_to_fix="Проверьте, что APP_SECRET_KEY не менялся. При необходимости "
                "добавьте бота заново.",
            ) from exc

    # --- inventory -----------------------------------------------------------
    async def list_bots(
        self, *, kind: BotKind | None = None, enabled: bool | None = None
    ) -> list[Bot]:
        bots, _ = await self.repo.list(kind=kind, enabled=enabled)
        return bots

    async def get(self, bot_id: str) -> Bot | None:
        return await self.repo.get(bot_id)

    async def add_bot(
        self,
        token: str,
        *,
        kind: BotKind = BotKind.ORDINARY,
        provider_name: str | None = None,
        title: str = "",
    ) -> Bot:
        """Validate a token with Telegram and store the bot.

        The token is verified by calling ``getMe``; it is only persisted (sealed)
        after successful validation.
        """
        token = (token or "").strip()
        if not token:
            raise BotServiceError(
                "Не указан токен бота.",
                how_to_fix="Создайте бота в @BotFather и скопируйте токен сюда.",
            )
        if kind == BotKind.MANAGER:
            existing = await self.repo.get_manager()
            if existing is not None:
                raise BotServiceError(
                    "Управляющий бот уже подключён.",
                    how_to_fix="Удалите или отключите текущего управляющего бота, "
                    "прежде чем добавлять нового.",
                    status_code=409,
                )

        provider_name = provider_name or self.settings.telegram_provider
        provider = self._provider_for(token, provider_name)
        try:
            identity = await provider.health_check()
        except TelegramProviderError as exc:
            await self.events.warning(
                "bots.bot_service",
                "Не удалось подключить бота: проверка не пройдена.",
                explanation=exc.message,
                how_to_fix=exc.how_to_fix,
            )
            await self.session.commit()
            raise BotServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.close()

        dup = await self.repo.get_by_telegram_id(identity.id)
        if dup is not None:
            dup.enabled = True
            dup.token_encrypted = seal_secret(token, self.settings)
            dup.provider_name = provider_name
            dup.health = BotHealth.OK
            dup.health_message = "Бот подключён."
            dup.health_hint = ""
            dup.last_error = ""
            dup.last_health_at = utcnow()
            await self.session.flush()
            return dup

        bot = Bot(
            kind=kind,
            enabled=True,
            telegram_id=identity.id,
            username=identity.username,
            title=title or identity.first_name or identity.username,
            token_encrypted=seal_secret(token, self.settings),
            provider_name=provider_name,
            can_manage_bots=identity.can_manage_bots,
            health=BotHealth.OK,
            health_message="Бот подключён и отвечает.",
            health_hint="",
            last_health_at=utcnow(),
        )
        await self.repo.add(bot)
        await self.events.info(
            "bots.bot_service",
            f"Добавлен бот @{bot.username or bot.telegram_id} ({bot.kind}).",
            actor=f"@{bot.username}" if bot.username else str(bot.telegram_id),
            operation="add_bot",
            status="ok",
        )
        await self.session.commit()
        return bot

    async def remove(self, bot_id: str) -> None:
        """Remove a bot from the active configuration and delete its record."""
        bot = await self.repo.get(bot_id)
        if bot is None:
            raise BotServiceError("Бот не найден.", status_code=404)
        label = f"@{bot.username}" if bot.username else str(bot.telegram_id)
        await self.repo.delete(bot)
        await self.events.warning(
            "bots.bot_service",
            f"Бот {label} удалён из конфигурации.",
            operation="remove_bot",
            status="ok",
        )
        await self.session.commit()

    async def set_enabled(self, bot_id: str, enabled: bool) -> Bot:
        bot = await self.repo.get(bot_id)
        if bot is None:
            raise BotServiceError("Бот не найден.", status_code=404)
        bot.enabled = enabled
        await self.session.flush()
        await self.session.commit()
        return bot

    # --- health --------------------------------------------------------------
    async def health_check(self, bot_id: str) -> BotHealthResult:
        bot = await self.repo.get(bot_id)
        if bot is None:
            raise BotServiceError("Бот не найден.", status_code=404)
        try:
            token = self._token_of(bot)
        except BotServiceError as exc:
            bot.health = BotHealth.WARNING
            bot.health_message = exc.message
            bot.health_hint = exc.how_to_fix
            bot.last_health_at = utcnow()
            await self.session.commit()
            return BotHealthResult(
                bot_id=bot.id,
                ok=False,
                status=bot.health.value,
                message=exc.message,
                how_to_fix=exc.how_to_fix,
                username=bot.username,
                telegram_id=bot.telegram_id,
            )

        provider = self._provider_for(token, bot.provider_name)
        try:
            identity = await provider.health_check()
            bot.telegram_id = identity.id
            bot.username = identity.username or bot.username
            bot.title = bot.title or identity.first_name
            bot.can_manage_bots = identity.can_manage_bots
            bot.health = BotHealth.OK
            bot.health_message = "Бот отвечает."
            bot.health_hint = ""
            bot.last_error = ""
            result = BotHealthResult(
                bot_id=bot.id,
                ok=True,
                status=BotHealth.OK.value,
                message=bot.health_message,
                username=bot.username,
                telegram_id=bot.telegram_id,
            )
        except TelegramProviderError as exc:
            bot.health = BotHealth.ERROR
            bot.health_message = exc.message
            bot.health_hint = exc.how_to_fix
            bot.last_error = exc.technical or exc.message
            await self.events.error(
                "bots.bot_service",
                "Проверка бота не пройдена.",
                explanation=exc.message,
                how_to_fix=exc.how_to_fix,
                actor=f"@{bot.username}" if bot.username else str(bot.telegram_id),
                operation="health_check",
                status="error",
            )
            result = BotHealthResult(
                bot_id=bot.id,
                ok=False,
                status=BotHealth.ERROR.value,
                message=exc.message,
                how_to_fix=exc.how_to_fix,
                username=bot.username,
                telegram_id=bot.telegram_id,
            )
        finally:
            await provider.close()
            bot.last_health_at = utcnow()
            await self.session.commit()
        return result

    # --- manager bot ---------------------------------------------------------
    async def ensure_manager_bot(self) -> Bot | None:
        """Register the manager bot from ``.env`` if configured and not present.

        Returns the manager bot, or ``None`` when no token is configured. Errors
        are logged as events but never raised, so application startup continues.
        """
        token = self.settings.manager_bot_token.get_secret_value()
        if not token:
            return None
        existing = await self.repo.get_manager()
        if existing is not None:
            if not existing.token_encrypted:
                existing.token_encrypted = seal_secret(token, self.settings)
                await self.session.flush()
            return existing
        try:
            return await self.add_bot(
                token, kind=BotKind.MANAGER, provider_name=self.settings.telegram_provider
            )
        except BotServiceError as exc:
            await self.events.warning(
                "bots.bot_service",
                "Управляющий бот из настроек не подключён.",
                explanation=exc.message,
                how_to_fix=exc.how_to_fix,
            )
            await self.session.commit()
            return None

    # --- Managed bots (official Bot API) -------------------------------------
    async def manager_link(self, username: str, name: str = "") -> str:
        """Build the official link a user opens to create a managed bot.

        Telegram creates the bot and delivers a ``managed_bot`` update to the
        manager bot, which then can fetch its token.
        """
        manager = await self.repo.get_manager()
        manager_username = manager.username if manager else ""
        return MANAGER_BOT_LINK.format(
            manager=manager_username, username=username, name=name or username
        )

    async def list_managed(self) -> list[Bot]:
        return await self.list_bots(kind=BotKind.MANAGED)

    async def register_managed_bot(
        self,
        user_id: int,
        *,
        username: str = "",
        title: str = "",
        owner_id: int | None = None,
        owner_username: str = "",
    ) -> Bot:
        """Record a managed bot (created via the manager link) in the inventory."""
        existing = await self.repo.get_by_telegram_id(user_id)
        if existing is not None:
            return existing
        bot = Bot(
            kind=BotKind.MANAGED,
            enabled=True,
            telegram_id=user_id,
            username=username,
            title=title or username,
            provider_name=self.settings.telegram_provider,
            owner_id=owner_id,
            owner_username=owner_username,
            health=BotHealth.UNKNOWN,
            health_message="Управляемый бот зарегистрирован. Получите токен для проверки.",
        )
        await self.repo.add(bot)
        await self.session.commit()
        return bot

    async def fetch_managed_bot_token(self, bot_id: str) -> Bot:
        """Fetch a managed bot's token via the manager bot and store it sealed.

        Uses the official ``getManagedBotToken`` method. Requires the manager
        bot to have "Bot Management Mode" enabled in @BotFather.
        """
        manager = await self.repo.get_manager()
        if manager is None:
            raise BotServiceError(
                "Управляющий бот не подключён.",
                how_to_fix="Сначала добавьте управляющего бота в разделе «Боты».",
                status_code=409,
            )
        bot = await self.repo.get(bot_id)
        if bot is None:
            raise BotServiceError("Бот не найден.", status_code=404)
        if bot.telegram_id is None:
            raise BotServiceError(
                "У этого бота неизвестен Telegram ID.",
                how_to_fix="Укажите Telegram ID управляемого бота.",
            )
        manager_token = self._token_of(manager)
        provider = self._provider_for(manager_token, manager.provider_name)
        try:
            token = await provider.get_managed_bot_token(bot.telegram_id)
        except TelegramProviderError as exc:
            bot.health = BotHealth.ERROR
            bot.health_message = exc.message
            bot.health_hint = exc.how_to_fix
            await self.session.commit()
            raise BotServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.close()

        bot.token_encrypted = seal_secret(token, self.settings)
        bot.health = BotHealth.UNKNOWN
        bot.health_message = "Токен получен. Выполните проверку."
        bot.health_hint = ""
        await self.session.flush()
        await self.events.info(
            "bots.bot_service",
            f"Получен токен управляемого бота @{bot.username or bot.telegram_id}.",
            operation="get_managed_bot_token",
            status="ok",
        )
        await self.session.commit()
        return bot

    async def replace_managed_bot_token(self, bot_id: str) -> Bot:
        """Revoke and regenerate a managed bot token via the manager bot."""
        manager = await self.repo.get_manager()
        if manager is None:
            raise BotServiceError(
                "Управляющий бот не подключён.",
                how_to_fix="Сначала добавьте управляющего бота.",
                status_code=409,
            )
        bot = await self.repo.get(bot_id)
        if bot is None or bot.telegram_id is None:
            raise BotServiceError("Бот не найден или неизвестен его Telegram ID.", status_code=404)
        manager_token = self._token_of(manager)
        provider = self._provider_for(manager_token, manager.provider_name)
        try:
            token = await provider.replace_managed_bot_token(bot.telegram_id)
        except TelegramProviderError as exc:
            raise BotServiceError(exc.message, how_to_fix=exc.how_to_fix) from exc
        finally:
            await provider.close()
        bot.token_encrypted = seal_secret(token, self.settings)
        await self.session.flush()
        await self.session.commit()
        return bot

    async def summary(self) -> dict[str, object]:
        """Aggregate counts for the Dashboard."""
        counts = await self.repo.count_by_kind()
        manager = await self.repo.get_manager()
        return {
            "total": sum(counts.values()),
            "by_kind": counts,
            "manager_connected": manager is not None,
            "manager_username": manager.username if manager else "",
            "manager_health": manager.health.value if manager else "unknown",
        }
