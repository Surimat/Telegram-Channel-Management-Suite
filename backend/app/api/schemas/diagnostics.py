"""Diagnostics schemas.

Used by the Diagnostics page and the redacted report download. The report
schemas deliberately contain no secret-bearing field: the payload is built and
redacted server-side, then returned as a file.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiagnosticItem(BaseModel):
    """One diagnostic row, explained in plain language."""

    key: str
    title: str
    status: str  # ok | warning | error | not_configured | unknown
    status_label: str
    meaning: str
    how_to_fix: str = ""


class DiagnosticsReport(BaseModel):
    """Aggregate diagnostics for the Diagnostics page."""

    version: str
    environment: str
    overall: str
    overall_label: str
    generated_at: str
    items: list[DiagnosticItem]


class MaintenanceAction(BaseModel):
    """A safe maintenance/repair action offered to the owner."""

    key: str
    title: str
    description: str
    destructive: bool = False
    requires_confirmation: bool = False
    available: bool = True


class MaintenanceResult(BaseModel):
    """Outcome of a maintenance action."""

    action: str
    ok: bool
    message: str
    detail: str = ""
    affected: int = 0


class ReportFormat(BaseModel):
    """Available report export formats (for the UI)."""

    formats: list[str] = Field(default_factory=lambda: ["json", "txt", "zip"])
