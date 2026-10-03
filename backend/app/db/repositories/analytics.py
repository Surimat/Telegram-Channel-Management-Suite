"""Analytics repository (PHASE 8).

Read-only aggregate queries over the data the suite already stores (posts,
reaction jobs, audience sources/users/links, invite tasks). Everything here is
portable SQLAlchemy — no SQLite-specific SQL — so the same queries work after a
future move to PostgreSQL (D-002).

Per-day series are bucketed in Python from a bounded time window rather than with
database-specific date functions: the owner's channel volume is small, and this
keeps the queries portable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.audience import AudienceSource, AudienceUser, SourceUserLink
from backend.app.db.models.invite import InviteStatus, InviteTask
from backend.app.db.models.post import Post
from backend.app.db.models.reaction import ReactionJob, ReactionJobStatus


def _day_key(moment: datetime) -> str:
    """ISO date (UTC) for a timestamp; tolerant of naive values from SQLite."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date().isoformat()


def _buckets(days: int, *, now: datetime | None = None) -> list[str]:
    """Ordered list of ISO dates for the last ``days`` days (inclusive of today)."""
    now = now or datetime.now(UTC)
    today = now.astimezone(UTC).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _rows(self, stmt) -> list:  # type: ignore[no-untyped-def]
        return list((await self.session.execute(stmt)).all())

    async def _scalar(self, stmt) -> int:  # type: ignore[no-untyped-def]
        return int((await self.session.execute(stmt)).scalar_one())

    async def _scalars(self, stmt) -> list:  # type: ignore[no-untyped-def]
        return list((await self.session.execute(stmt)).scalars().all())

    @staticmethod
    def _value(enum_or_value) -> str:  # type: ignore[no-untyped-def]
        return str(getattr(enum_or_value, "value", enum_or_value))

    # ==================================================================
    # Content / posts
    # ==================================================================
    async def posts_total(self) -> int:
        return await self._scalar(select(func.count()).select_from(Post))

    async def posts_since(self, since: datetime) -> int:
        stmt = select(func.count()).select_from(Post).where(Post.created_at >= since)
        return await self._scalar(stmt)

    async def posts_by_category(self) -> dict[str, int]:
        stmt = select(Post.category, func.count()).group_by(Post.category)
        return {str(cat or "unknown"): int(n) for cat, n in await self._rows(stmt)}

    async def posts_by_source(self) -> dict[str, int]:
        """Posts grouped by classification source (rules / llm / manual / fallback)."""
        stmt = select(Post.classification_source, func.count()).group_by(Post.classification_source)
        return {str(src or "unknown"): int(n) for src, n in await self._rows(stmt)}

    async def posts_by_status(self) -> dict[str, int]:
        stmt = select(Post.status, func.count()).group_by(Post.status)
        return {self._value(st): int(n) for st, n in await self._rows(stmt)}

    async def posts_per_day(self, days: int = 30) -> list[dict[str, object]]:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = select(Post.created_at).where(Post.created_at >= since)
        rows = await self._scalars(stmt)
        return self._bucket_counts(days, rows)

    @staticmethod
    def _bucket_counts(days: int, timestamps: list[datetime | None]) -> list[dict[str, object]]:
        keys = _buckets(days)
        counts: dict[str, int] = defaultdict(int)
        for ts in timestamps:
            if ts is None:
                continue
            counts[_day_key(ts)] += 1
        return [{"date": key, "count": counts.get(key, 0)} for key in keys]

    # ==================================================================
    # Reactions
    # ==================================================================
    async def reactions_total(self) -> int:
        stmt = select(func.count()).select_from(ReactionJob)
        return await self._scalar(stmt)

    async def reactions_by_status(self) -> dict[str, int]:
        stmt = select(ReactionJob.status, func.count()).group_by(ReactionJob.status)
        return {self._value(st): int(n) for st, n in await self._rows(stmt)}

    async def reactions_by_emoji(self, limit: int = 12) -> list[dict[str, object]]:
        stmt = (
            select(ReactionJob.reaction, func.count())
            .where(ReactionJob.reaction != "")
            .group_by(ReactionJob.reaction)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [{"reaction": str(r), "count": int(n)} for r, n in await self._rows(stmt)]

    async def reactions_by_category(self) -> dict[str, int]:
        """Reaction count per post category (join jobs → posts)."""
        stmt = (
            select(Post.category, func.count())
            .select_from(ReactionJob)
            .join(Post, Post.id == ReactionJob.post_id)
            .group_by(Post.category)
        )
        return {str(cat or "unknown"): int(n) for cat, n in await self._rows(stmt)}

    async def reactions_by_bot(self, limit: int = 20) -> list[dict[str, object]]:
        stmt = (
            select(ReactionJob.bot_id, func.count())
            .group_by(ReactionJob.bot_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [{"bot_id": str(b), "count": int(n)} for b, n in await self._rows(stmt)]

    async def reactions_per_day(self, days: int = 30) -> list[dict[str, object]]:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = select(ReactionJob.created_at).where(ReactionJob.created_at >= since)
        rows = await self._scalars(stmt)
        return self._bucket_counts(days, rows)

    async def reactions_completed_per_day(self, days: int = 30) -> list[dict[str, object]]:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(ReactionJob.completed_at)
            .where(ReactionJob.completed_at.is_not(None), ReactionJob.completed_at >= since)
            .where(ReactionJob.status == ReactionJobStatus.DONE)
        )
        rows = await self._scalars(stmt)
        return self._bucket_counts(days, rows)

    # ==================================================================
    # Audience
    # ==================================================================
    async def audience_total(self) -> int:
        stmt = select(func.count()).select_from(AudienceUser)
        return await self._scalar(stmt)

    async def audience_since(self, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(AudienceUser)
            .where(AudienceUser.first_seen_at >= since)
        )
        return await self._scalar(stmt)

    async def audience_per_day(self, days: int = 30) -> list[dict[str, object]]:
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = select(AudienceUser.first_seen_at).where(AudienceUser.first_seen_at >= since)
        rows = await self._scalars(stmt)
        return self._bucket_counts(days, rows)

    async def audience_by_status(self) -> dict[str, int]:
        stmt = select(AudienceUser.status, func.count()).group_by(AudienceUser.status)
        return {self._value(st): int(n) for st, n in await self._rows(stmt)}

    async def audience_sources_total(self) -> int:
        stmt = select(func.count()).select_from(AudienceSource)
        return await self._scalar(stmt)

    async def audience_links_total(self) -> int:
        stmt = select(func.count()).select_from(SourceUserLink)
        return await self._scalar(stmt)

    async def top_sources(self, limit: int = 10) -> list[dict[str, object]]:
        """Sources ranked by how many users they contributed (link count)."""
        stmt = (
            select(
                AudienceSource.id,
                AudienceSource.title,
                AudienceSource.username,
                func.count(SourceUserLink.id),
            )
            .select_from(AudienceSource)
            .outerjoin(SourceUserLink, SourceUserLink.source_id == AudienceSource.id)
            .group_by(AudienceSource.id)
            .order_by(func.count(SourceUserLink.id).desc())
            .limit(limit)
        )
        return [
            {
                "id": str(sid),
                "title": str(title or username or sid),
                "username": str(username or ""),
                "users": int(n),
            }
            for sid, title, username, n in (await self.session.execute(stmt)).all()
        ]

    async def source_effectiveness(self, limit: int = 10) -> list[dict[str, object]]:
        """Per-source scan quality: discovered vs. new vs. duplicates vs. errors."""
        stmt = (
            select(
                AudienceSource.id,
                AudienceSource.title,
                AudienceSource.username,
                AudienceSource.discovered_count,
                AudienceSource.new_count,
                AudienceSource.duplicate_count,
                AudienceSource.error_count,
                AudienceSource.completeness,
            )
            .order_by(AudienceSource.new_count.desc(), AudienceSource.discovered_count.desc())
            .limit(limit)
        )
        out: list[dict[str, object]] = []
        for sid, title, username, discovered, new, dups, errors, completeness in (
            await self.session.execute(stmt)
        ).all():
            out.append(
                {
                    "id": str(sid),
                    "title": str(title or username or sid),
                    "username": str(username or ""),
                    "discovered": int(discovered or 0),
                    "new": int(new or 0),
                    "duplicates": int(dups or 0),
                    "errors": int(errors or 0),
                    "completeness": str(getattr(completeness, "value", completeness)),
                }
            )
        return out

    # ==================================================================
    # Invites
    # ==================================================================
    async def invite_totals(self) -> dict[str, int]:
        stmt = select(InviteTask.status, func.count()).group_by(InviteTask.status)
        counts = {self._value(st): int(n) for st, n in await self._rows(stmt)}
        return {status.value: counts.get(status.value, 0) for status in InviteStatus}
