"""System / setup wizard schemas."""

from __future__ import annotations

from pydantic import BaseModel


class SetupCheck(BaseModel):
    key: str
    title: str
    status: str  # ok | warning | error | unknown
    meaning: str
    how_to_fix: str = ""


class SystemStatus(BaseModel):
    version: str
    environment: str
    checks: list[SetupCheck]
    overall: str


class DatabaseMigrationStatus(BaseModel):
    """Beginner-facing database migration state (docs/UI.md)."""

    state: str  # fresh | ready | pending | updating | updated | failed | unknown
    message: str
    current_revision: str | None = None
    head_revision: str = ""
    pending_count: int = 0
    error: str = ""


class DatabaseMigrationResult(BaseModel):
    state: str
    message: str
    applied: list[str] = []
    backup_file: str | None = None
    error: str = ""
