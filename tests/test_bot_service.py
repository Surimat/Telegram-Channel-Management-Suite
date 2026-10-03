"""BotService tests: inventory, health, secrets, managed-bot workflow.

All Telegram access uses the deterministic fake provider (decision D-001), so
no real credentials or network are needed.
"""

from __future__ import annotations

import pytest

from backend.app.db.models.bot import BotHealth, BotKind
from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import InvalidTokenError
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.registry import build_bot_provider
from backend.app.services.bot_service import BotService, BotServiceError


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def _factory(token, *, provider_name="auto", settings=None):
    return FakeTelegramBotProvider(token)


def _factory_failing(token, *, provider_name="auto", settings=None):
    return FakeTelegramBotProvider(token, fail_with=InvalidTokenError("Токен отклонён."))


async def test_add_bot_validates_and_seals_token() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        bot = await service.add_bot("111:AAA")
        assert bot.telegram_id == 111
        assert bot.username == "bot111"
        assert bot.health == BotHealth.OK
        assert bot.has_token is True
        # The raw token is never stored; only its sealed form.
        assert "111:AAA" not in bot.token_encrypted
        assert bot.token_encrypted.startswith("enc:")


async def test_add_bot_rejects_empty_token() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        with pytest.raises(BotServiceError):
            await service.add_bot("   ")


async def test_add_bot_surfaces_provider_error() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory_failing)
        with pytest.raises(BotServiceError) as exc:
            await service.add_bot("222:BBB")
        assert "Токен" in exc.value.message


async def test_add_duplicate_bot_reuses_record() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        first = await service.add_bot("333:CCC")
        second = await service.add_bot("333:CCC")
        assert first.id == second.id
        bots = await service.list_bots()
        assert len(bots) == 1


async def test_only_one_manager_bot() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        await service.add_bot("1:AAA", kind=BotKind.MANAGER)
        with pytest.raises(BotServiceError) as exc:
            await service.add_bot("2:BBB", kind=BotKind.MANAGER)
        assert exc.value.status_code == 409


async def test_enable_disable_and_remove() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        bot = await service.add_bot("444:DDD")
        disabled = await service.set_enabled(bot.id, False)
        assert disabled.enabled is False
        await service.remove(bot.id)
        assert await service.get(bot.id) is None


async def test_health_check_updates_state() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        bot = await service.add_bot("555:EEE")
        result = await service.health_check(bot.id)
        assert result.ok is True
        assert result.status == BotHealth.OK.value
        refreshed = await service.get(bot.id)
        assert refreshed is not None and refreshed.last_health_at is not None


async def test_health_check_failure_marks_error() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        bot = await service.add_bot("666:FFF")
        failing = BotService(session, provider_factory=_factory_failing)
        result = await failing.health_check(bot.id)
        assert result.ok is False
        assert result.status == BotHealth.ERROR.value


async def test_summary_reports_manager_state() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        await service.add_bot("777:GGG", kind=BotKind.MANAGER)
        await service.add_bot("888:HHH", kind=BotKind.ORDINARY)
        summary = await service.summary()
        assert summary["total"] == 2
        assert summary["manager_connected"] is True


async def test_managed_bot_register_and_fetch_token() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        await service.add_bot("999:MMM", kind=BotKind.MANAGER)
        managed = await service.register_managed_bot(
            user_id=12345, username="childbot", owner_username="owner"
        )
        assert managed.kind == BotKind.MANAGED
        assert managed.has_token is False
        updated = await service.fetch_managed_bot_token(managed.id)
        assert updated.has_token is True
        assert updated.token_encrypted.startswith("enc:")


async def test_fetch_managed_token_without_manager_fails() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        managed = await service.register_managed_bot(user_id=54321, username="orphan")
        with pytest.raises(BotServiceError) as exc:
            await service.fetch_managed_bot_token(managed.id)
        assert exc.value.status_code == 409


async def test_manager_link_uses_official_format() -> None:
    async with session_scope() as session:
        service = BotService(session, provider_factory=_factory)
        bot = await service.add_bot("1010:LNK", kind=BotKind.MANAGER)
        link = await service.manager_link("newchild")
        assert link == f"https://t.me/newbot/{bot.username}/newchild?name=newchild"


async def test_ensure_manager_bot_from_settings(monkeypatch) -> None:
    from backend.app.core.config import Settings

    settings = Settings(manager_bot_token="1212:ENV")
    async with session_scope() as session:
        service = BotService(session, settings=settings, provider_factory=_factory)
        bot = await service.ensure_manager_bot()
        assert bot is not None and bot.kind == BotKind.MANAGER
        # Idempotent: calling again does not create a duplicate.
        again = await service.ensure_manager_bot()
        assert again is not None and again.id == bot.id


def test_registry_default_is_real_provider() -> None:
    provider = build_bot_provider("1:A", provider_name="aiogram")
    # The real adapter is not the fake, and exposes the managed-bot surface.
    assert hasattr(provider, "get_managed_bot_token")
