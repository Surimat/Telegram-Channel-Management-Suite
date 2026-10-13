"""Content Pipeline Consolidation regression guard (D-126).

``ContentPipelineService`` is the single authoritative content-*processing*
engine and ``ContentService`` the single *receive/dedup* engine; ``PostingService``
remains the single *publish* engine. These integration tests drive the real
services end to end (temporary SQLite DB, fake AI gateway, fake bot provider —
no Telegram access, no credentials, no network) and prove:

* there is one processing path: the v1.2 ``/rewrite`` contract delegates to the
  pipeline, so the two engines cannot drift;
* the whole pipeline works: grab → process/translate → moderate → publish →
  comment/delete, with the processed text actually published;
* a restart (a repeated ``plan``/``tick``) never duplicates;
* the target language survives the path;
* an AI failure never destroys material and can be recovered by moderation;
* cross-cutting guards are untouched: the v1.2 API contract stays valid and the
  D-124 module gate still refuses a disabled module.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.ai.gateway.types import ChatResponse
from backend.app.db.base import utcnow
from backend.app.db.models.channel import Channel, ChannelKind
from backend.app.db.models.content import (
    CommentPlan,
    ContentItem,
    ContentItemStatus,
)
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.db.repositories.content import PublicationRepository
from backend.app.db.session import init_models, session_scope
from backend.app.providers.fake_bot import FakeTelegramBotProvider
from backend.app.providers.posting import BotPostingProvider
from backend.app.services.channel_modules import (
    MODULE_REACTIONS,
    ChannelModuleDisabledError,
)
from backend.app.services.content_pipeline import ContentPipelineService
from backend.app.services.content_service import ContentService
from backend.app.services.posting_service import PostingService, TargetSpec
from backend.app.services.reaction_service import ReactionService

pytestmark = pytest.mark.asyncio

SOURCE_TEXT = "Hello world, это тест"  # English lead → language en


@pytest_asyncio.fixture(autouse=True)
async def _models() -> None:
    await init_models()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    from backend.app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class _StepGateway:
    """Deterministic gateway: echoes a translation target, tags other tasks."""

    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[str] = []

    async def transform(
        self, *, task: str, text: str, instruction: str = "", **_: object
    ) -> ChatResponse:
        self.calls.append(task)
        if not self.ok:
            return ChatResponse(ok=False, error="нет провайдера")
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


def _bot_resolver(fake: FakeTelegramBotProvider):
    async def _resolve(channel_id: str):
        return BotPostingProvider(fake), "Тест"

    return _resolve


async def _seed_item(
    text: str = SOURCE_TEXT,
    *,
    source_language: str = "en",
    target_language: str = "ru",
    language: str = "en",
    status: ContentItemStatus = ContentItemStatus.DRAFT,
) -> str:
    async with session_scope() as session:
        source = await ContentService(session).create_source(
            kind="manual", reference=text
        )
        item = ContentItem(
            source_id=source.id,
            title="Consolidation",
            text=text,
            cleaned_text=text,
            entities="[]",
            language=language,
            source_language=source_language,
            target_language=target_language,
            status=status,
        )
        session.add(item)
        await session.flush()
        return item.id


async def _seed_channel(reference: str = "@cons") -> str:
    async with session_scope() as session:
        channel = Channel(
            reference=reference,
            title="Consolidation Канал",
            username=reference.lstrip("@"),
            telegram_id=-100777,
            target_language="ru",
        )
        session.add(channel)
        await session.flush()
        return channel.id


async def _plan(item_id: str, channel_id: str, *, auto_delete: bool = True) -> str:
    async with session_scope() as session:
        pub = (
            await PostingService(session).plan(
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
                text="Первый!",
                delay_seconds=0,
                enabled=True,
            )
        )
        if auto_delete:
            pub.delete_at = utcnow()
        await session.flush()
        return pub.id


# ---------------------------------------------------------------------------
# 1. One processing engine: the v1.2 /rewrite contract delegates (no drift)
# ---------------------------------------------------------------------------
async def test_rewrite_delegates_to_the_single_pipeline(monkeypatch):
    item_id = await _seed_item(text="Обычный текст", status=ContentItemStatus.DRAFT)
    calls: list[str] = []
    original = ContentPipelineService.rewrite_preview

    async def _spy(self, item_id: str, *, mode: str):
        calls.append(mode)
        return await original(self, item_id, mode=mode)

    monkeypatch.setattr(ContentPipelineService, "rewrite_preview", _spy)
    async with session_scope() as session:
        result = await ContentService(session).rewrite_preview(item_id, mode="rephrase")
    # The v1.2 contract is preserved by delegating to the pipeline owner.
    assert calls == ["rephrase"]
    assert result.ok is False
    assert "Рерайт недоступен" in result.message


# ---------------------------------------------------------------------------
# 2. The whole path works and publishes the processed text
# ---------------------------------------------------------------------------
async def test_processing_then_publish_uses_processed_text():
    item_id = await _seed_item()
    channel_id = await _seed_channel("@cons2")

    async with session_scope() as session:
        pipeline = ContentPipelineService(session, gateway=_StepGateway())
        item = await pipeline.process(item_id, profile_key="short")
        assert item.ai_status == "ok"
        assert item.status is ContentItemStatus.AI_PROCESSED

    await _plan(item_id, channel_id)
    fake = FakeTelegramBotProvider("123456:AAA")
    fake.script_linked_chat("cons2", 555)
    async with session_scope() as session:
        result = await PostingService(
            session, resolve_bot_provider=_bot_resolver(fake)
        ).tick()
        assert result["published"] == 1
        assert fake.posts and fake.posts[-1]["text"].startswith("[summarize]")


# ---------------------------------------------------------------------------
# 3. A restart never duplicates
# ---------------------------------------------------------------------------
async def test_restart_never_duplicates_after_consolidation():
    item_id = await _seed_item()
    channel_id = await _seed_channel("@cons3")

    async with session_scope() as session:
        await ContentPipelineService(session, gateway=_StepGateway()).moderate(
            item_id, decision="approve"
        )

    await _plan(item_id, channel_id, auto_delete=False)
    fake = FakeTelegramBotProvider("123456:AAA")
    fake.script_linked_chat("cons3", 555)
    async with session_scope() as session:
        service = PostingService(session, resolve_bot_provider=_bot_resolver(fake))
        assert (await service.tick())["published"] == 1
        assert (await service.tick())["published"] == 0
        assert len(fake.posts) == 1

    # Planning the same (item, channel) again is idempotent.
    await _plan(item_id, channel_id, auto_delete=False)
    async with session_scope() as session:
        pubs = await PublicationRepository(session).list_for_item(item_id)
        assert len(pubs) == 1


# ---------------------------------------------------------------------------
# 4. Translation + target language survive the path
# ---------------------------------------------------------------------------
async def test_translation_and_target_language_survive():
    item_id = await _seed_item()
    async with session_scope() as session:
        pipeline = ContentPipelineService(session, gateway=_StepGateway())
        translated = await pipeline.translate(item_id)
        assert translated.cleaned_text.startswith("[Русский]")
        assert translated.target_language == "ru"
        processed = await pipeline.process(item_id, profile_key="short")
        assert processed.cleaned_text.startswith("[summarize] [Русский]")
        assert processed.target_language == "ru"


# ---------------------------------------------------------------------------
# 5. An AI failure never loses material and can be recovered
# ---------------------------------------------------------------------------
async def test_ai_failure_is_recoverable():
    item_id = await _seed_item(text="Текст без провайдера")
    async with session_scope() as session:
        pipeline = ContentPipelineService(session, gateway=_StepGateway(ok=False))
        item = await pipeline.process(item_id, profile_key="short")
        assert item.ai_status == "ai_unavailable"
        assert item.status is ContentItemStatus.NEEDS_REVIEW
        # Material is intact.
        assert (item.cleaned_text or item.text) == "Текст без провайдера"
        assert item.original_text == "Текст без провайдера"

        recovered = await pipeline.moderate(item_id, decision="approve")
        assert recovered.status is ContentItemStatus.APPROVED


# ---------------------------------------------------------------------------
# 6. v1.2 API contract stays valid through the single engine
# ---------------------------------------------------------------------------
async def test_v12_api_contract_still_valid(client: AsyncClient):
    created = await client.post(
        "/api/v1/content/sources",
        json={"kind": "manual", "reference": "Текст через API"},
    )
    assert created.status_code == 201
    grabbed = await client.post(
        f"/api/v1/content/sources/{created.json()['id']}/grab"
    )
    item_id = grabbed.json()["item_ids"][0]

    # /clean, /rewrite and /ai/process keep their documented behaviour.
    assert (await client.get(f"/api/v1/content/items/{item_id}/clean")).status_code == 200
    rewrite = await client.post(
        f"/api/v1/content/items/{item_id}/rewrite", json={"mode": "rephrase"}
    )
    assert rewrite.status_code == 200 and rewrite.json()["ok"] is False
    assert "Рерайт недоступен" in rewrite.json()["message"]

    processed = await client.post(
        f"/api/v1/content/items/{item_id}/ai/process", json={"profile_key": "short"}
    )
    assert processed.status_code == 200
    body = processed.json()
    # No live provider in tests → honest needs_review, material preserved.
    assert body["status"] == "needs_review"
    assert body["ai_status"] == "ai_unavailable"
    assert (body["cleaned_text"] or body["text"]) == "Текст через API"


# ---------------------------------------------------------------------------
# 7. Cross-module guard untouched: a disabled module still gates (D-124)
# ---------------------------------------------------------------------------
async def test_disabled_module_still_gates_after_consolidation():
    async with session_scope() as session:
        await ChannelRepository(session).add(
            Channel(
                id="ch-cons-off",
                reference="@consoff",
                username="consoff",
                kind=ChannelKind.CHANNEL,
                modules=json.dumps({MODULE_REACTIONS: False}),
            )
        )
    async with session_scope() as session:
        with pytest.raises(ChannelModuleDisabledError):
            await ReactionService(session).ingest_post(
                text="новость", registry_channel_id="ch-cons-off", seed=1
            )


__all__: list[str] = []
