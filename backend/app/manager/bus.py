"""Notification bus + routing (post-1.0 hardening; extended in v1.4).

A single in-process :class:`asyncio.Queue` carries lightweight notification
payloads from anywhere in the app (typically the central event log) to the
Notification Center, which delivers them out of band. Publishing is
non-blocking and never raises, so a notification problem can never break the
main task.

v1.4 adds the Notification Center categories, an explicit priority and a stable
de-duplication key so the center can route, postpone during quiet hours and
aggregate identical messages. The bus still holds no credentials and no
application state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

# Categories the owner can toggle independently (mirrors the UI).
CATEGORY_SYSTEM = "system"
CATEGORY_TELEGRAM = "telegram"
CATEGORY_ACCOUNTS = "accounts"
CATEGORY_CHANNELS = "channels"
CATEGORY_AUDIENCE = "audience"
CATEGORY_REACTIONS = "reactions"
CATEGORY_INVITES = "invites"
CATEGORY_CONTENT = "content"
CATEGORY_MEDIA = "media"
CATEGORY_AI = "ai"
CATEGORY_UPDATES = "updates"
CATEGORY_WORKERS = "workers"

CATEGORIES = (
    CATEGORY_SYSTEM,
    CATEGORY_TELEGRAM,
    CATEGORY_ACCOUNTS,
    CATEGORY_CHANNELS,
    CATEGORY_AUDIENCE,
    CATEGORY_REACTIONS,
    CATEGORY_INVITES,
    CATEGORY_CONTENT,
    CATEGORY_MEDIA,
    CATEGORY_AI,
    CATEGORY_UPDATES,
    CATEGORY_WORKERS,
)

CATEGORY_LABELS = {
    CATEGORY_SYSTEM: "Система",
    CATEGORY_TELEGRAM: "Telegram",
    CATEGORY_ACCOUNTS: "Аккаунты",
    CATEGORY_CHANNELS: "Каналы",
    CATEGORY_AUDIENCE: "Аудитория",
    CATEGORY_REACTIONS: "Реакции",
    CATEGORY_INVITES: "Приглашения",
    CATEGORY_CONTENT: "Контент",
    CATEGORY_MEDIA: "Медиа",
    CATEGORY_AI: "ИИ",
    CATEGORY_UPDATES: "Обновления",
    CATEGORY_WORKERS: "Узлы сети",
}

# Priorities (kept as plain strings on the bus to avoid a heavy import).
PRIORITY_INFO = "info"
PRIORITY_SUCCESS = "success"
PRIORITY_WARNING = "warning"
PRIORITY_ERROR = "error"
PRIORITY_CRITICAL = "critical"

PRIORITIES = (
    PRIORITY_INFO,
    PRIORITY_SUCCESS,
    PRIORITY_WARNING,
    PRIORITY_ERROR,
    PRIORITY_CRITICAL,
)

#: Priorities delivered immediately even during quiet hours.
URGENT_PRIORITIES = frozenset({PRIORITY_WARNING, PRIORITY_ERROR, PRIORITY_CRITICAL})

#: Map an event level (INFO/WARNING/ERROR/CRITICAL) to a notification priority.
LEVEL_TO_PRIORITY = {
    "INFO": PRIORITY_INFO,
    "SUCCESS": PRIORITY_SUCCESS,
    "WARNING": PRIORITY_WARNING,
    "ERROR": PRIORITY_ERROR,
    "CRITICAL": PRIORITY_CRITICAL,
}

# How an event module maps to a notification category. Used by the events hook.
MODULE_TO_CATEGORY = {
    "scheduler": CATEGORY_SYSTEM,
    "bots.bot_service": CATEGORY_TELEGRAM,
    "sessions.session_service": CATEGORY_ACCOUNTS,
    "reactions.reaction_service": CATEGORY_REACTIONS,
    "audience.audience_service": CATEGORY_AUDIENCE,
    "invites": CATEGORY_INVITES,
    "content": CATEGORY_CONTENT,
    "media": CATEGORY_MEDIA,
    "editorial": CATEGORY_CONTENT,
    "backup": CATEGORY_SYSTEM,
    "ai.classifier": CATEGORY_AI,
    "permissions": CATEGORY_TELEGRAM,
    "channels": CATEGORY_CHANNELS,
    "update": CATEGORY_UPDATES,
    "mesh": CATEGORY_WORKERS,
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
    priority: str = PRIORITY_INFO
    dedup_key: str = ""


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
    priority: str = "",
    dedup_key: str = "",
) -> None:
    """Convenience helper: publish without importing the bus everywhere.

    ``priority`` defaults to the priority implied by ``level``.
    """
    get_notification_bus().publish(
        Notification(
            category=category,
            event_key=event_key,
            message=message,
            level=level,
            how_to_fix=how_to_fix,
            priority=priority or LEVEL_TO_PRIORITY.get(level.upper(), PRIORITY_INFO),
            dedup_key=dedup_key,
        )
    )


__all__ = [
    "CATEGORIES",
    "CATEGORY_ACCOUNTS",
    "CATEGORY_AI",
    "CATEGORY_AUDIENCE",
    "CATEGORY_CHANNELS",
    "CATEGORY_CONTENT",
    "CATEGORY_INVITES",
    "CATEGORY_LABELS",
    "CATEGORY_MEDIA",
    "CATEGORY_REACTIONS",
    "CATEGORY_SYSTEM",
    "CATEGORY_TELEGRAM",
    "CATEGORY_UPDATES",
    "CATEGORY_WORKERS",
    "LEVEL_TO_PRIORITY",
    "MODULE_TO_CATEGORY",
    "PRIORITIES",
    "PRIORITY_CRITICAL",
    "PRIORITY_ERROR",
    "PRIORITY_INFO",
    "PRIORITY_SUCCESS",
    "PRIORITY_WARNING",
    "URGENT_PRIORITIES",
    "Notification",
    "NotificationBus",
    "category_for_module",
    "get_notification_bus",
    "publish",
    "reset_notification_bus",
]
