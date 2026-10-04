"""Channel reaction capability service (product slice).

Telegram exposes the available reactions **per chat**, not globally. This
service asks a bot that is bound to the channel what reactions are actually
available and stores the answer so the Reaction Planner can intersect a profile
with reality instead of assuming a fixed emoji list works everywhere.

When the set cannot be determined, the service records ``unavailable`` (never a
guess) and the UI says "не удалось определить".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.base import utcnow
from backend.app.db.models.binding import FUNCTION_REACTIONS
from backend.app.db.models.bot import Bot
from backend.app.db.models.capability import (
    CAPABILITY_ERROR,
    CAPABILITY_OK,
    CAPABILITY_UNAVAILABLE,
    CAPABILITY_UNKNOWN,
    ChannelCapabilities,
)
from backend.app.db.repositories.bindings import BindingRepository
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.capabilities import CapabilityRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.events_service import EventsService

ProviderFactory = Callable[..., TelegramBotProvider]


@dataclass(slots=True)
class CapabilityView:
    channel_id: str
    status: str
    available: list[str]
    bot_reactions: list[str]
    reactions_limit: int
    paid_available: bool
    message: str
    last_checked: str = ""


class CapabilityService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = CapabilityRepository(session)
        self.bindings = BindingRepository(session)
        self.bots = BotRepository(session)
        self.channels = ChannelRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory

    async def get(self, channel_id: str) -> ChannelCapabilities | None:
        return await self.repo.get(channel_id)

    async def view(self, channel_id: str) -> CapabilityView:
        row = await self.repo.get(channel_id)
        if row is None:
            return CapabilityView(
                channel_id=channel_id,
                status=CAPABILITY_UNKNOWN,
                available=[],
                bot_reactions=[],
                reactions_limit=0,
                paid_available=False,
                message="Набор реакций канала ещё не проверялся.",
            )
        return self._to_view(row)

    async def probe(self, channel_id: str) -> CapabilityView:
        """Ask a bound bot what reactions the channel actually supports."""
        channel = await self.channels.get(channel_id)
        if channel is None:
            raise _error("Канал не найден.", status_code=404)
        row = await self.repo.upsert(channel_id)
        row.last_checked = utcnow()

        provider, _bot = await self._probe_provider(channel_id)
        if provider is None:
            row.status = CAPABILITY_UNAVAILABLE
            row.message = (
                "Чтобы узнать набор реакций канала, сначала подключите к нему бота "
                "(раздел «Боты» → «Подключить бота к каналу»)."
            )
            await self.session.flush()
            await self.session.commit()
            return self._to_view(row)

        target: int | str = channel.telegram_id or channel.reference or channel_id
        try:
            caps = await provider.get_reaction_capabilities(target)
        except TelegramProviderError as exc:
            row.status = CAPABILITY_ERROR
            row.message = exc.message
            await self.session.flush()
            await self.session.commit()
            return self._to_view(row)
        finally:
            await provider.close()

        if not caps.determined:
            row.status = CAPABILITY_UNAVAILABLE
            row.message = caps.message or "Не удалось определить набор реакций."
        else:
            row.status = CAPABILITY_OK
            row.available_reactions = json.dumps(caps.available)
            row.bot_reactions = json.dumps(caps.bot_compatible or caps.available)
            row.reactions_limit = int(caps.reactions_limit)
            row.paid_reactions_available = bool(caps.paid_available)
            row.message = "Набор реакций получен от Telegram."
        await self.session.flush()
        await self.events.info(
            "capabilities",
            f"Проверены реакции канала: {channel.title or channel.reference}.",
            explanation=row.message,
            operation="probe",
            status="ok" if row.status == CAPABILITY_OK else "warning",
        )
        await self.session.commit()
        return self._to_view(row)

    async def _probe_provider(
        self, channel_id: str
    ) -> tuple[TelegramBotProvider | None, Bot | None]:
        """Return a provider for any bot bound to this channel (bot-only probe)."""
        bindings = await self.bindings.list_for_channel(
            channel_id, function=FUNCTION_REACTIONS
        )
        for binding in bindings:
            bot = await self.bots.get(binding.bot_id)
            if bot is None or not bot.token_encrypted:
                continue
            try:
                token = open_secret(bot.token_encrypted, self.settings)
            except ValueError:
                continue
            provider = self._provider_factory(
                token, provider_name=bot.provider_name, settings=self.settings
            )
            return provider, bot
        return None, None

    def _to_view(self, row: ChannelCapabilities) -> CapabilityView:
        return CapabilityView(
            channel_id=row.channel_id,
            status=row.status,
            available=_load_list(row.available_reactions),
            bot_reactions=_load_list(row.bot_reactions),
            reactions_limit=row.reactions_limit,
            paid_available=row.paid_reactions_available,
            message=row.message,
            last_checked=row.last_checked.isoformat() if row.last_checked else "",
        )


def _load_list(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _error(message: str, *, status_code: int = 400) -> Exception:
    from backend.app.services.channel_service import ChannelServiceError

    return ChannelServiceError(message, status_code=status_code)


__all__ = ["CapabilityService", "CapabilityView"]
