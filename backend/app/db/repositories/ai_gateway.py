"""Repository for AI Gateway providers, route settings and request records."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.ai_gateway import (
    AiGatewayRequest,
    AiProviderRow,
    AiRouteSetting,
)


class AiProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: AiProviderRow) -> AiProviderRow:
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, row_id: str) -> AiProviderRow | None:
        return await self.session.get(AiProviderRow, row_id)

    async def find(self, provider: str) -> AiProviderRow | None:
        stmt = select(AiProviderRow).where(AiProviderRow.provider == provider)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(self) -> list[AiProviderRow]:
        stmt = select(AiProviderRow).order_by(
            AiProviderRow.priority.desc(), AiProviderRow.created_at
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, row: AiProviderRow) -> None:
        await self.session.delete(row)
        await self.session.flush()


class AiRouteSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> AiRouteSetting | None:
        stmt = select(AiRouteSetting).where(AiRouteSetting.key == key)
        return (await self.session.execute(stmt)).scalars().first()

    async def set(self, key: str, value: str, *, value_type: str = "str") -> AiRouteSetting:
        row = await self.get(key)
        if row is None:
            row = AiRouteSetting(key=key, value=value, value_type=value_type)
            self.session.add(row)
        else:
            row.value = value
            row.value_type = value_type
        await self.session.flush()
        return row

    async def all(self) -> list[AiRouteSetting]:
        stmt = select(AiRouteSetting).order_by(AiRouteSetting.key)
        return list((await self.session.execute(stmt)).scalars().all())


class AiGatewayRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: AiGatewayRequest) -> AiGatewayRequest:
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_recent(self, limit: int = 50) -> list[AiGatewayRequest]:
        stmt = (
            select(AiGatewayRequest)
            .order_by(AiGatewayRequest.created_at.desc())
            .limit(max(1, limit))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(AiGatewayRequest)
        return int((await self.session.execute(stmt)).scalar_one())

    async def trim(self, keep: int) -> int:
        """Delete the oldest rows so at most ``keep`` remain. Returns removed count."""
        keep = max(0, keep)
        all_ids = (
            await self.session.execute(
                select(AiGatewayRequest.id).order_by(AiGatewayRequest.created_at.desc())
            )
        ).scalars().all()
        to_remove = list(all_ids[keep:])
        if not to_remove:
            return 0
        await self.session.execute(
            delete(AiGatewayRequest).where(AiGatewayRequest.id.in_(to_remove))
        )
        await self.session.flush()
        return len(to_remove)

    async def clear(self) -> None:
        await self.session.execute(delete(AiGatewayRequest))
        await self.session.flush()


__all__ = [
    "AiGatewayRequestRepository",
    "AiProviderRepository",
    "AiRouteSettingRepository",
]
