"""Telegram backup provider: deliver a backup to a chat via the manager bot.

Uses the official Bot API ``sendDocument`` through the existing provider
abstraction — no user session required. The destination is a chat id (usually the
owner's private chat with the manager bot). Credentials are not stored here: the
manager bot token already lives, sealed, in the bot inventory.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.models.bot import Bot
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.backup_backends.base import (
    ProviderInfo,
    ProviderStatus,
    UploadResult,
)

ProviderFactory = Callable[..., TelegramBotProvider]


class TelegramBackupProvider:
    name = "telegram"
    title = "Telegram (через бота)"

    def __init__(
        self,
        *,
        bot: Bot | None,
        config: dict[str, object],
        settings: Settings | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
    ) -> None:
        self._bot = bot
        self._config = config or {}
        self.settings = settings or get_settings()
        self._provider_factory = provider_factory

    @property
    def chat_id(self) -> str:
        return str(self._config.get("chat_id", "") or "").strip()

    def _provider(self) -> TelegramBotProvider | None:
        if self._bot is None or not self._bot.token_encrypted:
            return None
        try:
            token = open_secret(self._bot.token_encrypted, self.settings)
        except ValueError:
            return None
        return self._provider_factory(
            token, provider_name=self._bot.provider_name, settings=self.settings
        )

    def check(self) -> ProviderStatus:
        if not self.chat_id:
            return ProviderStatus(
                configured=False,
                reachable=False,
                message="Не указан чат для резервных копий.",
            )
        provider = self._provider()
        if provider is None:
            return ProviderStatus(
                configured=False,
                reachable=False,
                message="Управляющий бот недоступен для отправки копии.",
            )
        return ProviderStatus(
            configured=True,
            reachable=True,
            message="Чат для резервных копий настроен.",
            account_label=self.chat_id,
        )

    def upload(self, filename: str, content: bytes, *, caption: str = "") -> UploadResult:
        if not self.chat_id:
            return UploadResult(
                ok=False,
                message="Не указан чат для резервных копий.",
                how_to_fix="Укажите chat id в настройках места хранения.",
            )
        provider = self._provider()
        if provider is None:
            return UploadResult(
                ok=False,
                message="Управляющий бот недоступен.",
                how_to_fix="Проверьте управляющего бота в разделе «Боты».",
            )
        import asyncio

        async def _send() -> bool:
            try:
                return await provider.send_document(
                    self.chat_id, filename=filename, content=content, caption=caption
                )
            finally:
                await provider.close()

        try:
            ok = asyncio.run(_send())
        except TelegramProviderError as exc:
            return UploadResult(ok=False, message=exc.message, how_to_fix=exc.how_to_fix)
        except RuntimeError:
            # Already inside a running loop: run in a fresh thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                ok = pool.submit(lambda: asyncio.run(_send())).result()
        if not ok:
            return UploadResult(ok=False, message="Telegram не принял файл.")
        return UploadResult(ok=True, message="Копия отправлена в Telegram.", location=self.chat_id)


def info() -> ProviderInfo:
    return ProviderInfo(
        name="telegram",
        title="Telegram (через бота)",
        requires_credentials=False,
        config_fields=["chat_id"],
        help="Копия отправляется в указанный чат управляющим ботом. "
        "Сессии в такую копию не включаются.",
    )


def parse_config(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


INFO = info()


__all__ = ["INFO", "TelegramBackupProvider", "info", "parse_config"]
