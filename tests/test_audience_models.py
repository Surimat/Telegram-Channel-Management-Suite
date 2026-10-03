"""Audience data-model, repository and deduplication tests (PHASE 5)."""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.db.models.audience import (
    AudienceSource,
    AudienceUser,
    Completeness,
    MemberStatus,
    ScanStatus,
    SourceType,
    SourceUserLink,
)


@pytest_asyncio.fixture
async def db():
    from backend.app.db.session import dispose_engine, init_models, session_scope

    await init_models()
    async with session_scope() as session:
        yield session
    await dispose_engine()


async def test_source_defaults(db) -> None:
    from backend.app.db.repositories.audience import AudienceSourceRepository

    repo = AudienceSourceRepository(db)
    source = await repo.add(
        AudienceSource(reference="@durov", username="durov", source_type=SourceType.CHANNEL)
    )
    assert source.id
    assert source.scan_status == ScanStatus.IDLE
    assert source.completeness == Completeness.UNKNOWN
    assert source.enabled is True
    assert source.discovered_count == 0


async def test_source_unique_telegram_id(db) -> None:
    from sqlalchemy.exc import IntegrityError

    from backend.app.db.repositories.audience import AudienceSourceRepository

    repo = AudienceSourceRepository(db)
    await repo.add(AudienceSource(reference="a", telegram_id=555, title="A"))
    with pytest.raises(IntegrityError):
        await repo.add(AudienceSource(reference="b", telegram_id=555, title="B"))
    await db.rollback()


async def test_source_list_search_and_counts(db) -> None:
    from backend.app.db.repositories.audience import AudienceSourceRepository

    repo = AudienceSourceRepository(db)
    await repo.add(AudienceSource(reference="@news", username="news", title="Новости"))
    await repo.add(AudienceSource(reference="@chat", username="chat", title="Чат"))
    rows, total = await repo.list(search="новост")
    assert total == 1
    assert rows[0].username == "news"
    assert await repo.count() == 2


async def test_user_unique_telegram_id(db) -> None:
    from sqlalchemy.exc import IntegrityError

    from backend.app.db.repositories.audience import AudienceUserRepository

    repo = AudienceUserRepository(db)
    await repo.add(AudienceUser(telegram_user_id=42, username="a"))
    with pytest.raises(IntegrityError):
        await repo.add(AudienceUser(telegram_user_id=42, username="b"))
    await db.rollback()


async def test_source_user_link_is_many_to_many(db) -> None:
    from backend.app.db.repositories.audience import (
        AudienceSourceRepository,
        AudienceUserRepository,
        SourceUserLinkRepository,
    )

    sources = AudienceSourceRepository(db)
    users = AudienceUserRepository(db)
    links = SourceUserLinkRepository(db)

    s1 = await sources.add(AudienceSource(reference="s1", telegram_id=1))
    s2 = await sources.add(AudienceSource(reference="s2", telegram_id=2))
    u = await users.add(AudienceUser(telegram_user_id=7, username="seven"))

    # One user linked to two sources.
    await links.add(SourceUserLink(source_id=s1.id, user_id=u.id))
    await links.add(SourceUserLink(source_id=s2.id, user_id=u.id))

    assert await links.count_for_user(u.id) == 2
    assert sorted(await links.source_ids_for_user(u.id)) == sorted([s1.id, s2.id])
    assert await links.count_for_source(s1.id) == 1


async def test_deduplication_get_many(db) -> None:
    from backend.app.db.repositories.audience import AudienceUserRepository

    repo = AudienceUserRepository(db)
    await repo.add(AudienceUser(telegram_user_id=1, username="one"))
    await repo.add(AudienceUser(telegram_user_id=2, username="two"))
    found = await repo.get_many_by_telegram_ids([1, 2, 3])
    assert set(found.keys()) == {1, 2}

    # One row per Telegram id (the unique constraint is the dedup guarantee).
    assert await repo.count_unique() == 2


async def test_user_filters(db) -> None:
    from backend.app.db.repositories.audience import AudienceUserRepository

    repo = AudienceUserRepository(db)
    await repo.add(
        AudienceUser(telegram_user_id=1, username="alpha", first_name="Ann", is_bot=False)
    )
    await repo.add(
        AudienceUser(telegram_user_id=2, username="", first_name="Bot", is_bot=True)
    )
    await repo.add(
        AudienceUser(
            telegram_user_id=3, username="gamma", is_bot=False, status=MemberStatus.DELETED
        )
    )

    rows, total = await repo.list(has_username=True, is_bot=False)
    assert total == 2
    assert {r.telegram_user_id for r in rows} == {1, 3}

    rows, total = await repo.list(is_bot=True)
    assert total == 1

    rows, total = await repo.list(search="ann")
    assert total == 1 and rows[0].telegram_user_id == 1

    rows, total = await repo.list(status=MemberStatus.DELETED)
    assert total == 1 and rows[0].telegram_user_id == 3

    rows, total = await repo.list(telegram_user_id=2)
    assert total == 1


async def test_user_filter_by_source_and_tag(db) -> None:
    from backend.app.db.repositories.audience import (
        AudienceSourceRepository,
        AudienceUserRepository,
        SourceUserLinkRepository,
    )

    sources = AudienceSourceRepository(db)
    users = AudienceUserRepository(db)
    links = SourceUserLinkRepository(db)
    s = await sources.add(AudienceSource(reference="s", telegram_id=10))
    u1 = await users.add(AudienceUser(telegram_user_id=1, username="a", tags='["vip"]'))
    await users.add(AudienceUser(telegram_user_id=2, username="b"))
    await links.add(SourceUserLink(source_id=s.id, user_id=u1.id))

    rows, total = await users.list(source_id=s.id)
    assert total == 1 and rows[0].telegram_user_id == 1

    rows, total = await users.list(tag="vip")
    assert total == 1 and rows[0].telegram_user_id == 1


async def test_user_pagination_and_sort(db) -> None:
    from backend.app.db.repositories.audience import AudienceUserRepository

    repo = AudienceUserRepository(db)
    for i in range(1, 11):
        await repo.add(AudienceUser(telegram_user_id=i, username=f"u{i:02d}"))
    rows, total = await repo.list(limit=3, offset=0, sort="username", order="asc")
    assert total == 10
    assert [r.username for r in rows] == ["u01", "u02", "u03"]

    rows, _ = await repo.list(limit=3, offset=9, sort="username", order="asc")
    assert [r.username for r in rows] == ["u10"]


async def test_bulk_operations(db) -> None:
    from backend.app.db.repositories.audience import AudienceUserRepository

    repo = AudienceUserRepository(db)
    u1 = await repo.add(AudienceUser(telegram_user_id=1, username="a"))
    u2 = await repo.add(AudienceUser(telegram_user_id=2, username="b"))
    updated = await repo.bulk_update_status([u1.id, u2.id], MemberStatus.BLOCKED)
    assert updated == 2
    updated = await repo.bulk_set_tags([u1.id], ["x", "y"])
    assert updated == 1
    refreshed = await repo.get(u1.id)
    assert refreshed is not None and "x" in refreshed.tags
