"""v2.0 Target Language tests.

Covers language detection, target resolution precedence, protected-span
translation (links/usernames/hashtags survive), the translate pipeline action,
the language API surface, per-channel target language and the free web-wrapper
backup templates. Uses a fake AI gateway — no Telegram access, no network.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from backend.app.ai.gateway.types import ChatResponse
from backend.app.db.models.content import ContentItem, ContentItemStatus, ContentSource
from backend.app.db.models.content_ops import AI_STATUS_OK
from backend.app.db.session import session_scope
from backend.app.services.content_language import (
    LANG_AUTO,
    ContentLanguageService,
    detect_language,
    needs_translation,
    normalize_language,
    protect_text,
    resolve_target,
)
from backend.app.services.content_pipeline import ContentPipelineService


@pytest_asyncio.fixture(autouse=True)
async def _models() -> None:
    from backend.app.db.session import init_models

    await init_models()


class _EchoGateway:
    """Echoes the (masked) text back, tagging the task — deterministic."""

    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[str] = []
        self.last_text = ""

    async def transform(
        self, *, task: str, text: str, instruction: str = "", **_: object
    ) -> ChatResponse:
        self.calls.append(task)
        self.last_text = text
        if not self.ok:
            return ChatResponse(ok=False, error="нет провайдера")
        return ChatResponse(
            ok=True,
            text=text,
            provider_used="fake",
            model_used="fake-1",
            attempts=[{"provider": "fake"}],
        )


class _TargetAwareGateway:
    """A gateway whose *output depends on the target language* in the instruction.

    It stamps the destination-language title that
    :func:`translation_instruction` embedded into the prompt. A test can then
    prove that changing ``target_language`` changes the produced text, rather
    than only changing a stored field.
    """

    async def transform(
        self, *, task: str, text: str, instruction: str = "", **_: object
    ) -> ChatResponse:
        # instruction looks like: "Переведи текст с языка «X» на «Y», ..."
        target = instruction.split("на «", 1)[-1].split("»", 1)[0] if "на «" in instruction else "?"
        return ChatResponse(
            ok=True,
            text=f"[{target}] {text}",
            provider_used="fake",
            model_used="fake-1",
            attempts=[{"provider": "fake"}],
        )


async def _get_item(session, item_id: str):  # type: ignore[no-untyped-def]
    from backend.app.db.repositories.content import ContentItemRepository

    return await ContentItemRepository(session).get(item_id)


async def _make_item(
    text: str = "Hello world",
    *,
    source_language: str = "en",
    target_language: str = "ru",
    language: str | None = None,
) -> str:
    async with session_scope() as session:
        source = ContentSource(
            kind="manual",
            reference=text,
            source_language=source_language,
            target_language=target_language,
        )
        session.add(source)
        await session.flush()
        item = ContentItem(
            source_id=source.id,
            text=text,
            cleaned_text=text,
            language=language if language is not None else source_language,
            source_language=source_language,
            target_language=target_language,
        )
        session.add(item)
        await session.flush()
        return item.id


@pytest_asyncio.fixture
async def lang_client() -> AsyncClient:
    """API client whose pipeline is wired to a deterministic fake gateway."""
    from backend.app.api.deps import get_content_pipeline_service, get_session
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()

    def _pipeline(session=Depends(get_session)):
        return ContentPipelineService(session, gateway=_EchoGateway())

    app.dependency_overrides[get_content_pipeline_service] = _pipeline
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- pure language helpers -------------------------------------------------


def test_detect_language_script_guess():
    assert detect_language("Привет, как дела?") == "ru"
    assert detect_language("Hello, how are you?") == "en"
    assert detect_language("Привіт, як справи?") == "uk"
    assert detect_language("你好，世界") == "zh"
    assert detect_language("こんにちは世界") == "ja"
    # Empty text falls back to the safe default, never an exception.
    assert detect_language("") == "ru"


def test_normalize_language_accepts_locales():
    assert normalize_language("ru-RU") == "ru"
    assert normalize_language("EN_us") == "en"
    assert normalize_language("auto") == LANG_AUTO
    assert normalize_language("") == "ru"


def test_resolve_target_precedence():
    # A concrete publication target wins over every lower level.
    assert (
        resolve_target(publication="de", channel="en", source="ru", global_default="ru")
        == "de"
    )
    # "auto" and "" fall through to the next level.
    assert resolve_target(publication="auto", channel="en", source="ru") == "en"
    assert (
        resolve_target(publication="", channel="auto", source="uk", global_default="ru")
        == "uk"
    )
    assert resolve_target(publication="", channel="", source="auto", global_default="en") == "en"
    # Never returns "auto" — a target must be concrete.
    assert resolve_target(publication="auto", channel="auto", source="auto") == "ru"


def test_needs_translation_only_when_different():
    assert needs_translation("en", "ru") is True
    assert needs_translation("ru", "ru") is False
    assert needs_translation("auto", "ru") is True


def test_protect_and_restore_roundtrip():
    text = "Смотри https://t.me/chan и @author #news дальше"
    protected = protect_text(text)
    # The protected spans are gone from the masked text…
    assert "https://t.me/chan" not in protected.masked
    assert "@author" not in protected.masked
    assert "#news" not in protected.masked
    # …and come back verbatim on restore.
    assert protected.restore(protected.masked) == text


# --- translation through the gateway --------------------------------------


@pytest.mark.asyncio
async def test_translate_masks_protected_spans_and_restores():
    item_id = await _make_item("Read https://t.me/chan by @author #news now")
    gateway = _EchoGateway()
    async with session_scope() as session:
        service = ContentLanguageService(session, gateway=gateway)
        item = await _get_item(session, item_id)
        outcome = await service.translate(item, target_language="ru")
    assert outcome.translated is True
    # The gateway saw masked placeholders, never the raw link/username.
    assert "https://t.me/chan" not in gateway.last_text
    assert "@author" not in gateway.last_text
    # The restored result is identical to the original for an echo gateway.
    assert outcome.text == "Read https://t.me/chan by @author #news now"


@pytest.mark.asyncio
async def test_translate_noop_when_same_language():
    item_id = await _make_item("Привет мир", source_language="ru", target_language="ru")
    gateway = _EchoGateway()
    async with session_scope() as session:
        service = ContentLanguageService(session, gateway=gateway)
        item = await _get_item(session, item_id)
        outcome = await service.translate(item, target_language="ru")
    assert outcome.translated is False
    assert "не требуется" in outcome.detail
    assert gateway.calls == []  # no pointless AI call


@pytest.mark.asyncio
async def test_translate_failure_never_loses_material():
    item_id = await _make_item("Hello world", source_language="en", target_language="ru")
    gateway = _EchoGateway(ok=False)
    async with session_scope() as session:
        service = ContentLanguageService(session, gateway=gateway)
        item = await _get_item(session, item_id)
        outcome = await service.translate(item, target_language="ru")
    assert outcome.translated is False
    assert outcome.text == "Hello world"  # original text preserved


# --- target language actually changes the output ---------------------------


@pytest.mark.asyncio
async def test_target_language_changes_output_not_just_stored():
    """The end-to-end v2.0 question: does ``target_language`` affect the text?

    Two identical English items are translated to different targets. Because the
    gateway echoes the destination title embedded in the instruction, the saved
    text must differ — proving the target is *applied*, not merely persisted.
    """
    async with session_scope() as session:
        service = ContentPipelineService(session, gateway=_TargetAwareGateway())
        ru_id = await _make_item("Hello world", source_language="en", target_language="ru")
        de_id = await _make_item("Hello world", source_language="en", target_language="de")
        ru_item = await service.translate(ru_id)
        de_item = await service.translate(de_id)

    assert ru_item.cleaned_text == "[Русский] Hello world"
    assert de_item.cleaned_text == "[Немецкий] Hello world"
    assert ru_item.cleaned_text != de_item.cleaned_text
    # The declared target is preserved and reflected on the item.
    assert ru_item.target_language == "ru"
    assert de_item.target_language == "de"


@pytest.mark.asyncio
async def test_source_auto_detects_english_then_translates_to_russian():
    """English source → auto-detect → translate to Russian (scenario A core)."""
    item_id = await _make_item(
        "Hello world, this is a news post.",
        source_language="auto",
        target_language="ru",
        language="auto",
    )
    async with session_scope() as session:
        service = ContentPipelineService(session, gateway=_TargetAwareGateway())
        item = await service.detect_language(item_id)
        assert item.source_language == "en"  # detected, not assumed
        item = await service.translate(item_id)

    assert item.source_language == "en"
    assert item.target_language == "ru"
    assert item.cleaned_text.startswith("[Русский]")


# --- pipeline action -------------------------------------------------------


@pytest.mark.asyncio
async def test_process_translate_action_preserves_protected_spans():
    item_id = await _make_item("Hello https://t.me/chan @author")
    gateway = _EchoGateway()
    async with session_scope() as session:
        from backend.app.services.ai_profiles import AiProfileService

        profiles = AiProfileService(session)
        await profiles.create(
            key="translate_only", title="Только перевод", actions=["translate"]
        )
        service = ContentPipelineService(session, gateway=gateway, profiles=profiles)
        item = await service.process(item_id, profile_key="translate_only")
    assert gateway.calls == ["translation"]
    assert "https://t.me/chan" not in gateway.last_text
    # The echo gateway returns the masked text; restore puts the link back.
    assert "https://t.me/chan" in item.cleaned_text
    assert "@author" in item.cleaned_text
    assert item.ai_status == AI_STATUS_OK


@pytest.mark.asyncio
async def test_process_translate_only_profile_is_ok_when_languages_match():
    item_id = await _make_item("Привет мир", source_language="ru", target_language="ru")
    gateway = _EchoGateway()
    async with session_scope() as session:
        from backend.app.services.ai_profiles import AiProfileService

        profiles = AiProfileService(session)
        await profiles.create(
            key="translate_only", title="Только перевод", actions=["translate"]
        )
        service = ContentPipelineService(session, gateway=gateway, profiles=profiles)
        item = await service.process(item_id, profile_key="translate_only")
        # A no-op translation is a success, not an "AI unavailable" failure.
        assert item.ai_status == AI_STATUS_OK
        assert item.status is ContentItemStatus.AI_PROCESSED


# --- API surface -----------------------------------------------------------


@pytest.mark.asyncio
async def test_language_catalog_api(lang_client: AsyncClient):
    resp = await lang_client.get("/api/v1/content/languages")
    assert resp.status_code == 200
    body = resp.json()
    codes = {item["code"] for item in body["languages"]}
    assert {"auto", "ru", "en", "uk"} <= codes
    assert body["default"] == "ru"


@pytest.mark.asyncio
async def test_detect_and_translate_endpoints(lang_client: AsyncClient):
    item_id = await _make_item("Hello https://t.me/chan @author")
    detected = await lang_client.post(f"/api/v1/content/items/{item_id}/language")
    assert detected.status_code == 200
    assert detected.json()["source_language"] == "en"

    translated = await lang_client.post(
        f"/api/v1/content/items/{item_id}/translate", json={"target_language": "ru"}
    )
    assert translated.status_code == 200
    body = translated.json()
    assert body["translated"] is True
    assert body["provider"] == "fake"


@pytest.mark.asyncio
async def test_source_carries_language_fields(lang_client: AsyncClient):
    created = await lang_client.post(
        "/api/v1/content/sources",
        json={
            "kind": "manual",
            "reference": "источник",
            "source_language": "en",
            "target_language": "de",
            "auto_detect": False,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["source_language"] == "en"
    assert body["target_language"] == "de"
    assert body["auto_detect"] is False


# --- channel target language ----------------------------------------------


@pytest.mark.asyncio
async def test_channel_target_language_update(channel_client: AsyncClient):
    created = await channel_client.post(
        "/api/v1/channels", json={"reference": "@langchan", "title": "Lang"}
    )
    assert created.status_code == 201
    channel_id = created.json()["id"]
    assert created.json()["target_language"] == "auto"

    patched = await channel_client.patch(
        f"/api/v1/channels/{channel_id}", json={"target_language": "en"}
    )
    assert patched.status_code == 200
    assert patched.json()["target_language"] == "en"


# --- bot factory fan-out binding ------------------------------------------


@pytest.mark.asyncio
async def test_bind_many_requires_channels(bot_client: AsyncClient):
    created = await bot_client.post(
        "/api/v1/bot-factory/batches", json={"prefix": "Mix", "count": 2}
    )
    assert created.status_code == 201
    batch_id = created.json()["batch"]["id"]

    empty = await bot_client.post(
        f"/api/v1/bot-factory/batches/{batch_id}/bind-many", json={"channel_ids": []}
    )
    assert empty.status_code == 400


# --- per-publication target language --------------------------------------


@pytest.mark.asyncio
async def test_plan_persists_target_language_on_publication(lang_client: AsyncClient):
    channel = await lang_client.post(
        "/api/v1/channels", json={"reference": "@pubchan", "title": "Pub"}
    )
    channel_id = channel.json()["id"]
    item_id = await _make_item("Hello world")

    planned = await lang_client.post(
        f"/api/v1/content/items/{item_id}/plan",
        json={"targets": [{"channel_id": channel_id, "target_language": "de"}]},
    )
    assert planned.status_code == 200, planned.text
    assert planned.json()["publications"][0]["target_language"] == "de"


# --- free wrapper backup templates ----------------------------------------


@pytest.mark.asyncio
async def test_wrapper_library_includes_free_backups(lang_client: AsyncClient):
    resp = await lang_client.get("/api/v1/ai-gateway/wrappers")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert {"generic", "chatgpt", "gemini"} <= ids
