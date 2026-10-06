"""Consistency router: the "Проверка целостности" panel.

Read-only. Reports cross-module drift (DB ↔ migration, API ↔ frontend, jobs ↔
handlers, providers, i18n, help catalog, documented endpoints) plus a few
DB-backed integration checks. Findings are explained in plain language with a
fix, and each carries a confidence so heuristics never look like hard errors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_consistency_auditor
from backend.app.api.schemas.consistency import (
    ConsistencyArea,
    ConsistencyFinding,
    ConsistencyReport,
)
from backend.app.services.consistency import ConsistencyAuditor

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.get("", response_model=ConsistencyReport)
async def consistency_report(
    auditor: ConsistencyAuditor = Depends(get_consistency_auditor),
) -> ConsistencyReport:
    report = await auditor.run()
    return ConsistencyReport(
        generated_at=report.generated_at,
        overall=report.overall,
        counts=report.counts,
        areas=[
            ConsistencyArea(key=a.key, label=a.label, status=a.status) for a in report.areas
        ],
        findings=[
            ConsistencyFinding(
                id=f.id,
                category=f.category,
                area=f.area,
                severity=f.severity,
                confidence=f.confidence,
                title=f.title,
                detail=f.detail,
                why=f.why,
                how_to_fix=f.how_to_fix,
                subsystem=f.subsystem,
            )
            for f in report.findings
        ],
    )


__all__ = ["router"]
