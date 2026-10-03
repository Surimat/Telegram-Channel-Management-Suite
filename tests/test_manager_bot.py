"""Manager-bot command + notification tests (post-1.0 hardening).

Runs the real service and the deterministic fake bot provider: no Telegram, no
network. Verifies authorization, plain-language commands, notification routing
and that delivery failures never propagate.
"""

from __future__ import annotations

import pytest

from backend.app.core.config import get_settings
from backend.app.core.security import seal_secret
from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.session import init_models, session_scope
from backend.app.manager.bus import (
    CATEGORY_AI,
    CATEGORY_SYSTEM,
    CATEGORY_TELEGRAM,
    Notification,
    NotificationBus,
    category_for_module,
    get_notification_bus,
    reset_notification_bus,
)
from backend.app.manager.service import ManagerBotService
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.types import BotUpdate


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()
    reset_notification_bus()
    yield
    reset_notification_bus()


async def _make_manager_bot(*, enabled: bool = True) -> None:
    settings = get_settings()
    async with session_scope() as db:
        bot = Bot(
            kind=BotKind.MANAGER,
            username="my_manager_bot",
            telegram_id=111,
            token_encrypted=seal_secret("123456:ABCDEF", settings),
            provider_name="fake",
            enabled=enabled,
            health=BotHealth.OK,
        )
        db.add(bot)
        await db.flush()


# --- authorization -----------------------------------------------------------


async def test_admin_check_uses_configured_ids(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42, 99")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        assert svc.is_admin(42) is True
        assert svc.is_admin(99) is True
        assert svc.is_admin(7) is False
        assert svc.is_admin(None) is False


async def test_unknown_user_command_refused(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        result = await svc.handle_update(
            BotUpdate(update_id=1, chat_id=5, user_id=999, text="/status")
        )
        assert result.handled is True
        assert result.authorized is False
        assert result.refused is True
        assert "владельц" in result.reply.lower()


async def test_non_command_ignored(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        result = await svc.handle_update(
            BotUpdate(update_id=1, chat_id=5, user_id=42, text="привет")
        )
        assert result.handled is False


async def test_unknown_command_not_handled(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        result = await svc.handle_update(
            BotUpdate(update_id=1, chat_id=5, user_id=42, text="/nonsense")
        )
        assert result.handled is False


# --- commands ----------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "start",
        "help",
        "status",
        "bots",
        "accounts",
        "queue",
        "reactions",
        "audience",
        "invites",
        "backup",
    ],
)
async def test_admin_commands_reply(monkeypatch, command: str) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        result = await svc.handle_update(
            BotUpdate(update_id=1, chat_id=5, user_id=42, text=f"/{command}")
        )
        assert result.handled is True
        assert result.authorized is True
        assert result.reply


async def test_command_with_bot_suffix(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        result = await svc.handle_update(
            BotUpdate(update_id=1, chat_id=5, user_id=42, text="/help@my_manager_bot")
        )
        assert result.handled is True
        assert result.authorized is True


async def test_reply_has_no_secrets(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await _make_manager_bot()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        result = await svc.handle_update(
            BotUpdate(update_id=1, chat_id=5, user_id=42, text="/bots")
        )
        blob = result.reply.lower()
        assert "abcdef" not in blob
        assert "token" not in blob
        assert "enc:" not in blob


# --- notification bus --------------------------------------------------------


async def test_bus_publish_drain_and_categories() -> None:
    bus = NotificationBus()
    bus.publish(Notification(category=CATEGORY_SYSTEM, event_key="a", message="m1"))
    bus.publish(Notification(category=CATEGORY_AI, event_key="b", message="m2"))
    assert bus.pending == 2
    drained = bus.drain(limit=10)
    assert [n.message for n in drained] == ["m1", "m2"]
    assert bus.empty()


async def test_bus_is_bounded_and_never_raises() -> None:
    bus = NotificationBus(maxsize=1)
    bus.publish(Notification(category=CATEGORY_SYSTEM, event_key="a", message="m1"))
    bus.publish(Notification(category=CATEGORY_SYSTEM, event_key="b", message="m2"))
    assert bus.dropped == 1


async def test_module_category_mapping() -> None:
    assert category_for_module("ai.classifier") == CATEGORY_AI
    assert category_for_module("invites") == "invites"
    assert category_for_module("sessions.session_service") == CATEGORY_TELEGRAM
    assert category_for_module("unknown.module") == CATEGORY_SYSTEM


# --- notification delivery ---------------------------------------------------


async def test_deliver_pending_sends_to_owner(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await _make_manager_bot()
    bus = get_notification_bus()
    bus.publish(
        Notification(
            category=CATEGORY_SYSTEM,
            event_key="app.started",
            message="Приложение запущено.",
            how_to_fix="Ничего делать не нужно.",
        )
    )
    provider = FakeTelegramBotProvider("123:abc")
    async with session_scope() as db:
        svc = ManagerBotService(db)
        sent = await svc.deliver_pending(provider)
    assert sent == 1
    assert provider.sent_messages
    chat_id, text = provider.sent_messages[0]
    assert chat_id == 42
    assert "Приложение запущено" in text


async def test_deliver_pending_respects_master_switch(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await _make_manager_bot()
    provider = FakeTelegramBotProvider("123:abc")
    async with session_scope() as db:
        svc = ManagerBotService(db)
        await svc.update_notification_settings(enabled=False)
        get_notification_bus().publish(
            Notification(category=CATEGORY_SYSTEM, event_key="x", message="m")
        )
        sent = await svc.deliver_pending(provider)
    assert sent == 0
    assert provider.sent_messages == []


async def test_deliver_pending_respects_category_switch(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await _make_manager_bot()
    provider = FakeTelegramBotProvider("123:abc")
    async with session_scope() as db:
        svc = ManagerBotService(db)
        await svc.update_notification_settings(categories={CATEGORY_AI: False})
        get_notification_bus().publish(
            Notification(category=CATEGORY_AI, event_key="x", message="ai-off")
        )
        get_notification_bus().publish(
            Notification(category=CATEGORY_SYSTEM, event_key="y", message="sys-on")
        )
        sent = await svc.deliver_pending(provider)
    assert sent == 1
    assert "sys-on" in provider.sent_messages[0][1]


async def test_delivery_failure_never_raises(monkeypatch) -> None:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "42")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await _make_manager_bot()
    provider = FakeTelegramBotProvider("123:abc", fail_with=RuntimeError("boom"))
    get_notification_bus().publish(
        Notification(category=CATEGORY_SYSTEM, event_key="x", message="m")
    )
    async with session_scope() as db:
        svc = ManagerBotService(db)
        sent = await svc.deliver_pending(provider)
    assert sent == 0


async def test_events_error_publishes_notification() -> None:
    from backend.app.services.events_service import EventsService

    async with session_scope() as db:
        events = EventsService(db)
        await events.error(
            "invites",
            "Тестовое уведомление.",
            how_to_fix="Проверьте настройки.",
            operation="invite",
            status="error",
        )
        await db.commit()
    assert get_notification_bus().pending >= 1


# --- manager provider --------------------------------------------------------


async def test_manager_provider_built_from_db(monkeypatch) -> None:
    await _make_manager_bot()
    async with session_scope() as db:
        svc = ManagerBotService(db)
        provider = await svc.manager_provider()
        assert provider is not None
        assert isinstance(provider, FakeTelegramBotProvider)
        assert await svc.register_commands(provider) is True
        assert provider.commands


async def test_manager_provider_none_when_disabled() -> None:
    await _make_manager_bot(enabled=False)
    async with session_scope() as db:
        svc = ManagerBotService(db)
        assert await svc.manager_provider() is None
