"""Editorial Workspace service (v1.4: редакционная комната).

A linked Telegram forum supergroup where the owner, editors and moderators work
on the same publication queue the Web UI shows. The suite owns the queue and the
order; Telegram topics only mirror it as one card per content item.

Design notes:

* **Honest rights.** A room only reaches ``ready`` after Telegram confirmed the
  bot is present and can send messages; a missing right stays ``needs_rights``.
* **Roles by numeric id.** Authorization uses Telegram *user ids* only; a
  username is never an identity.
* **The suite owns the order.** Cards are never moved between topics (a bot
  cannot reliably do that); a status change posts a fresh card into the target
  topic and the ``order_index`` lives in the database.
* **No secrets.** Telegram access goes through the provider abstraction; the
  service never logs or returns tokens or session contents.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import open_secret
from backend.app.db.base import utcnow
from backend.app.db.models.editorial import (
    DEFAULT_TOPICS,
    ROLE_ACTIONS,
    ROLE_TITLES,
    STATUS_TITLES,
    EditorialAuditEntry,
    EditorialItem,
    EditorialMember,
    EditorialRole,
    EditorialRoom,
    EditorialStatus,
    RoomStatus,
)
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.editorial import (
    EditorialAuditRepository,
    EditorialItemRepository,
    EditorialMemberRepository,
    EditorialRoomRepository,
)
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.services.events_service import EventsService

logger = get_logger(__name__)

MODULE = "editorial"

#: Telegram's numeric limit for ``callback_data`` in bytes.
CALLBACK_LIMIT = 64
#: Prefix for every editorial callback payload.
CALLBACK_PREFIX = "ed"

#: A publish handler: ``(content_item_id, channel_id) -> (ok, message)``.
PublishHandler = Callable[[str, str], Awaitable[tuple[bool, str]]]

#: Which status each button moves an item to (``publish`` is special).
_ACTION_TARGET = {
    "edit": EditorialStatus.EDITING,
    "review": EditorialStatus.REVIEW,
    "approve": EditorialStatus.APPROVED,
    "schedule": EditorialStatus.SCHEDULED,
    "reject": EditorialStatus.REJECTED,
    "pause": EditorialStatus.PAUSED,
    "inbox": EditorialStatus.INBOX,
    "publish": EditorialStatus.PUBLISHED,
}

#: Which permission a button needs.
_ACTION_PERMISSION = {
    "edit": "edit",
    "review": "edit",
    "approve": "approve",
    "schedule": "schedule",
    "reject": "reject",
    "pause": "moderate",
    "inbox": "edit",
    "publish": "publish",
}

#: Buttons shown per status: (action, label).
_CARD_BUTTONS: dict[EditorialStatus, list[tuple[str, str]]] = {
    EditorialStatus.INBOX: [
        ("edit", "✍️ Взять в работу"),
        ("review", "✅ На согласование"),
        ("reject", "❌ Отклонить"),
    ],
    EditorialStatus.EDITING: [
        ("review", "✅ На согласование"),
        ("pause", "⏸ Пауза"),
    ],
    EditorialStatus.REVIEW: [
        ("approve", "✅ Одобрить"),
        ("edit", "↩️ Вернуть в работу"),
        ("reject", "❌ Отклонить"),
    ],
    EditorialStatus.APPROVED: [
        ("schedule", "📅 В очередь публикации"),
    ],
    EditorialStatus.SCHEDULED: [
        ("publish", "🚀 Опубликовать"),
        ("pause", "⏸ Пауза"),
    ],
    EditorialStatus.FAILED: [
        ("schedule", "🔁 Повторить"),
        ("reject", "❌ Отклонить"),
    ],
    EditorialStatus.REJECTED: [
        ("inbox", "↩️ Вернуть во входящие"),
    ],
    EditorialStatus.PAUSED: [
        ("inbox", "↩️ Вернуть в работу"),
    ],
    EditorialStatus.PUBLISHED: [],
}


class EditorialError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class RoomCheck:
    room_id: str
    status: str
    status_label: str
    message: str
    how_to_fix: str = ""
    topics: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ActionResult:
    ok: bool
    action: str
    message: str
    item_id: str = ""
    status: str = ""
    answer: str = ""


class EditorialService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: Callable[..., TelegramBotProvider] = build_bot_provider,
        publish_handler: PublishHandler | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.rooms = EditorialRoomRepository(session)
        self.members = EditorialMemberRepository(session)
        self.items = EditorialItemRepository(session)
        self.audit = EditorialAuditRepository(session)
        self.bots = BotRepository(session)
        self.channels = ChannelRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory
        self._publish = publish_handler

    # --- provider ------------------------------------------------------------
    async def _room_provider(self, room: EditorialRoom) -> TelegramBotProvider | None:
        bot = await self.bots.get(room.bot_id) if room.bot_id else None
        if bot is None or not bot.has_token:
            bot = await self.bots.get_manager()
        if bot is None or not bot.enabled or not bot.token_encrypted:
            return None
        try:
            token = open_secret(bot.token_encrypted, self.settings)
        except ValueError:
            return None
        return self._provider_factory(
            token, provider_name=bot.provider_name, settings=self.settings
        )

    # --- rooms ---------------------------------------------------------------
    async def list_rooms(self) -> list[EditorialRoom]:
        return await self.rooms.list_all()

    async def get_room(self, room_id: str) -> EditorialRoom | None:
        return await self.rooms.get(room_id)

    async def room_for_channel(self, channel_id: str) -> EditorialRoom | None:
        return await self.rooms.for_channel(channel_id)

    async def room_for_group(self, group_chat_id: int) -> EditorialRoom | None:
        return await self.rooms.for_group(group_chat_id)

    async def create_room(
        self, *, channel_id: str, group_chat_id: int, bot_id: str = "", group_title: str = ""
    ) -> EditorialRoom:
        channel = await self.channels.get(channel_id)
        if channel is None:
            raise EditorialError("Канал не найден.", status_code=404)
        room = await self.rooms.for_channel(channel_id)
        if room is None:
            room = EditorialRoom(channel_id=channel_id)
            await self.rooms.add(room)
        room.channel_label = channel.title or channel.reference
        room.group_chat_id = group_chat_id
        room.group_title = group_title
        room.bot_id = bot_id
        room.status = RoomStatus.NOT_CONNECTED
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Создана редакционная комната для «{room.channel_label}».",
            explanation="Теперь проверьте права бота и создайте темы.",
            operation="room_create",
        )
        await self.session.commit()
        return room

    async def delete_room(self, room_id: str) -> None:
        room = await self.rooms.get(room_id)
        if room is None:
            raise EditorialError("Комната не найдена.", status_code=404)
        for item in await self.items.list_for_room(room_id):
            await self.items.delete(item)
        await self.rooms.delete(room)
        await self.session.commit()

    async def check_room(self, room_id: str, *, create_topics: bool = True) -> RoomCheck:
        """Verify the bot's rights in the group and (optionally) create topics."""
        room = await self.rooms.get(room_id)
        if room is None:
            raise EditorialError("Комната не найдена.", status_code=404)
        if room.group_chat_id is None:
            raise EditorialError(
                "Сначала выберите группу для редакционной комнаты.",
                how_to_fix="Создайте в Telegram супергруппу с темами и укажите её.",
            )
        provider = await self._room_provider(room)
        if provider is None:
            raise EditorialError(
                "Нет бота для редакционной комнаты.",
                how_to_fix="Добавьте управляющего бота или отдельного бота в разделе «Боты».",
            )
        try:
            if room.bot_id:
                bot = await self.bots.get(room.bot_id)
            else:
                bot = await self.bots.get_manager()
            bot_id = int(bot.telegram_id) if bot and bot.telegram_id else 0
            status = await provider.get_bot_channel_status(room.group_chat_id, bot_id)
            room.last_checked = utcnow()
            room.bot_is_member = bool(status.present)
            room.bot_is_admin = bool(status.is_admin)
            room.can_send_messages = bool(
                status.can_post_messages or status.can_manage_chat or status.is_admin
            )
            room.can_edit_messages = bool(status.can_edit_messages or status.is_admin)
            room.can_delete_messages = bool(status.can_delete_messages or status.is_admin)
            room.can_manage_topics = bool(status.can_manage_topics or status.is_admin)
            if not status.present:
                room.status = RoomStatus.NOT_CONNECTED
                room.last_error = status.message or "Бот не найден в этой группе."
            elif not room.can_send_messages:
                room.status = RoomStatus.NEEDS_RIGHTS
                room.last_error = "Боту не хватает права отправлять сообщения."
            elif create_topics:
                await self._ensure_topics(room, provider)
                room.status = RoomStatus.READY
                room.last_error = ""
            else:
                room.status = RoomStatus.READY
                room.last_error = ""
        except TelegramProviderError as exc:
            room.status = RoomStatus.ERROR
            room.last_error = exc.message
        finally:
            with contextlib.suppress(Exception):
                await provider.close()
        await self.session.flush()
        await self.session.commit()
        return RoomCheck(
            room_id=room.id,
            status=str(room.status),
            status_label=_room_status_label(room.status),
            message=room.last_error or "Комната готова к работе.",
            how_to_fix=_room_fix(room.status),
            topics=_load_topics(room),
        )

    async def _ensure_topics(self, room: EditorialRoom, provider: TelegramBotProvider) -> None:
        topics = _load_topics(room)
        for key, _emoji, title in DEFAULT_TOPICS:
            if topics.get(key):
                continue
            topic_id = await provider.create_forum_topic(room.group_chat_id or 0, title)
            if topic_id:
                topics[key] = topic_id
        room.topics = json.dumps(topics)

    # --- members / roles -----------------------------------------------------
    async def list_members(self, room_id: str) -> list[EditorialMember]:
        return await self.members.list_for_room(room_id)

    async def set_member(
        self,
        room_id: str,
        *,
        telegram_user_id: int,
        role: str,
        display_name: str = "",
        username: str = "",
        enabled: bool = True,
    ) -> EditorialMember:
        try:
            role_enum = EditorialRole(role)
        except ValueError as exc:
            raise EditorialError("Неизвестная роль.") from exc
        member = await self.members.find(room_id, telegram_user_id)
        if member is None:
            member = EditorialMember(room_id=room_id, telegram_user_id=telegram_user_id)
            await self.members.add(member)
        member.role = role_enum
        member.display_name = display_name or member.display_name
        member.username = username or member.username
        member.enabled = enabled
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Роль в редакции обновлена: {ROLE_TITLES.get(role_enum, role)}.",
            actor=display_name or str(telegram_user_id),
            operation="set_member",
        )
        await self.session.commit()
        return member

    async def remove_member(self, room_id: str, telegram_user_id: int) -> None:
        member = await self.members.find(room_id, telegram_user_id)
        if member is None:
            return
        await self.members.delete(member)
        await self.session.commit()

    async def role_for(self, room_id: str, telegram_user_id: int | None) -> EditorialRole | None:
        if telegram_user_id is None:
            return None
        if telegram_user_id in self.settings.admin_ids:
            return EditorialRole.OWNER
        member = await self.members.find(room_id, telegram_user_id)
        if member is None or not member.enabled:
            return None
        return member.role

    async def can(self, room_id: str, telegram_user_id: int | None, action: str) -> bool:
        role = await self.role_for(room_id, telegram_user_id)
        if role is None:
            return False
        return action in ROLE_ACTIONS.get(role, set())

    # --- queue items ---------------------------------------------------------
    async def enqueue_item(
        self,
        room_id: str,
        *,
        content_item_id: str,
        channel_id: str = "",
        title: str = "",
        status: EditorialStatus = EditorialStatus.INBOX,
    ) -> EditorialItem:
        room = await self.rooms.get(room_id)
        if room is None:
            raise EditorialError("Комната не найдена.", status_code=404)
        existing = await self.items.find(room_id, content_item_id, channel_id)
        if existing is not None:
            return existing
        channel = await self.channels.get(channel_id) if channel_id else None
        order_index = await self.items.next_order_index(room_id, status)
        item = EditorialItem(
            room_id=room_id,
            content_item_id=content_item_id,
            channel_id=channel_id,
            channel_label=(channel.title or channel.reference) if channel else "",
            title=title,
            status=status,
            order_index=order_index,
        )
        await self.items.add(item)
        await self.session.flush()
        await self._mirror_card(room, item)
        await self.audit.add(
            EditorialAuditEntry(
                room_id=room_id,
                item_id=item.id,
                actor_telegram_id=0,
                actor_name="Система",
                action="enqueue",
                old_status="",
                new_status=str(status),
                detail="Материал добавлен в редакционную очередь.",
            )
        )
        await self.session.commit()
        return item

    async def move(
        self,
        room_id: str,
        item_id: str,
        to_status: str,
        *,
        actor_telegram_id: int = 0,
        actor_name: str = "",
        expected_version: int | None = None,
    ) -> ActionResult:
        """Move one item to a new status, enforcing role permissions."""
        room = await self.rooms.get(room_id)
        if room is None:
            raise EditorialError("Комната не найдена.", status_code=404)
        item = await self.items.get(item_id)
        if item is None or item.room_id != room_id:
            raise EditorialError("Материал не найден.", status_code=404)
        try:
            target = EditorialStatus(to_status)
        except ValueError as exc:
            raise EditorialError("Неизвестный статус.") from exc
        action = _action_for_target(target)
        if not await self.can(room_id, actor_telegram_id, _ACTION_PERMISSION.get(action, action)):
            raise EditorialError(
                "Недостаточно прав для этого действия.",
                how_to_fix="Попросите владельца выдать вам роль редактора или модератора.",
                status_code=403,
            )
        if expected_version is not None and item.version != expected_version:
            raise EditorialError(
                "Материал изменён другим участником.",
                how_to_fix="Обновите список и повторите действие.",
                status_code=409,
            )

        old_status = str(item.status)
        publish_message = ""
        if target is EditorialStatus.PUBLISHED and self._publish is not None:
            ok, message = await self._publish(item.content_item_id, item.channel_id)
            publish_message = message
            if not ok:
                item.status = EditorialStatus.FAILED
                item.error = message
                item.version += 1
                await self._record_audit(
                    room, item, actor_telegram_id, actor_name, "publish_failed", old_status,
                    str(item.status), message,
                )
                await self._mirror_card(room, item)
                await self.session.commit()
                return ActionResult(
                    ok=False, action=action, message=message, item_id=item.id,
                    status=str(item.status),
                )

        item.status = target
        item.error = "" if target is not EditorialStatus.FAILED else item.error
        item.version += 1
        if target is EditorialStatus.SCHEDULED:
            item.order_index = await self.items.next_order_index(room_id, target)
        await self._record_audit(
            room, item, actor_telegram_id, actor_name, action, old_status, str(target),
            publish_message,
        )
        await self._mirror_card(room, item)
        await self.session.commit()
        label = STATUS_TITLES.get(target, str(target))
        return ActionResult(
            ok=True, action=action,
            message=f"Материал перемещён: {label}.",
            item_id=item.id, status=str(target),
        )

    async def reorder(
        self,
        room_id: str,
        *,
        status: str,
        ordered_ids: list[str],
        actor_telegram_id: int = 0,
        actor_name: str = "",
    ) -> list[EditorialItem]:
        """Set the explicit order of items in one status column."""
        if not await self.can(room_id, actor_telegram_id, "reorder"):
            raise EditorialError("Недостаточно прав для изменения порядка.", status_code=403)
        try:
            status_enum = EditorialStatus(status)
        except ValueError as exc:
            raise EditorialError("Неизвестный статус.") from exc
        items = {i.id: i for i in await self.items.list_for_room(room_id, status=status_enum)}
        for index, item_id in enumerate(ordered_ids, start=1):
            item = items.get(item_id)
            if item is not None:
                item.order_index = index
        await self.session.flush()
        await self._record_audit(
            room_id=room_id, item_id="", actor_telegram_id=actor_telegram_id,
            actor_name=actor_name, action="reorder", old_status="", new_status=status,
            detail=f"Новый порядок: {len(ordered_ids)}.",
        )
        await self.session.commit()
        return await self.items.list_for_room(room_id, status=status_enum)

    async def assign(
        self,
        room_id: str,
        item_id: str,
        telegram_user_id: int,
        *,
        actor_telegram_id: int = 0,
        actor_name: str = "",
    ) -> EditorialItem:
        if not await self.can(room_id, actor_telegram_id, "edit"):
            raise EditorialError("Недостаточно прав.", status_code=403)
        item = await self.items.get(item_id)
        if item is None or item.room_id != room_id:
            raise EditorialError("Материал не найден.", status_code=404)
        item.assigned_user_id = telegram_user_id
        item.version += 1
        await self._record_audit(
            room_id=room_id, item_id=item_id, actor_telegram_id=actor_telegram_id,
            actor_name=actor_name, action="assign", old_status="", new_status="",
            detail=f"Назначен пользователь {telegram_user_id}.",
        )
        await self.session.commit()
        return item

    # --- cards ---------------------------------------------------------------
    async def _mirror_card(self, room: EditorialRoom, item: EditorialItem) -> None:
        """Create the item's card in its status topic (best effort)."""
        provider = await self._room_provider(room)
        if provider is None or room.group_chat_id is None:
            return
        topics = _load_topics(room)
        topic_id = topics.get(str(item.status))
        text = _render_card(item)
        buttons = _card_buttons(item)
        try:
            result = await provider.send_topic_message(
                room.group_chat_id, topic_id or 0, text, buttons=buttons
            )
            if result.ok and result.message_ids:
                item.card_message_id = result.message_ids[0]
                item.topic_id = topic_id
        except TelegramProviderError as exc:
            logger.info("Could not mirror editorial card: %s", exc.message)
        finally:
            with contextlib.suppress(Exception):
                await provider.close()

    # --- callbacks -----------------------------------------------------------
    async def handle_callback(
        self,
        *,
        room_id: str,
        telegram_user_id: int | None,
        username: str,
        callback_query_id: str,
        data: str,
    ) -> ActionResult:
        """Handle one inline-button callback from an editorial card."""
        parsed = parse_callback(data)
        if parsed is None:
            return ActionResult(ok=False, action="", message="Непонятное действие.")
        action, item_id = parsed
        if telegram_user_id is None:
            return ActionResult(
                ok=False, action=action, message="Не удалось определить пользователя."
            )
        if not await self.can(
            room_id, telegram_user_id, _ACTION_PERMISSION.get(action, action)
        ):
            await self.events.warning(
                MODULE,
                "Отклонено действие в редакции от пользователя без прав.",
                actor=f"@{username}" if username else str(telegram_user_id),
                operation=action,
                status="refused",
            )
            await self.session.commit()
            return ActionResult(
                ok=False, action=action, item_id=item_id,
                message="Недостаточно прав для этого действия.",
                answer="Недостаточно прав",
            )
        target = _ACTION_TARGET.get(action)
        if target is None:
            return ActionResult(
                ok=False, action=action, item_id=item_id, message="Неизвестное действие."
            )
        try:
            result = await self.move(
                room_id, item_id, str(target),
                actor_telegram_id=telegram_user_id, actor_name=username,
            )
        except EditorialError as exc:
            return ActionResult(
                ok=False, action=action, item_id=item_id, message=exc.message, answer=exc.message
            )
        result.action = action
        result.answer = result.message
        return result

    # --- views ---------------------------------------------------------------
    async def board(self, room_id: str) -> dict[str, object]:
        room = await self.rooms.get(room_id)
        if room is None:
            raise EditorialError("Комната не найдена.", status_code=404)
        items = await self.items.list_for_room(room_id)
        columns: dict[str, list[dict[str, object]]] = {}
        for status in EditorialStatus:
            columns[str(status)] = []
        for item in items:
            columns[str(item.status)].append(_item_view(item))
        counts = await self.items.status_counts(room_id)
        return {
            "room_id": room.id,
            "channel_id": room.channel_id,
            "channel_label": room.channel_label,
            "group_title": room.group_title,
            "status": str(room.status),
            "status_label": _room_status_label(room.status),
            "topics": _load_topics(room),
            "counts": counts,
            "columns": columns,
            "status_titles": {str(s): STATUS_TITLES[s] for s in EditorialStatus},
        }

    async def history(self, room_id: str, item_id: str = "") -> list[EditorialAuditEntry]:
        if item_id:
            return await self.audit.list_for_item(item_id)
        return await self.audit.list_for_room(room_id)

    # --- helpers -------------------------------------------------------------
    async def _record_audit(
        self,
        room: EditorialRoom | None = None,
        item: EditorialItem | None = None,
        actor_telegram_id: int = 0,
        actor_name: str = "",
        action: str = "",
        old_status: str = "",
        new_status: str = "",
        detail: str = "",
        *,
        room_id: str = "",
        item_id: str = "",
    ) -> EditorialAuditEntry:
        entry = EditorialAuditEntry(
            room_id=room.id if room is not None else room_id,
            item_id=item.id if item is not None else item_id,
            actor_telegram_id=actor_telegram_id,
            actor_name=actor_name,
            action=action,
            old_status=old_status,
            new_status=new_status,
            detail=detail,
        )
        return await self.audit.add(entry)


# --- pure helpers ------------------------------------------------------------


def encode_callback(action: str, item_id: str) -> str:
    """Build a compact ``callback_data`` payload (≤ 64 bytes)."""
    return f"{CALLBACK_PREFIX}:{action}:{item_id}"[:CALLBACK_LIMIT]


def parse_callback(data: str) -> tuple[str, str] | None:
    """Parse ``ed:<action>:<item_id>``; returns ``None`` when malformed."""
    if not data or not data.startswith(CALLBACK_PREFIX + ":"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def _action_for_target(target: EditorialStatus) -> str:
    for action, status in _ACTION_TARGET.items():
        if status is target:
            return action
    return "move"


def _card_buttons(item: EditorialItem) -> list[list[object]]:
    from backend.app.providers.types import InlineButton

    buttons = _CARD_BUTTONS.get(item.status, [])
    rows: list[list[InlineButton]] = []
    row: list[InlineButton] = []
    for action, label in buttons:
        row.append(
            InlineButton(text=label, action="callback", value=encode_callback(action, item.id))
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def _render_card(item: EditorialItem) -> str:
    label = STATUS_TITLES.get(item.status, str(item.status))
    lines = [f"🗂 {item.title or 'Материал'}", f"Статус: {label}"]
    if item.channel_label:
        lines.append(f"Канал: {item.channel_label}")
    if item.assigned_user_id:
        lines.append(f"Ответственный: {item.assigned_user_id}")
    if item.error:
        lines.append(f"Ошибка: {item.error}")
    lines.append(f"№ {item.order_index}")
    return "\n".join(lines)


def _item_view(item: EditorialItem) -> dict[str, object]:
    return {
        "id": item.id,
        "content_item_id": item.content_item_id,
        "channel_id": item.channel_id,
        "channel_label": item.channel_label,
        "title": item.title,
        "status": str(item.status),
        "status_title": STATUS_TITLES.get(item.status, str(item.status)),
        "order_index": item.order_index,
        "assigned_user_id": item.assigned_user_id,
        "version": item.version,
        "error": item.error,
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else "",
        "card_message_id": item.card_message_id,
        "topic_id": item.topic_id,
        "available_actions": [a for a, _ in _CARD_BUTTONS.get(item.status, [])],
    }


def _load_topics(room: EditorialRoom) -> dict[str, int]:
    try:
        data = json.loads(room.topics or "{}")
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items() if str(v).lstrip("-").isdigit()}


def _room_status_label(status: RoomStatus | str) -> str:
    from backend.app.db.models.editorial import ROOM_STATUS_TITLES

    try:
        return ROOM_STATUS_TITLES[RoomStatus(str(status))]
    except (ValueError, KeyError):
        return str(status)


def _room_fix(status: RoomStatus) -> str:
    return {
        RoomStatus.NOT_CONNECTED: "Добавьте бота в группу редакции.",
        RoomStatus.NEEDS_RIGHTS: "Выдайте боту права отправлять сообщения и управлять темами.",
        RoomStatus.ERROR: "Проверьте подключение и повторите.",
        RoomStatus.READY: "",
    }.get(status, "")


__all__ = [
    "CALLBACK_LIMIT",
    "CALLBACK_PREFIX",
    "MODULE",
    "ActionResult",
    "EditorialError",
    "EditorialService",
    "PublishHandler",
    "RoomCheck",
    "encode_callback",
    "parse_callback",
]
