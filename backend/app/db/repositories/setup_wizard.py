"""Repository for end-to-end Setup Wizard progress (D-128)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.setup_wizard import SetupWizardStep


class SetupWizardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> SetupWizardStep | None:
        result = await self.session.execute(
            select(SetupWizardStep).where(SetupWizardStep.key == key)
        )
        return result.scalars().first()

    async def get_or_create(self, key: str, *, position: int = 0) -> SetupWizardStep:
        existing = await self.get(key)
        if existing is not None:
            return existing
        row = SetupWizardStep(key=key, position=position)
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_all(self) -> list[SetupWizardStep]:
        stmt = select(SetupWizardStep).order_by(SetupWizardStep.position)
        return list((await self.session.execute(stmt)).scalars().all())
