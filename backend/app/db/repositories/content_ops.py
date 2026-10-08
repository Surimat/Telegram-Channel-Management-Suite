"""Repositories for Content Operations 2.0 (v1.9)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.content_ops import AiProfile, AutomationRule, ContentOperation


class AiProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, profile: AiProfile) -> AiProfile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get(self, profile_id: str) -> AiProfile | None:
        return await self.session.get(AiProfile, profile_id)

    async def get_by_key(self, key: str) -> AiProfile | None:
        if not key:
            return None
        stmt = select(AiProfile).where(AiProfile.key == key)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(self) -> list[AiProfile]:
        stmt = select(AiProfile).order_by(AiProfile.builtin.desc(), AiProfile.title)
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, profile: AiProfile) -> None:
        await self.session.delete(profile)
        await self.session.flush()


class AutomationRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, rule: AutomationRule) -> AutomationRule:
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get(self, rule_id: str) -> AutomationRule | None:
        return await self.session.get(AutomationRule, rule_id)

    async def list_all(self) -> list[AutomationRule]:
        stmt = select(AutomationRule).order_by(
            AutomationRule.priority.desc(), AutomationRule.created_at
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_active(self, source_kind: str = "") -> list[AutomationRule]:
        stmt = (
            select(AutomationRule)
            .where(AutomationRule.enabled.is_(True))
            .order_by(AutomationRule.priority.desc(), AutomationRule.created_at)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [r for r in rows if not r.source_kind or r.source_kind == source_kind]

    async def delete(self, rule: AutomationRule) -> None:
        await self.session.delete(rule)
        await self.session.flush()


class ContentOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, operation: ContentOperation) -> ContentOperation:
        self.session.add(operation)
        await self.session.flush()
        return operation

    async def list_for_item(self, item_id: str) -> list[ContentOperation]:
        stmt = (
            select(ContentOperation)
            .where(ContentOperation.item_id == item_id)
            .order_by(ContentOperation.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_recent(self, limit: int = 100) -> list[ContentOperation]:
        stmt = (
            select(ContentOperation)
            .order_by(ContentOperation.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def stage_counts(self) -> dict[str, int]:
        stmt = select(ContentOperation.stage, func.count()).group_by(ContentOperation.stage)
        rows = (await self.session.execute(stmt)).all()
        return {str(stage): int(count) for stage, count in rows}

    async def status_counts_for_stage(self, stage: str) -> dict[str, int]:
        stmt = (
            select(ContentOperation.status, func.count())
            .where(ContentOperation.stage == stage)
            .group_by(ContentOperation.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}


__all__ = [
    "AiProfileRepository",
    "AutomationRuleRepository",
    "ContentOperationRepository",
]
