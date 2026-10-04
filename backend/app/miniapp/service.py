"""Mini App authentication service.

Ties :mod:`backend.app.miniapp.auth` and :mod:`backend.app.miniapp.sessions`
together with the manager bot's token (the only secret Telegram signs with).
The token is read from the sealed DB row and never leaves this module.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.repositories.bots import BotRepository
from backend.app.miniapp.auth import MiniAppAuthError, MiniAppUser, verify_init_data
from backend.app.miniapp.sessions import MiniAppSession, issue_session, verify_session
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.events_service import EventsService


@dataclass
class MiniAppStatus:
    enabled: bool
    available: bool
    bot_username: str
    reason: str
    how_to_fix: str
    public_url: str = ""


@dataclass
class MiniAppSetupResult:
    ok: bool
    message: str
    how_to_fix: str = ""


class MiniAppService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        provider_factory=build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.bots = BotRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory

    async def _manager_token(self) -> str:
        manager = await self.bots.get_manager()
        if manager is None or not manager.token_encrypted:
            return ""
        try:
            return open_secret(manager.token_encrypted, self.settings)
        except ValueError:
            return ""

    async def _enabled(self) -> bool:
        """Effective flag: a DB setting (editable in the UI) overrides the env."""
        from backend.app.services.settings_service import SettingsService

        value = await SettingsService(self.session).get_typed(
            "miniapp_enabled", self.settings.miniapp_enabled
        )
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    async def _public_url(self) -> str:
        from backend.app.services.settings_service import SettingsService

        value = await SettingsService(self.session).get_typed(
            "miniapp_public_url", self.settings.miniapp_public_url
        )
        return str(value or "").strip()

    async def status(self) -> MiniAppStatus:
        """Describe whether the Mini App can be used, in plain language."""
        if not await self._enabled():
            return MiniAppStatus(
                enabled=False,
                available=False,
                bot_username="",
                reason="Мини-приложение выключено.",
                how_to_fix="Включите «Мини-приложение» в разделе «Настройки», "
                "если хотите открывать систему прямо из Telegram.",
            )
        manager = await self.bots.get_manager()
        token = await self._manager_token()
        if manager is None or not token:
            return MiniAppStatus(
                enabled=True,
                available=False,
                bot_username="",
                reason="Управляющий бот не подключён, вход из Telegram невозможен.",
                how_to_fix="Подключите управляющего бота в разделе «Боты».",
            )
        return MiniAppStatus(
            enabled=True,
            available=True,
            bot_username=manager.username or "",
            reason="Мини-приложение готово к работе.",
            how_to_fix="",
            public_url=await self._public_url(),
        )

    def _is_admin(self, user: MiniAppUser) -> bool:
        admins = self.settings.admin_ids
        return bool(admins) and user.id in admins

    async def authenticate(self, init_data: str) -> tuple[str, MiniAppUser, bool]:
        """Verify ``initData`` and return ``(token, user, is_admin)``.

        Raises :class:`MiniAppAuthError` when the payload is untrusted or the
        caller is not an allowed owner.
        """
        token_secret = await self._manager_token()
        user = verify_init_data(
            init_data,
            token_secret,
            max_age=self.settings.miniapp_initdata_max_age,
        )
        is_admin = self._is_admin(user)
        # When the owner list is configured, only listed Telegram ids may sign in.
        if self.settings.admin_ids and not is_admin:
            await self.events.warning(
                "miniapp.service",
                "Отклонён вход в мини-приложение.",
                explanation="Telegram-пользователь не входит в список владельцев.",
                how_to_fix="Добавьте его ID в «Владельцы мини-приложения» в настройках.",
            )
            await self.session.commit()
            raise MiniAppAuthError(
                "not_allowed",
                "Этот Telegram-аккаунт не является владельцем системы.",
                hint="Войдите с разрешённого аккаунта или добавьте его ID в настройках.",
            )
        signed = issue_session(user.id, is_admin=is_admin, settings=self.settings)
        return signed, user, is_admin

    def resolve_session(self, token: str) -> MiniAppSession:
        return verify_session(token, settings=self.settings)

    async def setup(self, public_url: str) -> MiniAppSetupResult:
        """Register the Mini App menu button with Telegram.

        Validates that a public HTTPS URL is set and that the manager bot is
        connected, then points the bot's chat menu button at that URL so owners
        can open the suite straight from Telegram. Never bypasses Telegram: any
        provider error is reported in plain language (D-049).
        """
        url = (public_url or "").strip().rstrip("/")
        if not url:
            url = (await self._public_url()).rstrip("/")
        parsed = urlparse(url)
        if not url:
            return MiniAppSetupResult(
                ok=False,
                message="Не указан публичный адрес приложения.",
                how_to_fix="Укажите адрес вида https://ваш-домен (нужен HTTPS) "
                "и сохраните настройку.",
            )
        if parsed.scheme != "https" or not parsed.netloc:
            return MiniAppSetupResult(
                ok=False,
                message="Публичный адрес должен начинаться с https://.",
                how_to_fix="Telegram открывает мини-приложения только по HTTPS. "
                "Укажите адрес вида https://ваш-домен.",
            )

        manager = await self.bots.get_manager()
        token = await self._manager_token()
        if manager is None or not token:
            return MiniAppSetupResult(
                ok=False,
                message="Управляющий бот не подключён.",
                how_to_fix="Подключите управляющего бота в разделе «Боты», затем "
                "повторите настройку.",
            )

        provider = self._provider_factory(
            token, provider_name=manager.provider_name, settings=self.settings
        )
        try:
            await provider.set_menu_button("Открыть панель", url)
        except TelegramProviderError as exc:
            await self.events.error(
                "miniapp.service",
                "Не удалось зарегистрировать мини-приложение.",
                explanation=exc.message,
                how_to_fix=exc.how_to_fix
                or "Проверьте, что адрес доступен из интернета по HTTPS.",
            )
            await self.session.commit()
            return MiniAppSetupResult(
                ok=False,
                message="Telegram отклонил настройку мини-приложения.",
                how_to_fix=exc.how_to_fix
                or "Проверьте, что адрес доступен из интернета по HTTPS.",
            )
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    await close()

        from backend.app.services.settings_service import SettingsService

        await SettingsService(self.session).set("miniapp_public_url", url)
        await SettingsService(self.session).set("miniapp_enabled", True)
        await self.events.info(
            "miniapp.service",
            "Мини-приложение подключено.",
            explanation="Кнопка меню бота открывает панель управления.",
        )
        await self.session.commit()
        return MiniAppSetupResult(
            ok=True,
            message="Готово: мини-приложение подключено. Откройте бота в Telegram "
            "и нажмите кнопку меню.",
        )
