"""Tests for the Editorial Workspace (v1.4: редакционная комната).

The real service + repositories + API are exercised against the deterministic
fake bot provider. No Telegram account, network or real forum is required.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.db.models.editorial import EditorialRole, EditorialStatus, RoomStatus
from backend.app.db.session import init_models
from backend.app.services.editorial_service import (
    EditorialError,
    encode_callback,
    parse_callback,
)

EDITORIAL = "/api/v1/editorial"


# --- pure helpers ------------------------------------------------------------


def test_callback_roundtrip_and_limits() -> None:
    data = encode_callback("approve", "abc123")
    assert len(data.encode("utf-8")) <= 64
    assert parse_callback(data) == ("approve", "abc123")
    assert parse_callback("") is None
    assert parse_callback("nope") is None
    assert parse_callback("ed:approve") is None
    assert parse_callback("ed::abc") is None


def test_role_actions_are_honest() -> None:
    from backend.app.db.models.editorial import ROLE_ACTIONS

    # A viewer can only view; a moderator can never publish.
    assert ROLE_ACTIONS[EditorialRole.VIEWER] == {"view"}
    assert "publish" not in ROLE_ACTIONS[EditorialRole.MODERATOR]
    assert "publish" in ROLE_ACTIONS[EditorialRole.EDITOR]
    assert "manage_roles" in ROLE_ACTIONS[EditorialRole.OWNER]


# --- API ---------------------------------------------------------------------


@pytest_asyncio.fixture
async def editorial_client() -> AsyncClient:
    from backend.app.api.deps import get_provider_factory
    from backend.app.main import create_app
    from backend.app.providers.fake_bot import FakeTelegramBotProvider

    await init_models()
    app = create_app()
    app.dependency_overrides[get_provider_factory] = lambda: (
        lambda token, *, provider_name="auto", settings=None: FakeTelegramBotProvider(token)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _setup_room(client: AsyncClient, monkeypatch) -> str:
    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "777")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()

    channel = await client.post("/api/v1/channels", json={"reference": "@editorial_demo"})
    assert channel.status_code == 201, channel.text
    channel_id = channel.json()["id"]

    bot = await client.post(
        "/api/v1/bots", json={"token": "222:BBB", "kind": "manager"}
    )
    assert bot.status_code == 201, bot.text
    bot_id = bot.json()["id"]

    room = await client.post(
        EDITORIAL + "/rooms",
        json={
            "channel_id": channel_id,
            "group_chat_id": -1001234567890,
            "bot_id": bot_id,
            "group_title": "Редакция",
        },
    )
    assert room.status_code == 200, room.text
    assert room.json()["status"] == "not_connected"
    # No right is claimed before a real check.
    assert room.json()["bot_is_member"] is False
    return room.json()["id"]


async def test_room_check_verifies_rights_and_creates_topics(
    editorial_client: AsyncClient, monkeypatch
) -> None:
    room_id = await _setup_room(editorial_client, monkeypatch)

    check = await editorial_client.post(f"{EDITORIAL}/rooms/{room_id}/check")
    assert check.status_code == 200, check.text
    body = check.json()
    assert body["status"] == "ready"
    assert body["status_label"] == "Готова"
    # Topics were created for the default columns.
    assert set(body["topics"]) >= {"inbox", "editing", "review", "scheduled"}

    rooms = await editorial_client.get(EDITORIAL + "/rooms")
    assert rooms.status_code == 200
    assert rooms.json()["items"][0]["status"] == "ready"
    # The token never leaks.
    assert "BBB" not in rooms.text


async def test_room_check_reports_missing_rights(
    editorial_client: AsyncClient, monkeypatch
) -> None:
    from backend.app.api.deps import get_provider_factory
    from backend.app.providers.fake_bot import FakeTelegramBotProvider
    from backend.app.providers.types import BotChannelStatus

    room_id = await _setup_room(editorial_client, monkeypatch)

    def _factory(token, *, provider_name="auto", settings=None):
        provider = FakeTelegramBotProvider(token)
        provider.script_bot_status(
            -1001234567890,
            BotChannelStatus(found=True, present=True, status="member", is_admin=False),
        )
        return provider

    # Re-create the app dependency override for this test.
    app = editorial_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_provider_factory] = lambda: _factory

    check = await editorial_client.post(f"{EDITORIAL}/rooms/{room_id}/check")
    assert check.status_code == 200, check.text
    assert check.json()["status"] == "needs_rights"
    assert "права" in check.json()["how_to_fix"].lower()


async def test_queue_move_reorder_and_audit(
    editorial_client: AsyncClient, monkeypatch
) -> None:
    room_id = await _setup_room(editorial_client, monkeypatch)
    await editorial_client.post(f"{EDITORIAL}/rooms/{room_id}/check")

    # The owner (admin id) enqueues two items.
    first = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items",
        json={"content_item_id": "c1", "title": "Новость"},
    )
    assert first.status_code == 200, first.text
    second = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items",
        json={"content_item_id": "c2", "title": "Анонс"},
    )
    assert second.status_code == 200
    item_id = first.json()["id"]

    board = await editorial_client.get(f"{EDITORIAL}/rooms/{room_id}/board")
    assert board.status_code == 200
    assert board.json()["counts"].get("inbox") == 2
    assert "inbox" in board.json()["columns"]

    # Move the first item to review as the owner.
    moved = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items/{item_id}/move",
        json={"status": "review", "actor_telegram_id": 777, "actor_name": "owner"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["ok"] is True
    assert moved.json()["status"] == "review"

    # Reorder the review column.
    reordered = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/reorder",
        json={"status": "review", "ordered_ids": [item_id], "actor_telegram_id": 777},
    )
    assert reordered.status_code == 200

    audit = await editorial_client.get(f"{EDITORIAL}/rooms/{room_id}/audit")
    assert audit.status_code == 200
    actions = [e["action"] for e in audit.json()]
    assert "enqueue" in actions and "review" in actions


async def test_move_denied_for_user_without_role(
    editorial_client: AsyncClient, monkeypatch
) -> None:
    room_id = await _setup_room(editorial_client, monkeypatch)
    item = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items", json={"content_item_id": "c1"}
    )
    item_id = item.json()["id"]

    # A user id that is neither an admin nor a member is refused.
    denied = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items/{item_id}/move",
        json={"status": "review", "actor_telegram_id": 424242},
    )
    assert denied.status_code == 403, denied.text


async def test_member_roles_and_permissions(
    editorial_client: AsyncClient, monkeypatch
) -> None:
    room_id = await _setup_room(editorial_client, monkeypatch)

    added = await editorial_client.put(
        f"{EDITORIAL}/rooms/{room_id}/members",
        json={"telegram_user_id": 555, "role": "moderator", "display_name": "Модератор"},
    )
    assert added.status_code == 200, added.text
    assert added.json()["role"] == "moderator"
    assert added.json()["role_title"] == "Модератор"

    members = await editorial_client.get(f"{EDITORIAL}/rooms/{room_id}/members")
    assert len(members.json()) == 1

    # A moderator may reject but not publish.
    item = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items", json={"content_item_id": "c1"}
    )
    item_id = item.json()["id"]
    reject = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items/{item_id}/move",
        json={"status": "rejected", "actor_telegram_id": 555},
    )
    assert reject.status_code == 200, reject.text
    publish = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items/{item_id}/move",
        json={"status": "published", "actor_telegram_id": 555},
    )
    assert publish.status_code == 403

    removed = await editorial_client.delete(f"{EDITORIAL}/rooms/{room_id}/members/555")
    assert removed.status_code == 200
    assert (await editorial_client.get(f"{EDITORIAL}/rooms/{room_id}/members")).json() == []


async def test_version_conflict_is_reported(
    editorial_client: AsyncClient, monkeypatch
) -> None:
    room_id = await _setup_room(editorial_client, monkeypatch)
    item = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items", json={"content_item_id": "c1"}
    )
    item_id = item.json()["id"]
    conflict = await editorial_client.post(
        f"{EDITORIAL}/rooms/{room_id}/items/{item_id}/move",
        json={"status": "review", "actor_telegram_id": 777, "expected_version": 99},
    )
    assert conflict.status_code == 409


async def test_unknown_room_is_not_found(editorial_client: AsyncClient) -> None:
    resp = await editorial_client.get(f"{EDITORIAL}/rooms/does-not-exist/board")
    assert resp.status_code == 404


# --- service-level -----------------------------------------------------------


async def test_publish_failure_marks_item_failed(monkeypatch) -> None:
    from backend.app.db.models.channel import Channel
    from backend.app.db.session import session_scope
    from backend.app.providers.fake_bot import FakeTelegramBotProvider
    from backend.app.services.editorial_service import EditorialService

    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "777")
    from backend.app.core.config import reset_settings_cache

    reset_settings_cache()
    await init_models()

    async with session_scope() as session:
        channel = Channel(reference="@c", title="Канал")
        session.add(channel)
        await session.flush()
        channel_id = channel.id

    async def _fail_publish(_content_item_id: str, _channel_id: str) -> tuple[bool, str]:
        return False, "Публикация не удалась."

    async with session_scope() as session:
        svc = EditorialService(
            session,
            provider_factory=lambda token, **kw: FakeTelegramBotProvider(token),
            publish_handler=_fail_publish,
        )
        room = await svc.create_room(channel_id=channel_id, group_chat_id=-100999)
        item = await svc.enqueue_item(room.id, content_item_id="c1")
        result = await svc.move(
            room.id, item.id, "published", actor_telegram_id=777, actor_name="owner"
        )
        assert result.ok is False
        assert result.status == str(EditorialStatus.FAILED)
        assert item.error


async def test_callback_handles_unknown_payload() -> None:
    from backend.app.services.editorial_service import EditorialService

    # handle_callback with a malformed payload never touches the DB.
    result = await EditorialService.__new__(EditorialService).handle_callback(
        room_id="r",
        telegram_user_id=1,
        username="u",
        callback_query_id="q",
        data="garbage",
    )
    assert result.ok is False


async def test_runtime_routes_editorial_callback(monkeypatch) -> None:
    """The manager runtime routes a card callback into the editorial service."""
    from backend.app.db.models.bot import Bot, BotKind
    from backend.app.db.models.channel import Channel
    from backend.app.db.models.editorial import EditorialRoom
    from backend.app.db.session import session_scope
    from backend.app.manager.runtime import ManagerBotRuntime
    from backend.app.providers.fake_bot import FakeTelegramBotProvider
    from backend.app.providers.types import BotUpdate
    from backend.app.services.editorial_service import encode_callback

    monkeypatch.setenv("MANAGER_BOT_ADMIN_IDS", "777")
    from backend.app.core.config import reset_settings_cache
    from backend.app.core.security import seal_secret

    reset_settings_cache()
    await init_models()

    async with session_scope() as session:
        channel = Channel(reference="@c", title="Канал")
        session.add(channel)
        await session.flush()
        bot = Bot(
            kind=BotKind.MANAGER,
            enabled=True,
            telegram_id="999",
            token_encrypted=seal_secret("999:ZZZ"),
        )
        session.add(bot)
        await session.flush()
        room = EditorialRoom(
            channel_id=channel.id,
            group_chat_id=-100500,
            bot_id=bot.id,
            status=RoomStatus.READY,
        )
        session.add(room)
        await session.flush()
        room_id = room.id

    provider = FakeTelegramBotProvider("999:ZZZ")
    provider.queue_updates(
        [
            BotUpdate(
                update_id=1,
                kind="callback",
                chat_id=-100500,
                user_id=777,
                username="owner",
                callback_query_id="cb1",
                callback_data=encode_callback("review", "item-1"),
            )
        ]
    )

    runtime = ManagerBotRuntime(poll_interval=0.01)
    async with session_scope() as session:
        await runtime._handle_editorial_callback(session, provider, provider._updates[0])

    # The callback was acknowledged, even though the item does not exist.
    assert provider.answered_callbacks
    assert provider.answered_callbacks[0][0] == "cb1"
    assert room_id  # keep the room id referenced


async def test_callback_ignores_unknown_group() -> None:
    from backend.app.db.session import session_scope
    from backend.app.manager.runtime import ManagerBotRuntime
    from backend.app.providers.fake_bot import FakeTelegramBotProvider
    from backend.app.providers.types import BotUpdate

    await init_models()
    provider = FakeTelegramBotProvider("1:A")
    update = BotUpdate(
        update_id=1,
        kind="callback",
        chat_id=-1,
        user_id=1,
        callback_query_id="cb",
        callback_data="ed:review:x",
    )
    runtime = ManagerBotRuntime(poll_interval=0.01)
    async with session_scope() as session:
        await runtime._handle_editorial_callback(session, provider, update)
    assert provider.answered_callbacks
    assert "не найдена" in provider.answered_callbacks[0][1].lower()


def test_service_error_carries_fix_hint() -> None:
    exc = EditorialError("Нет прав.", how_to_fix="Попросите владельца.", status_code=403)
    assert exc.status_code == 403
    assert exc.how_to_fix == "Попросите владельца."
