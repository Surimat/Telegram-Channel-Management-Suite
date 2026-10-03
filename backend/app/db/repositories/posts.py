"""Post repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.post import Post, PostStatus


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, post: Post) -> Post:
        self.session.add(post)
        await self.session.flush()
        return post

    async def get(self, post_id: str) -> Post | None:
        return await self.session.get(Post, post_id)

    async def get_by_telegram(
        self, channel_id: int, telegram_message_id: int
    ) -> Post | None:
        stmt = select(Post).where(
            Post.channel_id == channel_id,
            Post.telegram_message_id == telegram_message_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list(
        self,
        *,
        status: PostStatus | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Post], int]:
        stmt = select(Post)
        count_stmt = select(func.count()).select_from(Post)
        for cond in (
            (Post.status == status) if status is not None else None,
            (Post.category == category) if category else None,
        ):
            if cond is not None:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(Post.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def latest(self) -> Post | None:
        stmt = select(Post).order_by(Post.created_at.desc()).limit(1)
        return (await self.session.execute(stmt)).scalars().first()
