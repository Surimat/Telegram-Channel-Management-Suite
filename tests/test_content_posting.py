"""Content Studio posting engine + moderation tests (v1.2).

Exercises the real :class:`PostingService` against the deterministic fake bot
provider (no network, no credentials) plus the auto-moderation rules in
:class:`ContentService`.
"""

from __future__ import annotations

import pytest

from backend.app.db.base import utcnow
from backend.app.db.models.channel import Channel
from backend.app.db.models.content import ContentItem, ContentItemStatus
from backend.app.db.session import init_models, session_scope
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.posting import BotPostingProvider
from backend.app.providers.types import InlineButton
from backend.app.services.content_service import ContentService
from backend.app.services.posting_service import (
    PostingService,
    TargetSpec,
    validate_buttons,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


async def _seed_item(text: str = "Привет, мир") -> str:
    async with session_scope() as session:
        item = ContentItem(
            title="T",
            text=text,
            entities="[]",
            status=ContentItemStatus.DRAFT,
        )
        session.add(item)
    return item.id


async def _seed_channel(reference: str = "@demo") -> str:
    async with session_scope() as session:
        channel = Channel(reference=reference, title="Demo", username="demo")
        session.add(channel)
    return channel.id


def _bot_resolver(fake: FakeTelegramBotProvider):
    async def _resolve(channel_id: str):
        return BotPostingProvider(fake), "Тест"

    return _resolve


async def test_plan_publish_and_preview_flow() -> None:
    item_id = await _seed_item("Привет, <b>мир</b>")
    channel_id = await _seed_channel()
    fake = FakeTelegramBotProvider("111:AAA")

    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        pubs = await service.plan(item_id, [TargetSpec(channel_id=channel_id)])
        assert len(pubs) == 1
        pub_id = pubs[0].id

        preview = await service.preview(item_id)
        assert preview.text
        assert preview.char_count > 0

        outcome = await service.publish(pub_id)
        assert outcome.ok, outcome.message
        assert outcome.message_ids
        assert fake.posts and fake.posts[0]["text"].startswith("Привет")

        # Re-publishing without force is a no-op (idempotent).
        again = await service.publish(pub_id)
        assert again.ok and again.message == "Уже опубликовано."


async def test_plan_is_idempotent_per_channel() -> None:
    item_id = await _seed_item()
    channel_id = await _seed_channel()
    fake = FakeTelegramBotProvider("111:AAA")
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        first = await service.plan(item_id, [TargetSpec(channel_id=channel_id)])
        second = await service.plan(item_id, [TargetSpec(channel_id=channel_id)])
        assert first[0].id == second[0].id


async def test_publish_held_item_is_refused() -> None:
    item_id = await _seed_item()
    channel_id = await _seed_channel()
    async with session_scope() as session:
        item = await session.get(ContentItem, item_id)
        assert item is not None
        item.held = True
        item.moderation_note = "Удержано ночной модерацией."
    fake = FakeTelegramBotProvider("111:AAA")
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        pubs = await service.plan(item_id, [TargetSpec(channel_id=channel_id)])
        outcome = await service.publish(pubs[0].id)
        assert not outcome.ok
        assert outcome.status == "held"


async def test_publish_uncertain_marks_not_retried() -> None:
    item_id = await _seed_item()
    channel_id = await _seed_channel()
    fake = FakeTelegramBotProvider("111:AAA")

    async def _flaky(*args, **kwargs):  # type: ignore[no-untyped-def]
        from backend.app.providers.types import PostSendResult

        return PostSendResult(
            ok=False, message="Связь прервалась.", uncertain=True
        )

    fake.send_post = _flaky  # type: ignore[assignment]
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        pubs = await service.plan(item_id, [TargetSpec(channel_id=channel_id)])
        outcome = await service.publish(pubs[0].id)
        assert not outcome.ok and outcome.uncertain


async def test_schedule_and_calendar() -> None:
    from datetime import timedelta

    item_id = await _seed_item()
    channel_id = await _seed_channel()
    fake = FakeTelegramBotProvider("111:AAA")
    when = utcnow() + timedelta(hours=1)
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        pubs = await service.plan(
            item_id, [TargetSpec(channel_id=channel_id, scheduled_at=when)]
        )
        assert pubs[0].scheduled_at is not None
        data = await service.calendar(utcnow(), utcnow() + timedelta(days=2))
        assert len(data["entries"]) == 1
        assert data["entries"][0]["publication_id"] == pubs[0].id


async def test_tick_publishes_due_and_auto_deletes() -> None:
    from datetime import timedelta

    item_id = await _seed_item()
    channel_id = await _seed_channel()
    fake = FakeTelegramBotProvider("111:AAA")
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        pubs = await service.plan(item_id, [TargetSpec(channel_id=channel_id)])
        pub = pubs[0]
        pub.scheduled_at = utcnow() - timedelta(minutes=1)
        pub.delete_at = utcnow() - timedelta(minutes=1)
        await session.flush()
        result = await service.tick()
        assert result["published"] == 1
        assert fake.posts
        # delete_at was already in the past → deleted on the same tick.
        assert result["deleted"] == 1
        assert fake.deleted


async def test_validate_rejects_broken_markup() -> None:
    item_id = await _seed_item("Текст с **незакрытым тегом")
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(
            FakeTelegramBotProvider("111:AAA")
        ))
        result = await service.validate(item_id)
        assert not result["ok"]
        assert result["issues"]


async def test_validate_buttons_rules() -> None:
    assert validate_buttons([[InlineButton(text="A", action="url", value="https://x")]]) == []
    problems = validate_buttons([[InlineButton(text="A", action="url", value="not-a-url")]])
    assert problems
    problems = validate_buttons([[InlineButton(text="", action="url", value="https://x")]])
    assert problems


async def test_blocked_keywords_filter_grab() -> None:
    async with session_scope() as session:
        service = ContentService(session)
        source = await service.create_source(
            kind="manual", reference="Плохое слово и текст"
        )
        await service.set_moderation(source.id, blocked_keywords=["Плохое"])
        outcome = await service.grab(source.id)
        assert outcome.new_items == 0
        assert outcome.blocked == 1


async def test_quiet_hours_hold_and_release() -> None:
    async with session_scope() as session:
        service = ContentService(session)
        source = await service.create_source(kind="manual", reference="Ночной текст")
        hour = utcnow().hour
        await service.set_moderation(
            source.id,
            quiet_hours_enabled=True,
            quiet_hours_start=hour,
            quiet_hours_end=(hour + 1) % 24,
            quiet_hours_tz="UTC",
        )
        outcome = await service.grab(source.id)
        assert outcome.held == 1
        item_id = outcome.item_ids[0]
        item = await session.get(ContentItem, item_id)
        assert item is not None and item.held
        released = await service.release_held(item_id)
        assert not released.held
