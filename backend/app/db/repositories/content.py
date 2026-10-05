"""Repositories for the Content Studio (v1.2)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.content import (
    ButtonSet,
    CommentPlan,
    ContentItem,
    ContentItemStatus,
    ContentSource,
    ContentSourceKind,
    MediaAsset,
    Publication,
    PublicationStatus,
)


class ContentSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, source: ContentSource) -> ContentSource:
        self.session.add(source)
        await self.session.flush()
        return source

    async def get(self, source_id: str) -> ContentSource | None:
        return await self.session.get(ContentSource, source_id)

    async def list_all(
        self, *, kind: ContentSourceKind | None = None, enabled_only: bool = False
    ) -> list[ContentSource]:
        stmt = select(ContentSource)
        if kind is not None:
            stmt = stmt.where(ContentSource.kind == kind)
        if enabled_only:
            stmt = stmt.where(ContentSource.enabled.is_(True))
        stmt = stmt.order_by(ContentSource.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_by_reference(self, reference: str) -> ContentSource | None:
        if not reference:
            return None
        stmt = select(ContentSource).where(ContentSource.reference == reference)
        return (await self.session.execute(stmt)).scalars().first()

    async def delete(self, source: ContentSource) -> None:
        await self.session.delete(source)
        await self.session.flush()


class ContentItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, item: ContentItem) -> ContentItem:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get(self, item_id: str) -> ContentItem | None:
        return await self.session.get(ContentItem, item_id)

    async def find_by_source_hash(self, source_hash: str) -> ContentItem | None:
        if not source_hash:
            return None
        stmt = select(ContentItem).where(ContentItem.source_hash == source_hash)
        return (await self.session.execute(stmt)).scalars().first()

    async def find_by_content_hash(self, content_hash: str) -> ContentItem | None:
        if not content_hash:
            return None
        stmt = select(ContentItem).where(ContentItem.content_hash == content_hash)
        return (await self.session.execute(stmt)).scalars().first()

    async def find_by_source_message(
        self, source_id: str, message_id: int
    ) -> ContentItem | None:
        stmt = select(ContentItem).where(
            ContentItem.source_id == source_id,
            ContentItem.source_message_id == message_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list(
        self,
        *,
        status: ContentItemStatus | None = None,
        source_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ContentItem], int]:
        stmt = select(ContentItem)
        count_stmt = select(func.count()).select_from(ContentItem)
        for cond in (
            (ContentItem.status == status) if status is not None else None,
            (ContentItem.source_id == source_id) if source_id else None,
        ):
            if cond is not None:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(ContentItem.created_at.desc()).limit(limit).offset(offset)
        rows = list((await self.session.execute(stmt)).scalars().all())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def status_counts(self) -> dict[str, int]:
        stmt = select(ContentItem.status, func.count()).group_by(ContentItem.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def scheduled_between(self, start, end) -> list[ContentItem]:  # type: ignore[no-untyped-def]
        stmt = (
            select(ContentItem)
            .where(ContentItem.scheduled_at.is_not(None))
            .where(ContentItem.scheduled_at >= start)
            .where(ContentItem.scheduled_at <= end)
            .order_by(ContentItem.scheduled_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, item: ContentItem) -> None:
        await self.session.delete(item)
        await self.session.flush()


class MediaAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, asset: MediaAsset) -> MediaAsset:
        self.session.add(asset)
        await self.session.flush()
        return asset

    async def get(self, asset_id: str) -> MediaAsset | None:
        return await self.session.get(MediaAsset, asset_id)

    async def find_by_media_hash(self, media_hash: str) -> MediaAsset | None:
        if not media_hash:
            return None
        stmt = select(MediaAsset).where(MediaAsset.media_hash == media_hash)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_item(self, item_id: str) -> list[MediaAsset]:
        stmt = (
            select(MediaAsset)
            .where(MediaAsset.item_id == item_id)
            .order_by(MediaAsset.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, asset: MediaAsset) -> None:
        await self.session.delete(asset)
        await self.session.flush()


class PublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, publication: Publication) -> Publication:
        self.session.add(publication)
        await self.session.flush()
        return publication

    async def get(self, publication_id: str) -> Publication | None:
        return await self.session.get(Publication, publication_id)

    async def find_by_idempotency(self, key: str) -> Publication | None:
        if not key:
            return None
        stmt = select(Publication).where(Publication.idempotency_key == key)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_item(self, item_id: str) -> list[Publication]:
        stmt = (
            select(Publication)
            .where(Publication.item_id == item_id)
            .order_by(Publication.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def due(self, now, limit: int = 50) -> list[Publication]:  # type: ignore[no-untyped-def]
        stmt = (
            select(Publication)
            .where(Publication.status.in_(
                [PublicationStatus.PLANNED, PublicationStatus.SCHEDULED]
            ))
            .where(Publication.enabled.is_(True))
            .where(Publication.scheduled_at.is_not(None))
            .where(Publication.scheduled_at <= now)
            .order_by(Publication.scheduled_at)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def due_deletions(self, now, limit: int = 50) -> list[Publication]:  # type: ignore[no-untyped-def]
        stmt = (
            select(Publication)
            .where(Publication.status == PublicationStatus.PUBLISHED)
            .where(Publication.delete_at.is_not(None))
            .where(Publication.delete_at <= now)
            .where(Publication.deleted_at.is_(None))
            .order_by(Publication.delete_at)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_range(self, start, end) -> list[Publication]:  # type: ignore[no-untyped-def]
        stmt = (
            select(Publication)
            .where(Publication.scheduled_at.is_not(None))
            .where(Publication.scheduled_at >= start)
            .where(Publication.scheduled_at <= end)
            .order_by(Publication.scheduled_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def counts(self) -> dict[str, int]:
        stmt = select(Publication.status, func.count()).group_by(Publication.status)
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def published_since(self, since) -> list[Publication]:  # type: ignore[no-untyped-def]
        stmt = (
            select(Publication)
            .where(Publication.status == PublicationStatus.PUBLISHED)
            .where(Publication.published_at.is_not(None))
            .where(Publication.published_at >= since)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, publication: Publication) -> None:
        await self.session.delete(publication)
        await self.session.flush()


class ButtonSetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, button_set: ButtonSet) -> ButtonSet:
        self.session.add(button_set)
        await self.session.flush()
        return button_set

    async def get(self, button_set_id: str) -> ButtonSet | None:
        return await self.session.get(ButtonSet, button_set_id)

    async def for_item(self, item_id: str) -> ButtonSet | None:
        stmt = select(ButtonSet).where(ButtonSet.item_id == item_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def for_publication(self, publication_id: str) -> ButtonSet | None:
        stmt = select(ButtonSet).where(ButtonSet.publication_id == publication_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def delete(self, button_set: ButtonSet) -> None:
        await self.session.delete(button_set)
        await self.session.flush()


class CommentPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, plan: CommentPlan) -> CommentPlan:
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def get(self, plan_id: str) -> CommentPlan | None:
        return await self.session.get(CommentPlan, plan_id)

    async def for_publication(self, publication_id: str) -> CommentPlan | None:
        stmt = select(CommentPlan).where(CommentPlan.publication_id == publication_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def due(self, now, limit: int = 50) -> list[CommentPlan]:  # type: ignore[no-untyped-def]
        stmt = (
            select(CommentPlan)
            .where(CommentPlan.enabled.is_(True))
            .where(CommentPlan.status == "planned")
            .where(CommentPlan.created_at <= now)
            .order_by(CommentPlan.created_at)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, plan: CommentPlan) -> None:
        await self.session.delete(plan)
        await self.session.flush()


__all__ = [
    "ButtonSetRepository",
    "CommentPlanRepository",
    "ContentItemRepository",
    "ContentSourceRepository",
    "MediaAssetRepository",
    "PublicationRepository",
]
