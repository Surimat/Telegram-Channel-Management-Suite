"""Provider tests: the fake provider and interface conformance.

No real credentials or network are required (decision D-001).
"""

from __future__ import annotations

import pytest

from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import InvalidTokenError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.registry import build_bot_provider
from backend.app.providers.types import BotIdentity, ManagedBotRef


def test_fake_provider_satisfies_interface() -> None:
    provider = FakeTelegramBotProvider("123:ABC")
    assert isinstance(provider, TelegramBotProvider)


async def test_get_me_derives_identity_from_token() -> None:
    provider = FakeTelegramBotProvider("555:XYZ")
    me = await provider.get_me()
    assert me.id == 555
    assert me.username == "bot555"


async def test_get_me_rejects_malformed_token() -> None:
    provider = FakeTelegramBotProvider("not-a-token")
    with pytest.raises(InvalidTokenError):
        await provider.get_me()


async def test_managed_bot_token_and_list() -> None:
    managed = [ManagedBotRef(user_id=42, username="child", owner_username="owner")]
    provider = FakeTelegramBotProvider(
        "1:AAA",
        identity=BotIdentity(id=1, username="manager", can_manage_bots=True),
        managed_bots=managed,
    )
    assert (await provider.get_managed_bot_token(42)).startswith("42:")
    assert "MANAGED" in await provider.get_managed_bot_token(42)
    bots = await provider.get_managed_bots()
    assert bots and bots[0].username == "child"


async def test_send_message_is_recorded() -> None:
    provider = FakeTelegramBotProvider("7:ZZZ")
    await provider.send_message(10, "Привет")
    assert provider.sent_messages == [(10, "Привет")]


def test_registry_fake_selection() -> None:
    provider = build_bot_provider("1:A", provider_name="fake")
    assert isinstance(provider, FakeTelegramBotProvider)


def test_registry_offline_mode_uses_fake() -> None:
    from backend.app.core.config import Settings

    settings = Settings(offline_mode=True)
    provider = build_bot_provider("1:A", settings=settings)
    assert isinstance(provider, FakeTelegramBotProvider)
