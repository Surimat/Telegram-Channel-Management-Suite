"""Audience repositories (PHASE 5): the only modules that query audience tables.

Kept query-focused so services stay free of SQLAlchemy specifics and SQL stays
portable (SQLite → PostgreSQL). All filtering/pagination happens in the database
so a weak machine never loads the whole audience into memory.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.audience import (
    AudienceSource,
    AudienceUser,
    Completeness,
    MemberStatus,
    ScanStatus,
    SourceUserLink,
)


def _enum_value(enum_cls, raw: object) -> str:
    """Normalize a stored enum key (name or value) to its lowercase value.

    SQLAlchemy stores ``Enum`` members by *name* on SQLite, while the rest of the
    code reasons in *values*; grouping a column therefore returns names. This
    keeps the two representations consistent for counts and dashboards.
    """
    text = str(raw)
    member = enum_cls.__members__.get(text)
    return member.value if member is not None else text.lower()


class AudienceSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, source: AudienceSource) -> AudienceSource:
        self.session.add(source)
        await self.session.flush()
        return source

    async def get(self, source_id: str) -> AudienceSource | None:
        return await self.session.get(AudienceSource, source_id)

    async def get_by_telegram_id(self, telegram_id: int) -> AudienceSource | None:
        result = await self.session.execute(
            select(AudienceSource).where(AudienceSource.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        enabled: bool | None = None,
        status: ScanStatus | None = None,
        search: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[AudienceSource], int]:
        stmt = select(AudienceSource)
        count_stmt = select(func.count()).select_from(AudienceSource)
        conditions = []
        if enabled is not None:
            conditions.append(AudienceSource.enabled == enabled)
        if status is not None:
            conditions.append(AudienceSource.scan_status == status)
        if search:
            like = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(AudienceSource.title).like(like),
                    func.lower(AudienceSource.username).like(like),
                    func.lower(AudienceSource.reference).like(like),
                )
            )
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(AudienceSource.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def delete(self, source: AudienceSource) -> None:
        # Remove links first (SQLite has no FK cascade by default).
        await self.session.execute(
            SourceUserLink.__table__.delete().where(SourceUserLink.source_id == source.id)
        )
        await self.session.delete(source)
        await self.session.flush()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(AudienceSource))
        return int(result.scalar_one())

    async def count_completeness(self) -> dict[str, int]:
        stmt = select(AudienceSource.completeness, func.count()).group_by(
            AudienceSource.completeness
        )
        rows = (await self.session.execute(stmt)).all()
        return {_enum_value(Completeness, k): int(v) for k, v in rows}

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(AudienceSource.scan_status, func.count()).group_by(
            AudienceSource.scan_status
        )
        rows = (await self.session.execute(stmt)).all()
        return {_enum_value(ScanStatus, k): int(v) for k, v in rows}

    async def partial_count(self) -> int:
        stmt = select(func.count()).select_from(AudienceSource).where(
            AudienceSource.completeness.in_([Completeness.PARTIAL, Completeness.NO_ACCESS])
        )
        return int((await self.session.execute(stmt)).scalar_one())


class SourceUserLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, source_id: str, user_id: str) -> SourceUserLink | None:
        stmt = select(SourceUserLink).where(
            SourceUserLink.source_id == source_id, SourceUserLink.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, link: SourceUserLink) -> SourceUserLink:
        self.session.add(link)
        await self.session.flush()
        return link

    async def add_many(self, links: list[SourceUserLink]) -> None:
        if links:
            self.session.add_all(links)
            await self.session.flush()

    async def existing_user_ids(self, source_id: str, user_ids: list[str]) -> set[str]:
        if not user_ids:
            return set()
        stmt = select(SourceUserLink.user_id).where(
            SourceUserLink.source_id == source_id,
            SourceUserLink.user_id.in_(user_ids),
        )
        return set((await self.session.execute(stmt)).scalars().all())

    async def count_for_source(self, source_id: str) -> int:
        stmt = select(func.count()).select_from(SourceUserLink).where(
            SourceUserLink.source_id == source_id
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_for_user(self, user_id: str) -> int:
        stmt = select(func.count()).select_from(SourceUserLink).where(
            SourceUserLink.user_id == user_id
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def source_ids_for_user(self, user_id: str) -> list[str]:
        stmt = select(SourceUserLink.source_id).where(SourceUserLink.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_total(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(SourceUserLink)))
            .scalar_one()
        )

    async def source_overlap(self, limit: int = 50) -> list[tuple[str, int]]:
        """Sources ranked by number of members (for the overlap chart)."""
        stmt = (
            select(SourceUserLink.source_id, func.count().label("n"))
            .group_by(SourceUserLink.source_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [(str(sid), int(n)) for sid, n in (await self.session.execute(stmt)).all()]


class AudienceUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user: AudienceUser) -> AudienceUser:
        self.session.add(user)
        await self.session.flush()
        return user

    async def add_many(self, users: list[AudienceUser]) -> None:
        if users:
            self.session.add_all(users)
            await self.session.flush()

    async def get(self, user_id: str) -> AudienceUser | None:
        return await self.session.get(AudienceUser, user_id)

    async def get_by_telegram_id(self, telegram_user_id: int) -> AudienceUser | None:
        stmt = select(AudienceUser).where(AudienceUser.telegram_user_id == telegram_user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_many_by_telegram_ids(
        self, telegram_user_ids: list[int]
    ) -> dict[int, AudienceUser]:
        if not telegram_user_ids:
            return {}
        stmt = select(AudienceUser).where(
            AudienceUser.telegram_user_id.in_(telegram_user_ids)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return {u.telegram_user_id: u for u in rows}

    async def list(
        self,
        *,
        search: str = "",
        source_id: str | None = None,
        source_ids: list[str] | None = None,
        tag: str | None = None,
        status: MemberStatus | None = None,
        is_bot: bool | None = None,
        is_deleted: bool | None = None,
        has_username: bool | None = None,
        is_premium: bool | None = None,
        telegram_user_id: int | None = None,
        seen_after: datetime | None = None,
        seen_before: datetime | None = None,
        sort: str = "last_seen",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AudienceUser], int]:
        stmt = select(AudienceUser)
        count_stmt = select(func.count()).select_from(AudienceUser)
        conditions = self._conditions(
            search=search,
            source_id=source_id,
            source_ids=source_ids,
            tag=tag,
            status=status,
            is_bot=is_bot,
            is_deleted=is_deleted,
            has_username=has_username,
            is_premium=is_premium,
            telegram_user_id=telegram_user_id,
            seen_after=seen_after,
            seen_before=seen_before,
        )
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(*self._order(sort, order)).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    def _conditions(self, **kw: object) -> list[object]:
        conditions: list[object] = []
        search = kw["search"]
        if search:
            like = f"%{str(search).lower()}%"
            conditions.append(
                or_(
                    func.lower(AudienceUser.username).like(like),
                    func.lower(AudienceUser.first_name).like(like),
                    func.lower(AudienceUser.last_name).like(like),
                    func.lower(AudienceUser.display_name).like(like),
                )
            )
        if kw["telegram_user_id"] is not None:
            conditions.append(AudienceUser.telegram_user_id == kw["telegram_user_id"])
        if kw["status"] is not None:
            conditions.append(AudienceUser.status == kw["status"])
        if kw["is_bot"] is not None:
            conditions.append(AudienceUser.is_bot == kw["is_bot"])
        if kw["is_deleted"] is not None:
            conditions.append(AudienceUser.is_deleted == kw["is_deleted"])
        if kw["is_premium"] is not None:
            conditions.append(AudienceUser.is_premium == kw["is_premium"])
        if kw["has_username"] is not None:
            if kw["has_username"]:
                conditions.append(AudienceUser.username != "")
            else:
                conditions.append(AudienceUser.username == "")
        if kw["tag"]:
            # Tags are a JSON text list; a LIKE match is portable and adequate.
            conditions.append(AudienceUser.tags.like(f'%"{kw["tag"]}"%'))
        if kw["seen_after"] is not None:
            conditions.append(AudienceUser.last_seen_at >= kw["seen_after"])
        if kw["seen_before"] is not None:
            conditions.append(AudienceUser.last_seen_at <= kw["seen_before"])
        if kw["source_id"]:
            sub = select(SourceUserLink.user_id).where(
                SourceUserLink.source_id == kw["source_id"]
            )
            conditions.append(AudienceUser.id.in_(sub))
        source_ids = kw.get("source_ids")
        if source_ids:
            sub = select(SourceUserLink.user_id).where(
                SourceUserLink.source_id.in_(source_ids)
            )
            conditions.append(AudienceUser.id.in_(sub))
        return conditions

    @staticmethod
    def _order(sort: str, order: str):
        columns = {
            "last_seen": AudienceUser.last_seen_at,
            "first_seen": AudienceUser.first_seen_at,
            "username": AudienceUser.username,
            "score": AudienceUser.score,
            "created": AudienceUser.created_at,
            "telegram_id": AudienceUser.telegram_user_id,
        }
        col = columns.get(sort, AudienceUser.last_seen_at)
        return [col.desc() if order == "desc" else col.asc()]

    async def count(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(AudienceUser)))
            .scalar_one()
        )

    async def count_unique(self) -> int:
        stmt = select(func.count(func.distinct(AudienceUser.telegram_user_id)))
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(AudienceUser.status, func.count()).group_by(AudienceUser.status)
        rows = (await self.session.execute(stmt)).all()
        return {_enum_value(MemberStatus, k): int(v) for k, v in rows}

    async def count_new_since(self, since: datetime) -> int:
        stmt = select(func.count()).select_from(AudienceUser).where(
            AudienceUser.created_at >= since
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_bots(self) -> int:
        stmt = select(func.count()).select_from(AudienceUser).where(AudienceUser.is_bot.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def discovered_per_day(self, days: int = 30) -> list[tuple[str, int]]:
        """New users per day (YYYY-MM-DD) for the discovery chart."""
        day = func.strftime("%Y-%m-%d", AudienceUser.created_at)
        stmt = (
            select(day.label("day"), func.count())
            .group_by(day)
            .order_by(day.desc())
            .limit(days)
        )
        try:
            rows = (await self.session.execute(stmt)).all()
        except Exception:  # pragma: no cover - non-SQLite fallback
            return []
        return [(str(d), int(n)) for d, n in rows][::-1]

    async def iter_all(
        self,
        *,
        source_id: str | None = None,
        tag: str | None = None,
        batch_size: int = 500,
    ):
        """Yield users in batches (streaming export; never all in RAM at once)."""
        offset = 0
        while True:
            rows, total = await self.list(
                source_id=source_id, tag=tag, limit=batch_size, offset=offset
            )
            if not rows:
                break
            for row in rows:
                yield row
            offset += len(rows)
            if offset >= total:
                break

    async def bulk_update_status(self, user_ids: list[str], status: MemberStatus) -> int:
        if not user_ids:
            return 0
        stmt = (
            update(AudienceUser)
            .where(AudienceUser.id.in_(user_ids))
            .values(status=status, updated_at=utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)

    async def bulk_set_tags(self, user_ids: list[str], tags: list[str]) -> int:
        if not user_ids:
            return 0
        import json

        stmt = (
            update(AudienceUser)
            .where(AudienceUser.id.in_(user_ids))
            .values(tags=json.dumps(tags), updated_at=utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)
