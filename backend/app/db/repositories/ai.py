"""AI metrics / diagnostics repository (PHASE 7)."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.ai import AiMetric, AiRecord

GLOBAL_METRIC = "global"


class AiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- aggregate metrics ---------------------------------------------------
    async def get_metric(self) -> AiMetric:
        metric = (
            await self.session.execute(
                select(AiMetric).where(AiMetric.name == GLOBAL_METRIC)
            )
        ).scalar_one_or_none()
        if metric is None:
            metric = AiMetric(name=GLOBAL_METRIC)
            self.session.add(metric)
            await self.session.flush()
        return metric

    async def bump(
        self,
        *,
        rules: int = 0,
        ai: int = 0,
        fallback: int = 0,
        manual: int = 0,
        ai_error: int = 0,
        latency_ms: int = 0,
        model_load_ms: int | None = None,
    ) -> AiMetric:
        metric = await self.get_metric()
        metric.rules_count += rules
        metric.ai_count += ai
        metric.fallback_count += fallback
        metric.manual_count += manual
        metric.ai_error_count += ai_error
        if latency_ms:
            metric.total_latency_ms += latency_ms
            metric.last_latency_ms = latency_ms
        if model_load_ms is not None:
            metric.model_load_ms = model_load_ms
        await self.session.flush()
        return metric

    # --- recent records ------------------------------------------------------
    async def add_record(self, record: AiRecord) -> AiRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_records(self, *, limit: int = 50, offset: int = 0) -> tuple[list[AiRecord], int]:
        stmt = (
            select(AiRecord)
            .order_by(AiRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        count_stmt = select(func.count()).select_from(AiRecord)
        total = int((await self.session.execute(count_stmt)).scalar_one())
        return rows, total

    async def trim_records(self, keep: int) -> int:
        """Delete older records so at most ``keep`` remain. Returns deleted count."""
        if keep <= 0:
            result = await self.session.execute(delete(AiRecord))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
        ids = (
            await self.session.execute(
                select(AiRecord.id).order_by(AiRecord.created_at.desc()).offset(keep)
            )
        ).scalars().all()
        if not ids:
            return 0
        result = await self.session.execute(delete(AiRecord).where(AiRecord.id.in_(list(ids))))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def reset_records(self) -> None:
        await self.session.execute(delete(AiRecord))


__all__ = ["GLOBAL_METRIC", "AiRepository"]
