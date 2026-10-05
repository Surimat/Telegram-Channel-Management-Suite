"""Content Studio foundation tests (v1.2): sources, grabber, dedup, cleaner, rights.

No real network or credentials: RSS/Atom parsing uses in-memory XML, and the
Telegram grabber uses the deterministic fake session provider.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.providers.content_base import ContentQuery
from backend.app.providers.content_sources import (
    AtomContentProvider,
    ManualContentProvider,
    RssContentProvider,
    parse_feed,
)
from backend.app.services.content_cleaner import clean_text
from backend.app.services.content_service import (
    ContentService,
    content_hash,
    source_hash,
)

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test Feed</title>
  <item>
    <title>First</title>
    <link>https://example.com/1?utm_source=x&amp;utm_medium=y</link>
    <description>Hello &lt;b&gt;world&lt;/b&gt;</description>
    <pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>
    <guid>item-1</guid>
  </item>
  <item>
    <title>Second</title>
    <link>https://example.com/2</link>
    <description>Another</description>
    <guid>item-2</guid>
  </item>
</channel></rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Entry A</title>
    <link href="https://example.com/a" rel="alternate"/>
    <summary>Summary A</summary>
    <id>tag:example.com,2026:a</id>
    <updated>2026-10-05T10:00:00Z</updated>
  </entry>
</feed>
"""


def test_parse_rss_feed():
    parsed = parse_feed(RSS_XML, kind="rss", reference="https://example.com/rss", limit=10)
    assert parsed.title == "Test Feed"
    assert len(parsed.items) == 2
    assert parsed.items[0].text == "Hello world"
    assert parsed.items[0].extra["guid"] == "item-1"


def test_parse_atom_feed():
    parsed = parse_feed(ATOM_XML, kind="atom", reference="https://example.com/atom", limit=10)
    assert parsed.title == "Atom Feed"
    assert parsed.items[0].source_url == "https://example.com/a"


@pytest.mark.asyncio
async def test_manual_provider_accepts_plain_text():
    provider = ManualContentProvider()
    result = await provider.fetch(ContentQuery(reference="Просто текст"), state={})
    assert result.ok
    assert result.items[0].text == "Просто текст"


@pytest.mark.asyncio
async def test_rss_provider_incremental_state():
    provider = RssContentProvider()

    # First run sees both items.
    async def fake_download(url, state):
        return RSS_XML, "etag-1", "lm-1", 200, ""

    provider._download = fake_download  # type: ignore[assignment]
    first = await provider.fetch(ContentQuery(reference="https://example.com/rss"), state={})
    assert first.ok and len(first.items) == 2
    assert first.etag == "etag-1"

    # Second run with last_seen_item returns only newer items.
    second = await provider.fetch(
        ContentQuery(reference="https://example.com/rss"),
        state={"last_seen_item": "item-2"},
    )
    assert len(second.items) == 1
    assert second.items[0].extra["guid"] == "item-1"


@pytest.mark.asyncio
async def test_rss_provider_handles_304():
    provider = RssContentProvider()

    async def fake_download(url, state):
        return "", state.get("etag", ""), state.get("last_modified", ""), 304, ""

    provider._download = fake_download  # type: ignore[assignment]
    result = await provider.fetch(
        ContentQuery(reference="https://example.com/rss"),
        state={"etag": "etag-1", "last_modified": "lm-1"},
    )
    assert result.ok
    assert result.items == []


def test_cleaner_removes_ads_cta_and_tracking():
    text = (
        "Заголовок новости\n"
        "Полезный текст.\n"
        "Реклама: промокод SUMMER\n"
        "Подписывайтесь на канал!\n"
        "Ссылка https://example.com/page?utm_source=telegram&id=5\n"
        "---\n"
    )
    result = clean_text(text)
    assert "Реклама" not in result.cleaned
    assert "Подписывайтесь" not in result.cleaned
    assert "utm_source" not in result.cleaned
    assert "id=5" in result.cleaned
    assert result.changed
    assert result.removed_lines >= 3


def test_cleaner_never_deletes_silently():
    result = clean_text("Обычный текст без мусора.")
    assert result.cleaned == "Обычный текст без мусора."
    assert result.changes == []


def test_content_hash_is_whitespace_insensitive():
    assert content_hash("Привет   мир") == content_hash("привет мир")


def test_source_hash_deterministic():
    a = source_hash("rss", "https://x", None, "guid-1")
    b = source_hash("rss", "https://x", None, "guid-1")
    assert a == b
    assert a != source_hash("rss", "https://x", None, "guid-2")


@pytest_asyncio.fixture
async def content_service() -> ContentService:
    from backend.app.db.session import init_models, session_scope

    await init_models()
    async with session_scope() as session:
        yield ContentService(session)


@pytest.mark.asyncio
async def test_grab_deduplicates(content_service: ContentService):
    source = await content_service.create_source(
        kind="manual", reference="Текст материала"
    )
    first = await content_service.grab(source.id)
    assert first.ok
    assert first.new_items == 1
    # The same manual reference has a stable source hash → duplicate.
    second = await content_service.grab(source.id)
    assert second.new_items == 0
    assert second.duplicates == 1


@pytest.mark.asyncio
async def test_clean_and_rights_flow(content_service: ContentService):
    source = await content_service.create_source(kind="manual", reference="Текст с рекламой")
    outcome = await content_service.grab(source.id)
    item_id = outcome.item_ids[0]

    preview = await content_service.clean_preview(item_id)
    assert preview.original == "Текст с рекламой"

    item = await content_service.apply_clean(item_id)
    assert item.cleaned_text

    # Rights unknown → warning shown (never silent).
    assert "права" in content_service.rights_warning(item).lower()
    await content_service.update_item(item_id, rights_status="own")
    item = await content_service.get_item(item_id)
    assert content_service.rights_warning(item) == ""


@pytest.mark.asyncio
async def test_telegram_source_protected_keeps_only_link():
    from backend.app.db.session import init_models, session_scope
    from backend.app.providers.fake_session import FakeContentScenario, FakeSessionProvider

    await init_models()
    fake = FakeSessionProvider(content=FakeContentScenario(protected=True))

    async def _resolve(account_id: str = ""):  # type: ignore[no-untyped-def]
        return fake

    async with session_scope() as session:
        service = ContentService(session, resolve_provider=_resolve)
        source = await service.create_source(kind="telegram", reference="protectedchan")
        outcome = await service.grab(source.id)
        assert outcome.ok
        assert outcome.protected
        assert "нельзя автоматически получить" in outcome.message
        assert outcome.new_items == 0


@pytest.mark.asyncio
async def test_telegram_source_fake_grab_and_dedup():
    from backend.app.db.session import init_models, session_scope
    from backend.app.providers.fake_session import FakeContentScenario, FakeSessionProvider

    await init_models()
    fake = FakeSessionProvider(
        content=FakeContentScenario(
            messages=[
                {"message_id": 11, "text": "Первый пост", "url": "https://t.me/c/11"},
                {"message_id": 12, "text": "Второй пост", "url": "https://t.me/c/12"},
            ]
        )
    )

    async def _resolve(account_id: str = ""):  # type: ignore[no-untyped-def]
        return fake

    async with session_scope() as session:
        service = ContentService(session, resolve_provider=_resolve)
        source = await service.create_source(kind="telegram", reference="fakechannel")
        outcome = await service.grab(source.id)
        assert outcome.new_items == 2
        # Grabbing again is incremental: the source is caught up, nothing new.
        again = await service.grab(source.id)
        assert again.new_items == 0
        # Re-reading from the start (state reset) deduplicates by message id.
        source = await service.sources.get(source.id)
        source.last_seen_item = ""
        await session.flush()
        reread = await service.grab(source.id)
        assert reread.new_items == 0
        assert reread.duplicates == 2


@pytest.mark.asyncio
async def test_attribution_and_publish_text(content_service: ContentService):
    source = await content_service.create_source(kind="manual", reference="Материал для атрибуции")
    outcome = await content_service.grab(source.id)
    item = await content_service.get_item(outcome.item_ids[0])
    item.source_channel = "Канал-источник"
    item.source_url = "https://t.me/source/1"
    text = content_service.publish_text(item)
    assert "Канал-источник" in text
    assert "https://t.me/source/1" in text
    # Attribution can be disabled explicitly.
    item.attribution_enabled = False
    assert "Канал-источник" not in content_service.publish_text(item)


def test_atom_provider_available():
    assert AtomContentProvider().available() == (True, "")
