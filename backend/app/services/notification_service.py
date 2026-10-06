"""Notification Center service (v1.4).

Turns the in-process notification bus into a durable, inspectable, routable
center:

* **Destinations** — Telegram owner DM (the primary one), a Telegram group, an
  optional Windows toast, or none. A dedicated notification bot can be used
  instead of the manager bot; both go through the same bus and the same service.
* **Categories** — system / telegram / accounts / channels / audience / reactions
  / invites / content / media / ai / updates / workers, each independently on/off.
* **Priority** — info / success / warning / error / critical.
* **Quiet hours** — info & success are postponed; warning+ are delivered at once.
* **Anti-spam aggregation** — many identical notifications in a short window
  become one ("за минуту произошло N одинаковых ошибок").
* **History** — every notification and every delivery attempt is stored (no
  secrets), so the owner can see what failed.

Delivery never raises into the caller: a Telegram/Toast problem is recorded as a
failed delivery, never a crash.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.db.base import utcnow
from backend.app.db.models.notification import (
    PRIORITY_ORDER,
    URGENT_PRIORITIES,
    NotificationDelivery,
    NotificationDestination,
    NotificationPriority,
    NotificationRecord,
    NotificationStatus,
)
from backend.app.db.repositories.notifications import (
    NotificationDeliveryRepository,
    NotificationRepository,
)
from backend.app.manager.bus import (
    CATEGORIES,
    LEVEL_TO_PRIORITY,
    Notification,
    get_notification_bus,
)
from backend.app.providers.base import TelegramBotProvider
from backend.app.services.notification_destinations import (
    NotificationDestinationProvider,
    TelegramDestination,
    WindowsToastDestination,
)
from backend.app.services.settings_service import SettingsService

logger = get_logger(__name__)

MODULE = "notifications"

#: Default routing per category. The owner can change it in the UI.
DEFAULT_ROUTING: dict[str, list[str]] = {
    "system": [NotificationDestination.TELEGRAM_OWNER],
    "telegram": [NotificationDestination.TELEGRAM_OWNER],
    "accounts": [NotificationDestination.TELEGRAM_OWNER],
    "channels": [NotificationDestination.TELEGRAM_OWNER],
    "audience": [NotificationDestination.TELEGRAM_OWNER],
    "reactions": [NotificationDestination.TELEGRAM_OWNER],
    "invites": [NotificationDestination.TELEGRAM_OWNER],
    "content": [NotificationDestination.TELEGRAM_OWNER, NotificationDestination.TELEGRAM_GROUP],
    "media": [NotificationDestination.TELEGRAM_OWNER],
    "ai": [NotificationDestination.TELEGRAM_OWNER],
    "updates": [NotificationDestination.TELEGRAM_OWNER],
    "workers": [NotificationDestination.TELEGRAM_OWNER],
}

#: Window for anti-spam aggregation of identical notifications.
AGGREGATION_WINDOW_SECONDS = 60

#: A ``resolve`` callable returns a bot provider for a destination, or ``None``.
ProviderResolver = Callable[[], Awaitable[TelegramBotProvider | None]]


@dataclass(slots=True)
class NotificationSettings:
    enabled: bool
    categories: dict[str, bool]
    routing: dict[str, list[str]]
    quiet_hours_enabled: bool
    quiet_hours_start: int
    quiet_hours_end: int
    quiet_hours_tz: str
    aggregation_enabled: bool


class NotificationCenterService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        resolve_owner_provider: ProviderResolver | None = None,
        resolve_group_provider: ProviderResolver | None = None,
        toast: NotificationDestinationProvider | None = None,
    ) -> None:
        self.session = session
        self.app_settings = settings or get_settings()
        self.records = NotificationRepository(session)
        self.deliveries = NotificationDeliveryRepository(session)
        self._resolve_owner = resolve_owner_provider
        self._resolve_group = resolve_group_provider
        self._toast = toast

    # --- settings ------------------------------------------------------------
    async def load_settings(self) -> NotificationSettings:
        svc = SettingsService(self.session)
        enabled = bool(await svc.get_typed("notifications_enabled", True))
        categories = {c: bool(await svc.get_typed(f"notifications_{c}", True)) for c in CATEGORIES}
        routing_raw = await svc.get_typed("notification_routing", {})
        routing = _normalize_routing(routing_raw)
        return NotificationSettings(
            enabled=enabled,
            categories=categories,
            routing=routing,
            quiet_hours_enabled=bool(await svc.get_typed("notification_quiet_enabled", False)),
            quiet_hours_start=int(await svc.get_typed("notification_quiet_start", 23) or 23),
            quiet_hours_end=int(await svc.get_typed("notification_quiet_end", 8) or 8),
            quiet_hours_tz=str(await svc.get_typed("notification_quiet_tz", "UTC") or "UTC"),
            aggregation_enabled=bool(await svc.get_typed("notification_aggregation", True)),
        )

    async def update_settings(
        self,
        *,
        enabled: bool | None = None,
        categories: dict[str, bool] | None = None,
        routing: dict[str, list[str]] | None = None,
        quiet_hours_enabled: bool | None = None,
        quiet_hours_start: int | None = None,
        quiet_hours_end: int | None = None,
        quiet_hours_tz: str | None = None,
        aggregation_enabled: bool | None = None,
    ) -> NotificationSettings:
        svc = SettingsService(self.session)
        if enabled is not None:
            await svc.set("notifications_enabled", bool(enabled))
        for name, value in (categories or {}).items():
            if name in CATEGORIES:
                await svc.set(f"notifications_{name}", bool(value))
        if routing is not None:
            await svc.set("notification_routing", _normalize_routing(routing))
        if quiet_hours_enabled is not None:
            await svc.set("notification_quiet_enabled", bool(quiet_hours_enabled))
        if quiet_hours_start is not None:
            await svc.set("notification_quiet_start", max(0, min(23, int(quiet_hours_start))))
        if quiet_hours_end is not None:
            await svc.set("notification_quiet_end", max(0, min(23, int(quiet_hours_end))))
        if quiet_hours_tz is not None:
            await svc.set("notification_quiet_tz", (quiet_hours_tz or "UTC").strip())
        if aggregation_enabled is not None:
            await svc.set("notification_aggregation", bool(aggregation_enabled))
        await self.session.flush()
        return await self.load_settings()

    # --- routing / quiet hours ----------------------------------------------
    def destinations_for(self, cfg: NotificationSettings, category: str) -> list[str]:
        return list(cfg.routing.get(category, DEFAULT_ROUTING.get(category, [])))

    def in_quiet_hours(self, cfg: NotificationSettings, *, now: datetime | None = None) -> bool:
        if not cfg.quiet_hours_enabled:
            return False
        try:
            tz = ZoneInfo(cfg.quiet_hours_tz or "UTC")
        except Exception:
            tz = UTC
        hour = (now or utcnow()).astimezone(tz).hour
        start, end = cfg.quiet_hours_start, cfg.quiet_hours_end
        if start == end:
            return False
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _quiet_until(self, cfg: NotificationSettings, *, now: datetime | None = None) -> datetime:
        """The next moment quiet hours end (when a postponed item becomes due)."""
        try:
            tz = ZoneInfo(cfg.quiet_hours_tz or "UTC")
        except Exception:
            tz = UTC
        current = (now or utcnow()).astimezone(tz)
        target = current.replace(
            hour=cfg.quiet_hours_end, minute=0, second=0, microsecond=0
        )
        if target <= current:
            target = target + timedelta(days=1)
        return target.astimezone(UTC)

    # --- submission ----------------------------------------------------------
    async def submit(
        self, notification: Notification, *, now: datetime | None = None
    ) -> NotificationRecord:
        """Record and (if allowed) deliver one notification.

        Applies category toggles, quiet hours and anti-spam aggregation. Never
        raises on a delivery problem.
        """
        cfg = await self.load_settings()
        priority = _priority_of(notification)
        dedup_key = notification.dedup_key or f"{notification.category}:{notification.event_key}"
        record = NotificationRecord(
            category=notification.category,
            priority=priority,
            destination=NotificationDestination.NONE,
            event_key=notification.event_key,
            dedup_key=dedup_key,
            source_module=notification.category,
            title="",
            message=notification.message,
            how_to_fix=notification.how_to_fix,
            status=NotificationStatus.PENDING,
        )

        if not cfg.enabled or not cfg.categories.get(notification.category, True):
            record.status = NotificationStatus.SKIPPED
            await self.records.add(record)
            await self.session.commit()
            return record

        # Anti-spam aggregation: merge identical notifications in a short window.
        if cfg.aggregation_enabled and priority not in URGENT_PRIORITIES:
            window_start = (now or utcnow()) - timedelta(seconds=AGGREGATION_WINDOW_SECONDS)
            existing = await self.records.recent_by_dedup(dedup_key, window_start)
            if existing is not None and existing.status in (
                NotificationStatus.SENT,
                NotificationStatus.PENDING,
                NotificationStatus.POSTPONED,
            ):
                existing.aggregate_count += 1
                existing.message = _aggregate_message(
                    existing.message, existing.aggregate_count
                )
                record.status = NotificationStatus.AGGREGATED
                await self.records.add(record)
                await self.session.commit()
                return existing

        destinations = self.destinations_for(cfg, notification.category)
        if not destinations or NotificationDestination.NONE in destinations:
            record.status = NotificationStatus.SKIPPED
            await self.records.add(record)
            await self.session.commit()
            return record

        # Quiet hours: postpone non-urgent notifications.
        if self.in_quiet_hours(cfg, now=now) and priority not in URGENT_PRIORITIES:
            record.status = NotificationStatus.POSTPONED
            record.postponed_until = self._quiet_until(cfg, now=now)
            await self.records.add(record)
            await self.session.commit()
            return record

        await self.records.add(record)
        await self.session.flush()
        await self._deliver(record, destinations)
        await self.session.commit()
        return record

    async def flush_pending(self, limit: int = 50) -> int:
        """Drain the in-process bus and submit everything queued."""
        items = get_notification_bus().drain(limit=limit)
        for notification in items:
            await self.submit(notification)
        return len(items)

    async def deliver_due_postponed(self, *, now: datetime | None = None) -> int:
        """Deliver notifications postponed during quiet hours once due."""
        due = await self.records.due_postponed(now or utcnow())
        cfg = await self.load_settings()
        sent = 0
        for record in due:
            if not cfg.enabled or not cfg.categories.get(record.category, True):
                record.status = NotificationStatus.SKIPPED
                continue
            destinations = self.destinations_for(cfg, record.category)
            await self._deliver(record, destinations)
            sent += 1
        if due:
            await self.session.commit()
        return sent

    # --- delivery ------------------------------------------------------------
    async def _deliver(
        self, record: NotificationRecord, destinations: list[str]
    ) -> None:
        record.destination = _primary_destination(destinations)
        delivered_any = False
        last_error = ""
        for destination in destinations:
            if destination == NotificationDestination.NONE:
                continue
            provider = await self._destination_for(destination)
            if provider is None:
                await self._record_delivery(
                    record,
                    destination,
                    NotificationStatus.SKIPPED,
                    "Нет подключённого бота для этого получателя.",
                )
                continue
            result = await provider.deliver(
                _render(record), title=f"[{_category_label(record.category)}]"
            )
            if result.ok:
                delivered_any = True
                await self._record_delivery(record, destination, NotificationStatus.SENT)
            else:
                last_error = result.message
                status = (
                    NotificationStatus.SKIPPED if result.unavailable else NotificationStatus.FAILED
                )
                await self._record_delivery(record, destination, status, result.message)
        record.status = NotificationStatus.SENT if delivered_any else NotificationStatus.FAILED
        record.error = "" if delivered_any else last_error
        if delivered_any:
            record.delivered_at = utcnow()

    async def _record_delivery(
        self,
        record: NotificationRecord,
        destination: str,
        status: NotificationStatus,
        error: str = "",
    ) -> None:
        await self.deliveries.add(
            NotificationDelivery(
                notification_id=record.id,
                destination=_destination_enum(destination),
                status=status,
                error=error,
                attempts=1,
                sent_at=utcnow() if status == NotificationStatus.SENT else None,
            )
        )

    async def _destination_for(self, destination: str) -> NotificationDestinationProvider | None:
        if destination == NotificationDestination.WINDOWS_TOAST:
            return self._toast or WindowsToastDestination()
        if destination == NotificationDestination.TELEGRAM_OWNER:
            provider = await self._resolve_owner() if self._resolve_owner else None
            if provider is None:
                return None
            owner_id = await self._owner_chat_id()
            if owner_id is None:
                return None
            return TelegramDestination(provider, owner_id, own_provider=False)
        if destination == NotificationDestination.TELEGRAM_GROUP:
            provider = await self._resolve_group() if self._resolve_group else None
            if provider is None:
                return None
            group_id = await self._group_chat_id()
            if group_id is None:
                return None
            return TelegramDestination(provider, group_id, own_provider=False)
        return None

    async def _owner_chat_id(self) -> int | None:
        admins = self.app_settings.admin_ids
        return admins[0] if admins else None

    async def _group_chat_id(self) -> int | None:
        svc = SettingsService(self.session)
        raw = await svc.get_typed("notification_group_chat_id", 0)
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return value or None

    # --- history / dashboard -------------------------------------------------
    async def history(
        self,
        *,
        category: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[NotificationRecord], int]:
        status_enum = None
        if status:
            try:
                status_enum = NotificationStatus(status)
            except ValueError:
                status_enum = None
        return await self.records.list(
            category=category,
            priority=priority,
            status=status_enum,
            limit=limit,
            offset=offset,
        )

    async def failed_deliveries(self, limit: int = 50) -> list[NotificationDelivery]:
        return await self.deliveries.failed(limit=limit)

    async def dashboard(self) -> dict[str, object]:
        cfg = await self.load_settings()
        return {
            "enabled": cfg.enabled,
            "categories": cfg.categories,
            "routing": cfg.routing,
            "quiet_hours_enabled": cfg.quiet_hours_enabled,
            "quiet_hours_start": cfg.quiet_hours_start,
            "quiet_hours_end": cfg.quiet_hours_end,
            "quiet_hours_tz": cfg.quiet_hours_tz,
            "aggregation_enabled": cfg.aggregation_enabled,
            "status_counts": await self.records.status_counts(),
            "category_counts": await self.records.category_counts(),
            "pending": get_notification_bus().pending,
            "failed": len(await self.failed_deliveries(limit=100)),
        }

    async def send_test(
        self, *, category: str = "system", priority: str = "info"
    ) -> NotificationRecord:
        """Send a visible test notification (so the owner can verify routing)."""
        prio = _priority_enum(priority)
        return await self.submit(
            Notification(
                category=category if category in CATEGORIES else "system",
                event_key="notification.test",
                message="Это тестовое уведомление. Если вы его видите — уведомления настроены.",
                how_to_fix="",
                level="INFO",
                priority=str(prio),
                dedup_key=f"test:{utcnow().timestamp()}",
            )
        )

    async def mark_read(self, notification_id: str) -> NotificationRecord | None:
        record = await self.records.get(notification_id)
        if record is None:
            return None
        record.read = True
        await self.session.commit()
        return record


# --- helpers -----------------------------------------------------------------


def _priority_of(notification: Notification) -> NotificationPriority:
    if notification.priority:
        return _priority_enum(notification.priority)
    return _priority_enum(LEVEL_TO_PRIORITY.get(notification.level.upper(), "info"))


def _priority_enum(value: str) -> NotificationPriority:
    try:
        return NotificationPriority(str(value).lower())
    except ValueError:
        return NotificationPriority.INFO


def _destination_enum(value: str) -> NotificationDestination:
    try:
        return NotificationDestination(str(value))
    except ValueError:
        return NotificationDestination.NONE


def _primary_destination(destinations: list[str]) -> NotificationDestination:
    for value in destinations:
        if value != NotificationDestination.NONE:
            return _destination_enum(value)
    return NotificationDestination.NONE


def _category_label(category: str) -> str:
    from backend.app.manager.bus import CATEGORY_LABELS

    return CATEGORY_LABELS.get(category, category)


def _render(record: NotificationRecord) -> str:
    lines = [record.message]
    if record.how_to_fix:
        lines.append(f"Что сделать: {record.how_to_fix}")
    if record.aggregate_count > 1:
        lines.append(f"Всего похожих уведомлений: {record.aggregate_count}.")
    return "\n".join(lines)


def _aggregate_message(message: str, count: int) -> str:
    base = message.split("\n")[0]
    return (
        f"{base}\n"
        f"За последнюю минуту произошло {count} похожих событий."
    )


def _normalize_routing(raw: object) -> dict[str, list[str]]:
    routing = {c: list(DEFAULT_ROUTING.get(c, [])) for c in CATEGORIES}
    if not isinstance(raw, dict):
        return routing
    for key, value in raw.items():
        if key not in CATEGORIES:
            continue
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = [str(v) for v in value]
        else:
            continue
        valid = [v for v in values if v in {d.value for d in NotificationDestination}]
        routing[key] = valid
    return routing


def priority_rank(value: str) -> int:
    return PRIORITY_ORDER.get(_priority_enum(value), 0)


def routing_json(routing: dict[str, list[str]]) -> str:
    return json.dumps(routing, ensure_ascii=False)


__all__ = [
    "AGGREGATION_WINDOW_SECONDS",
    "DEFAULT_ROUTING",
    "MODULE",
    "NotificationCenterService",
    "NotificationSettings",
    "priority_rank",
    "routing_json",
]
