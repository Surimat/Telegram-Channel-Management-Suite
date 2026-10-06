"""Consistency report data types (v1.5).

Kept separate from the auditor and the static checks so both can import the
``Finding`` type without a circular import.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

HEALTH_PASS = "pass"
HEALTH_WARNING = "warning"
HEALTH_FAIL = "fail"
HEALTH_NOT_TESTED = "not_tested"

#: Health areas surfaced in the panel (never a meaningless single percentage).
AREA_LABELS = {
    "configuration": "Configuration",
    "integration": "Integration",
    "security": "Security",
    "documentation": "Documentation",
    "ux": "UX",
}

#: Which area each category belongs to.
CATEGORY_AREA = {
    "database": "configuration",
    "settings": "configuration",
    "capabilities": "configuration",
    "api": "integration",
    "scheduler": "integration",
    "providers": "integration",
    "channels": "integration",
    "security": "security",
    "docs": "documentation",
    "i18n": "documentation",
    "help": "ux",
    "frontend": "ux",
    "orphan": "configuration",
}


@dataclass(slots=True)
class Finding:
    id: str
    category: str
    severity: str
    confidence: str
    title: str
    detail: str
    why: str = ""
    how_to_fix: str = ""
    subsystem: str = ""

    @property
    def area(self) -> str:
        return CATEGORY_AREA.get(self.category, "integration")

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["area"] = self.area
        return data


@dataclass(slots=True)
class HealthArea:
    key: str
    label: str
    status: str

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label, "status": self.status}


@dataclass(slots=True)
class ConsistencyReport:
    generated_at: str
    overall: str
    counts: dict[str, int]
    areas: list[HealthArea] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "overall": self.overall,
            "counts": self.counts,
            "areas": [a.as_dict() for a in self.areas],
            "findings": [f.as_dict() for f in self.findings],
        }


def status_for(findings: list[Finding]) -> str:
    severities = {f.severity for f in findings}
    if SEVERITY_ERROR in severities:
        return HEALTH_FAIL
    if SEVERITY_WARNING in severities:
        return HEALTH_WARNING
    return HEALTH_PASS


def overall_from_counts(counts: dict[str, int]) -> str:
    if counts.get(SEVERITY_ERROR):
        return HEALTH_FAIL
    if counts.get(SEVERITY_WARNING):
        return HEALTH_WARNING
    return HEALTH_PASS


def count_findings(findings: list[Finding]) -> dict[str, int]:
    counts = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 0, SEVERITY_INFO: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def build_report(findings: list[Finding]) -> ConsistencyReport:
    """Assemble the report (areas + counts + overall) from raw findings."""
    by_area: dict[str, list[Finding]] = {key: [] for key in AREA_LABELS}
    for f in findings:
        by_area.setdefault(f.area, []).append(f)
    areas = [
        HealthArea(key=key, label=label, status=status_for(by_area.get(key, [])))
        for key, label in AREA_LABELS.items()
    ]
    counts = count_findings(findings)
    return ConsistencyReport(
        generated_at=datetime.now(UTC).isoformat(),
        overall=overall_from_counts(counts),
        counts=counts,
        areas=areas,
        findings=sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.id)),
    )


__all__ = [
    "AREA_LABELS",
    "CATEGORY_AREA",
    "HEALTH_FAIL",
    "HEALTH_NOT_TESTED",
    "HEALTH_PASS",
    "HEALTH_WARNING",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_ORDER",
    "SEVERITY_WARNING",
    "ConsistencyReport",
    "Finding",
    "HealthArea",
    "build_report",
    "count_findings",
    "overall_from_counts",
    "status_for",
]
