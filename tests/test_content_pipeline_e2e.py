"""v2.0 end-to-end content scenario on fake providers (one item, one path).

Proves the whole researched path works together, not just per unit:

    English source → translate to Russian → AI processing → human moderation →
    schedule → test publication → first comment → auto-delete

and, critically (D-116):

* a failed first comment or auto-delete never changes the publication's success;
* a restart (a second ``tick`` / a repeated ``plan``) never creates duplicates.

Everything runs against the deterministic fake bot provider and a fake AI
gateway — no network, no credentials, no message to a real user or channel.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.ai.gateway.types import ChatResponse
from backend.app.db.base import utcnow
from backend.app.db.models.channel import Channel
from backend.app.db.models.content import (
    CommentPlan,
    ContentItem,
    ContentItemStatus,
    ContentSource,
    Publication,
    PublicationStatus,
)
from backend.app.db.session import init_models, session_scope
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.posting import BotPostingProvider
from backend.app.providers.types import PostSendResult
from backend.app.services.ai_profiles import AiProfileService
from backend.app.services.content_pipeline import ContentPipelineService
from backend.app.services.posting_service import PostingService, TargetSpec

pytestmark = pytest.mark.asyncio

SOURCE_TEXT = "Hello world, это тест"  # English lead, Russian body → language en


@pytest_asyncio.fixture(autouse=True)
async def _models() -> None:
    await init_models()


class _StepGateway:
    """Deterministic gateway: echoes translation targets, tags other tasks."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transform(
        self, *, task: str, text: str, instruction: str = "", **_: object
    ) -> ChatResponse:
        self.calls.append(task)
        if task == "translation":
            target = (
                instruction.split("на «", 1)[-1].split("»", 1)[0]
                if "на «" in instruction
                else "?"
            )
            out = f"[{target}] {text}"
        else:
            out = f"[{task}] {text}"
        return ChatResponse(
            ok=True,
            text=out,
            provider_used="fake",
            model_used="fake-1",
            attempts=[{"provider": "fake"}],
        )


async def _seed() -> tuple[str, str]:
    """Seed one English source item and one Russian channel; return their ids."""
    async with session_scope() as session:
        source = ContentSource(
            kind="manual",
            reference=SOURCE_TEXT,
            source_language="en",
            target_language="ru",
            auto_detect=True,
        )
        session.add(source)
        await session.flush()
        item = ContentItem(
            source_id=source.id,
            title="E2E",
            text=SOURCE_TEXT,
            cleaned_text=SOURCE_TEXT,
            entities="[]",
            language="en",
            source_language="en",
            target_language="ru",
            status=ContentItemStatus.DRAFT,
        )
        session.add(item)
        channel = Channel(
            reference="@e2e",
            title="E2E Канал",
            username="e2e",
            telegram_id=-100500,
            target_language="ru",
        )
        session.add(channel)
        await session.flush()
        return item.id, channel.id


def _resolver(fake: FakeTelegramBotProvider):
    async def _resolve(channel_id: str):
        return BotPostingProvider(fake), "Тест"

    return _resolve


async def _plan(
    item_id: str,
    channel_id: str,
    *,
    comment: str = "Первый!",
    auto_delete: bool = True,
) -> str:
    async with session_scope() as session:
        ps = PostingService(session)
        pub = (
            await ps.plan(
                item_id,
                [
                    TargetSpec(
                        channel_id=channel_id,
                        scheduled_at=utcnow(),
                        target_language="ru",
                    )
                ],
            )
        )[0]
        session.add(
            CommentPlan(
                publication_id=pub.id,
                item_id=item_id,
                text=comment,
                delay_seconds=0,
                enabled=True,
            )
        )
        if auto_delete:
            pub.delete_at = utcnow()
        await session.flush()
        return pub.id


async def test_full_content_path_english_to_russian_publish_comment_delete() -> None:
    """One item flows en → ru → AI → moderation → schedule → publish → comment →
    delete through the *real* services on fake providers."""
    item_id, channel_id = await _seed()
    gateway = _StepGateway()

    async with session_scope() as session:
        pipeline = ContentPipelineService(session, gateway=gateway)
        await AiProfileService(session).create(
            key="e2e_profile", title="E2E", actions=["rewrite"]
        )

        # 1) Translate English → Russian (target applied, not just stored).
        translated = await pipeline.translate(item_id)
        assert translated.cleaned_text.startswith("[Русский]"), translated.cleaned_text
        assert translated.target_language == "ru"

        # 2) AI processing (rewrite) over the translated text.
        processed = await pipeline.process(item_id, profile_key="e2e_profile")
        assert processed.ai_status == "ok"
        assert processed.cleaned_text.startswith("[rewrite] [Русский]")

        # 3) Human moderation.
        moderated = await pipeline.moderate(item_id, decision="approve")
        assert moderated.status is ContentItemStatus.APPROVED

    pub_id = await _plan(item_id, channel_id)

    # 4) One durable tick: schedule → publish → first comment → auto-delete.
    fake = FakeTelegramBotProvider("123456:AAA")
    fake.script_linked_chat("e2e", 555)
    async with session_scope() as session:
        ps = PostingService(session, resolve_bot_provider=_resolver(fake))
        result = await ps.tick()
        # A zero-delay comment is sent inline on publish (D-116), so it is not
        # counted in the tick's own comment loop.
        assert result == {"published": 1, "deleted": 1, "comments": 0}, result

        pub = await session.get(Publication, pub_id)
        assert pub is not None
        assert pub.status is PublicationStatus.CANCELLED  # deleted after publish
        assert pub.comment_status == "comment_posted"
        assert pub.delete_status == "deleted"

        # The published text is the AI-processed, translated text (target applied).
        assert fake.posts and fake.posts[-1]["text"].startswith("[rewrite] [Русский]")
        assert len(fake.comments) == 1
        assert fake.deleted  # auto-delete reached the provider

    # 5) A restart must not duplicate: a second tick does nothing and no extra
    #    publication rows appear. (The publication is CANCELLED by its
    #    auto-delete, so it is not a candidate for a blind re-publish here.)
    async with session_scope() as session:
        ps = PostingService(session, resolve_bot_provider=_resolver(fake))
        again = await ps.tick()
        assert again == {"published": 0, "deleted": 0, "comments": 0}, again

        from backend.app.db.repositories.content import PublicationRepository

        pubs = await PublicationRepository(session).list_for_item(item_id)
        assert len(pubs) == 1  # idempotent per (item, channel)
        assert len(fake.posts) == 1  # no duplicate post
        assert len(fake.comments) == 1  # no duplicate comment


async def test_restart_does_not_duplicate_a_published_post() -> None:
    """Publishing, then restarting, must not post or comment twice."""
    item_id, channel_id = await _seed()
    pub_id = await _plan(item_id, channel_id, auto_delete=False)

    fake = FakeTelegramBotProvider("123456:AAA")
    fake.script_linked_chat("e2e", 555)

    async with session_scope() as session:
        ps = PostingService(session, resolve_bot_provider=_resolver(fake))
        assert (await ps.tick())["published"] == 1
        # The post is published; re-running the same work (a restart) is a no-op.
        assert (await ps.tick())["published"] == 0
        outcome = await ps.publish(pub_id)
        assert outcome.ok and outcome.message == "Уже опубликовано."
        assert len(fake.posts) == 1
        assert len(fake.comments) == 1


async def test_comment_failure_does_not_fail_publication() -> None:
    """A lost first comment leaves the post PUBLISHED (D-116)."""
    item_id, channel_id = await _seed()
    pub_id = await _plan(item_id, channel_id, auto_delete=False)

    fake = FakeTelegramBotProvider("123456:AAA")
    fake.script_linked_chat("e2e", 555)

    async def _fail_comment(*args, **kwargs):  # type: ignore[no-untyped-def]
        return PostSendResult(ok=False, message="Комментарий не отправлен.")

    fake.send_comment = _fail_comment  # type: ignore[method-assign]

    async with session_scope() as session:
        ps = PostingService(session, resolve_bot_provider=_resolver(fake))
        result = await ps.tick()
        assert result["published"] == 1  # the post itself still succeeded
        assert result["comments"] == 0

        pub = await session.get(Publication, pub_id)
        assert pub is not None
        assert pub.status is PublicationStatus.PUBLISHED
        assert pub.comment_status == "failed"  # COMMENT_FAILED constant
        assert fake.posts  # the post reached the provider


async def test_delete_failure_does_not_fail_publication() -> None:
    """A failed auto-delete keeps the publication history intact (D-116)."""
    item_id, channel_id = await _seed()
    pub_id = await _plan(item_id, channel_id, auto_delete=False)
    # The auto-delete is enabled separately so a *deletion* failure is isolated
    # from the comment (which succeeds here).
    async with session_scope() as session:
        pub = await session.get(Publication, pub_id)
        assert pub is not None
        pub.delete_at = utcnow()
        await session.flush()

    fake = FakeTelegramBotProvider("123456:AAA")
    fake.script_linked_chat("e2e", 555)
    fake.fail_deletion = True

    async with session_scope() as session:
        ps = PostingService(session, resolve_bot_provider=_resolver(fake))
        result = await ps.tick()
        assert result["published"] == 1
        assert result["deleted"] == 0

        pub = await session.get(Publication, pub_id)
        assert pub is not None
        assert pub.status is PublicationStatus.PUBLISHED  # not corrupted
        assert pub.delete_status == "delete_failed"
        assert not fake.deleted


__all__: list[str] = []
