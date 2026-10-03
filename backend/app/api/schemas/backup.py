"""Backup / restore API schemas (PHASE 10, RU-first)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BackupEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    kind: str
    created_at: datetime | None = None
    size_bytes: int
    size_human: str
    includes_sessions: bool
    version: str = ""


class BackupListOut(BaseModel):
    items: list[BackupEntryOut]
    total: int
    backup_dir: str = Field(description="Where backups are stored (local path).")
    retention: int = Field(description="How many recent backups are kept (0 = all).")
    include_sessions_default: bool = Field(
        description="Whether new backups include session files by default."
    )


class BackupCreateIn(BaseModel):
    include_sessions: bool | None = Field(
        default=None,
        description="Include MTProto session files. Defaults to the configured value.",
    )
    note: str = Field(default="", max_length=200, description="Optional human note.")


class RestoreResultOut(BaseModel):
    restored: bool
    source: str
    safety_backup: str
    includes_sessions: bool


class ImportConfigOut(BaseModel):
    imported: dict[str, int]
    message: str


class BackupInfoOut(BaseModel):
    """Plain-language explanation shown next to the controls."""

    what_it_does: str
    why: str
    sessions_warning: str
    safe_default: str
    excluded_tables: list[str]
