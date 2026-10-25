"""Notification destinations (v1.4 Notification Center).

A destination is a small adapter that delivers one already-rendered message. The
Notification Center decides *what* to send and *where* (routing); a destination
only knows *how* to deliver to one channel:

* :class:`TelegramDestination` — send a text through a
  :class:`~backend.app.providers.base.TelegramBotProvider` to a fixed chat id
  (the owner's DM or a notification group).
* :class:`WindowsToastDestination` — a best-effort Windows toast. When no toast
  library is available it honestly reports ``available=False`` and never breaks
  the app.

No destination ever logs or returns a token; the provider already seals secrets.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.app.core.logging import get_logger
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError

logger = get_logger(__name__)


@dataclass(slots=True)
class NotificationDeliveryResult:
    """Outcome of one notification delivery attempt."""

    ok: bool
    message: str = ""
    unavailable: bool = False


@runtime_checkable
class NotificationDestinationProvider(Protocol):
    """Delivers a rendered notification to one destination."""

    async def deliver(self, text: str, *, title: str = "") -> NotificationDeliveryResult:
        ...


class TelegramDestination:
    """Deliver to a fixed Telegram chat through a bot provider."""

    def __init__(
        self,
        provider: TelegramBotProvider,
        chat_id: int,
        *,
        own_provider: bool = True,
    ) -> None:
        self.provider = provider
        self.chat_id = chat_id
        self._own_provider = own_provider

    async def deliver(self, text: str, *, title: str = "") -> NotificationDeliveryResult:
        body = f"{title}\n\n{text}".strip() if title else text
        try:
            await self.provider.send_message(self.chat_id, body)
            return NotificationDeliveryResult(ok=True)
        except TelegramProviderError as exc:
            return NotificationDeliveryResult(ok=False, message=exc.message)
        except Exception as exc:  # pragma: no cover - defensive
            return NotificationDeliveryResult(ok=False, message=type(exc).__name__)

    async def close(self) -> None:
        if self._own_provider:
            with contextlib.suppress(Exception):
                await self.provider.close()


def toast_available() -> bool:
    """True when a Windows toast backend can be imported (never required)."""
    import importlib.util

    return any(
        importlib.util.find_spec(name) is not None
        for name in ("winotify", "win10toast", "plyer")
    )


class WindowsToastDestination:
    """Best-effort Windows toast; unavailable on other platforms or without a lib.

    The notification never fails the app: when no toast backend exists the
    delivery is reported as ``unavailable`` so the center can record it and move
    on (the Telegram destination still delivers).
    """

    def __init__(self) -> None:
        self._available = toast_available()

    @property
    def available(self) -> bool:
        return self._available

    async def deliver(self, text: str, *, title: str = "") -> NotificationDeliveryResult:
        if not self._available:
            return NotificationDeliveryResult(
                ok=False,
                unavailable=True,
                message="Системные уведомления Windows недоступны на этой системе.",
            )
        return await asyncio.to_thread(self._deliver_sync, title or "TCMS", text)

    def _deliver_sync(  # pragma: no cover
        self, title: str, text: str
    ) -> NotificationDeliveryResult:
        try:
            import importlib

            if importlib.util.find_spec("winotify") is not None:  # type: ignore[attr-defined]
                from winotify import Notification, audio  # type: ignore[import-not-found]

                toast = Notification(app_id="TCMS", title=title, msg=text)
                toast.set_audio(audio.Default, loop=False)
                toast.show()
                return NotificationDeliveryResult(ok=True)
            if importlib.util.find_spec("win10toast") is not None:  # type: ignore[attr-defined]
                from win10toast import ToastNotifier  # type: ignore[import-not-found]

                ToastNotifier().show_toast(title, text, duration=5, threaded=True)
                return NotificationDeliveryResult(ok=True)
            if importlib.util.find_spec("plyer") is not None:  # type: ignore[attr-defined]
                from plyer import notification  # type: ignore[import-not-found]

                notification.notify(title=title, message=text, timeout=5)
                return NotificationDeliveryResult(ok=True)
        except Exception as exc:
            return NotificationDeliveryResult(ok=False, message=type(exc).__name__)
        return NotificationDeliveryResult(ok=False, unavailable=True)


__all__ = [
    "NotificationDeliveryResult",
    "NotificationDestinationProvider",
    "TelegramDestination",
    "WindowsToastDestination",
    "toast_available",
]
