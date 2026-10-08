"""Content Operations 2.0 tests (v1.9).

Covers the AI profiles, the classification/processing/moderation pipeline, the
declarative automation rules, pipeline analytics and the independent
comment/auto-delete statuses. Uses a manual source and a fake AI gateway — no
Telegram access, no credentials, no network.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.ai.gateway.types import ChatResponse
from backend.app.db.models.content import ContentItem, ContentItemStatus, ContentSource
from backend.app.db.models.content_ops import (
    AI_STATUS_OK,
    AI_STATUS_UNAVAILABLE,
)
from backend.app.db.session import session_scope
from backend.app.services.content_pipeline import ContentPipelineService


@pytest_asyncio.fixture(autouse=True)
async def _models() -> None:
    from backend.app.db.session import init_models

    await init_models()


@pytest_asyncio.fixture
async def ops_client() -> AsyncClient:
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_item(text: str = "Спасибо большое за помощь, вы лучшие!") -> str:
    async with session_scope() as session:
        source = ContentSource(kind="manual", reference=text)
        session.add(source)
        await session.flush()
        item = ContentItem(source_id=source.id, text=text, cleaned_text=text)
        session.add(item)
        await session.flush()
        return item.id


class _FakeGateway:
    """A deterministic gateway: every transform succeeds."""

    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[str] = []

    async def transform(
        self, *, task: str, text: str, instruction: str = "", **_: object
    ) -> ChatResponse:
        self.calls.append(task)
        if not self.ok:
            return ChatResponse(ok=False, error="нет провайдера")
        return ChatResponse(
            ok=True,
            text=f"[{task}] {text}",
            provider_used="fake",
            model_used="fake-1",
            fallback_used=False,
            attempts=[{"provider": "fake"}],
        )


# --- AI profiles ----------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_profiles_seeded_and_crud(ops_client: AsyncClient):
    listed = await ops_client.get("/api/v1/content/ai-profiles")
    assert listed.status_code == 200
    keys = {p["key"] for p in listed.json()}
    assert {"news", "neutral", "cynical", "informative", "short", "long", "telegram"} <= keys
    assert all(p["builtin"] for p in listed.json() if p["key"] in keys)

    created = await ops_client.post(
        "/api/v1/content/ai-profiles",
        json={
            "key": "my_profile",
            "title": "Мой профиль",
            "tone": "warm",
            "actions": ["rewrite", "title", "bogus_action"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["key"] == "my_profile"
    # Unknown actions are dropped, never accepted blindly.
    assert body["actions"] == ["rewrite", "title"]

    patched = await ops_client.patch(
        f"/api/v1/content/ai-profiles/{body['id']}", json={"enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    deleted = await ops_client.delete(f"/api/v1/content/ai-profiles/{body['id']}")
    assert deleted.status_code == 204

    # Built-in profiles are protected.
    builtin_id = next(p["id"] for p in listed.json() if p["key"] == "news")
    blocked = await ops_client.delete(f"/api/v1/content/ai-profiles/{builtin_id}")
    assert blocked.status_code == 400


# --- classification -------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_items_advisory(ops_client: AsyncClient):
    item_id = await _make_item("Спасибо большое за помощь, вы лучшие!")
    resp = await ops_client.post(f"/api/v1/content/items/{item_id}/ai/classify")
    assert resp.status_code == 200
    body = resp.json()
    allowed = {
        "donation", "news", "funny", "sad", "angry", "cute", "support",
        "announcement", "neutral",
    }
    assert body["ai_category"] in allowed
    assert body["ai_intent"] in {
        "support", "sympathy", "joy", "humor", "anger", "surprise", "love", "neutral",
    }
    assert body["ai_note"]
    # Intent is advisory and must never be an emoji.
    assert not any(ch in body["ai_intent"] for ch in "\U0001F300-\U0001FAFF")


# --- processing (existing gateway) ----------------------------------------


@pytest.mark.asyncio
async def test_process_uses_gateway_and_sets_ai_processed():
    item_id = await _make_item("Новость дня")
    gateway = _FakeGateway()
    async with session_scope() as session:
        service = ContentPipelineService(session, gateway=gateway)
        item = await service.process(item_id, profile_key="short")
        assert item.ai_status == AI_STATUS_OK
        assert item.status is ContentItemStatus.AI_PROCESSED
        assert item.ai_profile == "short"
        assert item.original_text == "Новость дня"
        assert item.cleaned_text.startswith("[summarize]")
    assert gateway.calls == ["summarize"]


@pytest.mark.asyncio
async def test_process_without_gateway_flags_review():
    item_id = await _make_item("Текст без провайдера")
    gateway = _FakeGateway(ok=False)
    async with session_scope() as session:
        service = ContentPipelineService(session, gateway=gateway)
        item = await service.process(item_id, profile_key="short")
        assert item.ai_status == AI_STATUS_UNAVAILABLE
        assert item.status is ContentItemStatus.NEEDS_REVIEW
        assert "проверьте" in item.ai_note.lower() or "не удалось" in item.ai_note.lower()
        # A failed AI run must never destroy the material.
        assert item.cleaned_text  # still present


# --- moderation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_moderation_decisions(ops_client: AsyncClient):
    item_id = await _make_item("Материал на модерацию")
    approved = await ops_client.post(
        f"/api/v1/content/items/{item_id}/moderate",
        json={"decision": "approve", "note": "ок"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    rejected = await ops_client.post(
        f"/api/v1/content/items/{item_id}/moderate", json={"decision": "reject"}
    )
    assert rejected.json()["status"] == "rejected"

    bad = await ops_client.post(
        f"/api/v1/content/items/{item_id}/moderate", json={"decision": "explode"}
    )
    assert bad.status_code == 400


# --- automation rules -----------------------------------------------------


@pytest.mark.asyncio
async def test_automation_rules_crud_and_apply(ops_client: AsyncClient):
    created = await ops_client.post(
        "/api/v1/content/automation-rules",
        json={
            "name": "Донаты в проверку",
            "source_kind": "manual",
            "condition": {"contains": ["донат"], "min_length": 3},
            "actions": ["rewrite", "review", "bogus"],
            "profile_key": "short",
        },
    )
    assert created.status_code == 201
    rule = created.json()
    assert rule["actions"] == ["rewrite", "review"]
    assert rule["action_titles"] == ["Переписать", "Отправить на проверку"]
    assert rule["condition"] == {"contains": ["донат"], "min_length": 3}

    item_id = await _make_item("Срочный донат на лечение")
    applied = await ops_client.post(f"/api/v1/content/items/{item_id}/apply-rules")
    assert applied.status_code == 200
    # The matching rule rewrote (gateway unavailable → review) then set review.
    assert applied.json()["status"] == "needs_review"

    # A non-matching item is untouched.
    other = await _make_item("Обычная заметка без ключевого слова")
    untouched = await ops_client.post(f"/api/v1/content/items/{other}/apply-rules")
    assert untouched.status_code == 200
    assert untouched.json()["status"] != "needs_review"

    deleted = await ops_client.delete(f"/api/v1/content/automation-rules/{rule['id']}")
    assert deleted.status_code == 204

    empty = await ops_client.post(
        "/api/v1/content/automation-rules", json={"name": "пусто", "actions": []}
    )
    assert empty.status_code == 400


@pytest.mark.asyncio
async def test_rule_condition_vocabulary_is_bounded():
    from backend.app.services.automation_rules import _clean_condition

    cleaned = _clean_condition(
        {"contains": ["a"], "bogus": "x", "min_length": "5", "max_length": "not-a-number"}
    )
    assert cleaned == {"contains": ["a"], "min_length": 5}


# --- pipeline analytics ---------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_analytics_records_stages(ops_client: AsyncClient):
    item_id = await _make_item("Аналитика пайплайна")
    await ops_client.post(f"/api/v1/content/items/{item_id}/ai/classify")
    await ops_client.post(
        f"/api/v1/content/items/{item_id}/moderate", json={"decision": "approve"}
    )
    analytics = await ops_client.get("/api/v1/content/pipeline/analytics")
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["stage_counts"].get("ai", 0) >= 1
    assert body["stage_counts"].get("moderation", 0) >= 1
    assert any(r["stage"] == "ai" for r in body["recent"])


# --- publishing status tracking -------------------------------------------


@pytest.mark.asyncio
async def test_comment_and_delete_status_tracked_independently():
    """A lost comment never marks the post failed (D-116)."""
    from backend.app.db.models.content import (
        CommentPlan,
        Publication,
        PublicationStatus,
    )
    from backend.app.services import posting_service as ps

    item_id = await _make_item("Пост с комментарием")
    async with session_scope() as session:
        item = await session.get(ContentItem, item_id)
        pub = Publication(
            item_id=item_id,
            channel_id="ch1",
            channel_username="chan",
            status=PublicationStatus.PUBLISHED,
            telegram_message_ids="[10]",
        )
        session.add(pub)
        await session.flush()
        plan = CommentPlan(publication_id=pub.id, enabled=True, text="Первый!", delay_seconds=0)
        session.add(plan)
        await session.flush()

        service = ps.PostingService(session)
        # User mode cannot comment → the post stays published.
        await service._after_publish(item, pub, ps._NullPostingProvider(), "user")
        assert pub.status is PublicationStatus.PUBLISHED
        assert pub.comment_status == ps.COMMENT_NOT_SUPPORTED


__all__: list[str] = []
