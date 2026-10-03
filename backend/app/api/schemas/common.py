"""Common API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str = Field(description="Short machine-readable error code.")
    message: str = Field(description="Human-friendly message (RU-first).")
    hint: str = Field(default="", description="What the user can do next.")
    details: str | None = Field(default=None, description="Optional technical detail.")


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 50


class HealthStatus(BaseModel):
    status: str
    version: str
    timestamp: datetime
    checks: dict[str, str] = Field(default_factory=dict)
