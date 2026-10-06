"""Consistency ("Проверка целостности") schemas.

The panel shows an overall status, one health row per area, and the findings
with a plain-language explanation and fix. No secret-bearing field is present.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConsistencyFinding(BaseModel):
    id: str
    category: str
    area: str
    severity: str  # error | warning | info
    confidence: str  # high | medium | low
    title: str
    detail: str
    why: str = ""
    how_to_fix: str = ""
    subsystem: str = ""


class ConsistencyArea(BaseModel):
    key: str
    label: str
    status: str  # pass | warning | fail | not_tested


class ConsistencyReport(BaseModel):
    generated_at: str
    overall: str
    counts: dict[str, int] = Field(default_factory=dict)
    areas: list[ConsistencyArea] = Field(default_factory=list)
    findings: list[ConsistencyFinding] = Field(default_factory=list)


__all__ = ["ConsistencyArea", "ConsistencyFinding", "ConsistencyReport"]
