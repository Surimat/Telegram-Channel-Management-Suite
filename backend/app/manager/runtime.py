"""Manager-bot runtime loop (post-1.0 hardening).

A single asyncio task that short-polls the manager bot for updates, dispatches
authorized commands, and forwards queued notifications. Design goals:

- **Durable, not a second scheduler.** The loop never blocks the durable job
  scheduler: each iteration is a short poll with an await point between ticks.
- **Graceful shutdown.** ``stop()`` cancels the task and closes the provider.
- **Offline tolerant.** If Telegram is unreachable the loop backs off and the
  application keeps working locally; nothing is raised into startup.
- **No secrets.** All Telegram access goes through the provider abstraction.
"""

from __future__ import annotations

import asyncio
import contextlib

from backend.app.core.logging import get_logger
from backend.app.db.session import session_scope
from backend.app.manager.service import ManagerBotService
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.types import MANAGER_ALLOWED_UPDATES

logger = get_logger(__name__)


class ManagerBotRuntime:
    """Polls the manager bot and delivers notifications while the app runs."""

    def __init__(self, *, poll_interval: float = 3.0) -> None:
        self.poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._offset: int | None = None
        self._backoff = poll_interval
        self.running = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="tcms-manager-bot")
        self.running = True
        logger.info("Manager bot runtime started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.running = False
        logger.info("Manager bot runtime stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
                self._backoff = self.poll_interval
            except TelegramProviderError as exc:
                # Telegram unavailable: back off but keep the app running.
                self._backoff = min(self._backoff * 2, 60.0)
                logger.info("Manager bot offline (%s); retry in %.0fs", exc.message, self._backoff)
            except Exception as exc:  # pragma: no cover - defensive
                self._backoff = min(self._backoff * 2, 60.0)
                logger.warning("Manager bot tick failed: %s", type(exc).__name__)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._backoff)

    async def _tick(self) -> None:
        """One poll cycle: flush notifications, handle updates."""
        async with session_scope() as session:
            service = ManagerBotService(session)
            provider = await service.manager_provider()
            # Notification Center: drain the bus, deliver, and release anything
            # postponed by quiet hours. Works with or without a manager bot
            # (the Windows-toast destination needs no Telegram provider).
            await self._flush_notifications(session, provider)
            if provider is None:
                # No manager bot configured: nothing else to do, but stay alive.
                return
            try:
                await service.register_commands(provider)
                updates = await provider.get_updates(
                    offset=self._offset,
                    timeout=0,
                    allowed_updates=list(MANAGER_ALLOWED_UPDATES),
                )
                for update in updates:
                    self._offset = max(self._offset or 0, update.update_id + 1)
                    if getattr(update, "kind", "") == "callback":
                        await self._handle_editorial_callback(session, provider, update)
                        continue
                    if getattr(update, "kind", "") == "managed_bot":
                        await self._handle_managed_bot(session, update)
                        continue
                    if getattr(update, "kind", "") == "channel_post":
                        await self._handle_channel_post(session, update)
                        continue
                    result = await service.handle_update(update)
                    chat_id = getattr(update, "chat_id", None)
                    if result.handled and result.reply and chat_id is not None:
                        with contextlib.suppress(TelegramProviderError):
                            await provider.send_message(chat_id, result.reply)
            finally:
                await provider.close()

    async def _handle_editorial_callback(self, session, provider, update) -> None:  # type: ignore[no-untyped-def]
        """Route an inline-button callback from an editorial card."""
        from backend.app.services.editorial_service import EditorialService

        chat_id = getattr(update, "chat_id", None)
        callback_id = getattr(update, "callback_query_id", "") or ""
        data = getattr(update, "callback_data", "") or ""
        if chat_id is None:
            return
        service = EditorialService(session)
        room = await service.room_for_group(int(chat_id))
        if room is None:
            if callback_id:
                with contextlib.suppress(TelegramProviderError):
                    await provider.answer_callback_query(callback_id, text="Карточка не найдена.")
            return
        result = await service.handle_callback(
            room_id=room.id,
            telegram_user_id=getattr(update, "user_id", None),
            username=getattr(update, "username", "") or "",
            callback_query_id=callback_id,
            data=data,
        )
        if callback_id:
            with contextlib.suppress(TelegramProviderError):
                await provider.answer_callback_query(
                    callback_id, text=result.answer or result.message
                )

    async def _handle_managed_bot(self, session, update) -> None:  # type: ignore[no-untyped-def]
        """Adopt a bot the owner created through a deep link (D-125).

        Telegram announces a bot created via the official managed-bot flow
        (``t.me/newbot``) with a ``managed_bot`` update. Routing it here closes
        the lifecycle loop: the bot is registered into its Bot Factory batch, the
        batch is settled once no candidate remains waiting, and the owner is
        notified — so a deep-link batch completes and is reported instead of
        silently staying "created by hand, never registered". A bot with an
        unknown username is ignored, never searched for or imported (D-070); the
        same update delivered twice is a no-op.
        """
        from backend.app.services.bot_lifecycle import BotLifecycleService

        user_id = getattr(update, "managed_bot_user_id", None)
        username = getattr(update, "managed_bot_username", "") or ""
        if not user_id or not username:
            return
        title = getattr(update, "managed_bot_first_name", "") or ""
        await BotLifecycleService(session).adopt_managed_bot(
            username=username, telegram_id=int(user_id), title=title
        )

    async def _handle_channel_post(self, session, update) -> None:  # type: ignore[no-untyped-def]
        """Feed a real channel post into the Reaction Manager (D-130).

        The manager bot is a channel administrator, so Telegram delivers each new
        post as a ``channel_post`` update carrying the real numeric chat id and
        message id. The post is stored and its reactions are planned; an edited
        post refreshes the stored text but is never re-planned, and a redelivered
        update is a no-op (the service deduplicates by chat id + message id).
        """
        from backend.app.services.reaction_service import ReactionService

        chat_id = getattr(update, "channel_post_chat_id", None)
        message_id = getattr(update, "channel_post_message_id", None)
        if chat_id is None or message_id is None:
            return
        try:
            await ReactionService(session).ingest_channel_post(
                chat_id=int(chat_id),
                message_id=int(message_id),
                text=getattr(update, "channel_post_text", "") or "",
                chat_username=getattr(update, "channel_post_chat_username", "") or "",
                edited=bool(getattr(update, "channel_post_edited", False)),
            )
        except Exception as exc:  # a bad post must not stop the poll loop
            logger.warning(
                "Channel post ingestion failed: %s", type(exc).__name__
            )

    async def _flush_notifications(self, session, provider) -> None:  # type: ignore[no-untyped-def]
        """Route queued notifications through the Notification Center."""
        from backend.app.services.notification_service import NotificationCenterService

        async def _owner_provider():  # type: ignore[no-untyped-def]
            return provider

        center = NotificationCenterService(
            session,
            resolve_owner_provider=_owner_provider,
            resolve_group_provider=_owner_provider,
        )
        try:
            await center.flush_pending()
            await center.deliver_due_postponed()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Notification flush failed: %s", type(exc).__name__)


__all__ = ["ManagerBotRuntime"]
