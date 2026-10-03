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
