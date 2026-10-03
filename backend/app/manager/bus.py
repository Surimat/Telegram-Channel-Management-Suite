"""Notification bus + routing for the manager bot (post-1.0 hardening).

A single in-process :class:`asyncio.Queue` carries lightweight notification
payloads from anywhere in the app (typically the central event log) to the
manager-bot runtime, which delivers them out of band. Publishing is
non-blocking and never raises, so a notification problem can never break the
main task (a hard requirement of the hardening brief).

The bus is a small module-level singleton with an explicit reset hook so tests
get a clean instance. It holds no credentials and no application state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

# Categories the owner can toggle independently (mirrors the UI).
CATEGORY_SYSTEM = "system"
CATEGORY_TELEGRAM = "telegram"
CATEGORY_REACTIONS = "reactions"
CATEGORY_AUDIENCE = "audience"
CATEGORY_INVITES = "invites"
CATEGORY_AI = "ai"

CATEGORIES = (
    CATEGORY_SYSTEM,
    CATEGORY_TELEGRAM,
    CATEGORY_REACTIONS,
    CATEGORY_AUDIENCE,
    CATEGORY_INVITES,
    CATEGORY_AI,
)

CATEGORY_LABELS = {
    CATEGORY_SYSTEM: "Система",
    CATEGORY_TELEGRAM: "Telegram",
    CATEGORY_REACTIONS: "Реакции",
    CATEGORY_AUDIENCE: "Аудитория",
    CATEGORY_INVITES: "Приглашения",
    CATEGORY_AI: "ИИ",
}

# How an event module maps to a notification category. Used by the events hook.
MODULE_TO_CATEGORY = {
    "scheduler": CATEGORY_SYSTEM,
    "bots.bot_service": CATEGORY_TELEGRAM,
    "sessions.session_service": CATEGORY_TELEGRAM,
    "reactions.reaction_service": CATEGORY_REACTIONS,
    "audience.audience_service": CATEGORY_AUDIENCE,
    "invites": CATEGORY_INVITES,
    "backup": CATEGORY_SYSTEM,
    "ai.classifier": CATEGORY_AI,
    "permissions": CATEGORY_TELEGRAM,
}


def category_for_module(module: str) -> str:
    """Best-effort mapping of an event module to a notification category."""
    if module in MODULE_TO_CATEGORY:
        return MODULE_TO_CATEGORY[module]
    # Fall back to a prefix match so dotted/derived module names still route.
    for prefix, category in MODULE_TO_CATEGORY.items():
        if module.startswith(prefix.split(".")[0]):
            return category
    return CATEGORY_SYSTEM


@dataclass(slots=True)
class Notification:
    """One notification ready for delivery.

    ``event_key`` is a stable identifier (e.g. ``app.started``,
    ``session.auth_required``) used for routing and de-duplication. ``message``
    is the plain-language RU text; it must never contain secrets.
    """

    category: str
    event_key: str
    message: str
    level: str = "INFO"
    how_to_fix: str = ""


class NotificationBus:
    """A bounded, non-blocking queue of pending notifications."""

    def __init__(self, maxsize: int = 500) -> None:
        self._queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def publish(self, notification: Notification) -> None:
        """Enqueue a notification; never blocks and never raises."""
        try:
            self._queue.put_nowait(notification)
        except asyncio.QueueFull:
            self.dropped += 1
        except Exception:  # pragma: no cover - defensive
            self.dropped += 1

    def drain(self, limit: int = 20) -> list[Notification]:
        """Return up to ``limit`` pending notifications without blocking."""
        items: list[Notification] = []
        while len(items) < limit:
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    def empty(self) -> bool:
        return self._queue.empty()

    @property
    def pending(self) -> int:
        return self._queue.qsize()


_bus: NotificationBus | None = None


def get_notification_bus() -> NotificationBus:
    """Return the process-wide notification bus (created on first use)."""
    global _bus
    if _bus is None:
        _bus = NotificationBus()
    return _bus


def reset_notification_bus() -> None:
    """Drop the bus so a new one is created (used by tests)."""
    global _bus
    _bus = None


def publish(
    *,
    category: str,
    event_key: str,
    message: str,
    level: str = "INFO",
    how_to_fix: str = "",
) -> None:
    """Convenience helper: publish without importing the bus everywhere."""
    get_notification_bus().publish(
        Notification(
            category=category,
            event_key=event_key,
            message=message,
            level=level,
            how_to_fix=how_to_fix,
        )
    )


__all__ = [
    "CATEGORIES",
    "CATEGORY_AI",
    "CATEGORY_AUDIENCE",
    "CATEGORY_INVITES",
    "CATEGORY_LABELS",
    "CATEGORY_REACTIONS",
    "CATEGORY_SYSTEM",
    "CATEGORY_TELEGRAM",
    "MODULE_TO_CATEGORY",
    "Notification",
    "NotificationBus",
    "category_for_module",
    "get_notification_bus",
    "publish",
    "reset_notification_bus",
]
