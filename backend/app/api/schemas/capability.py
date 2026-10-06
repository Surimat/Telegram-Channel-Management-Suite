"""Capability graph schemas (v1.5).

One machine-readable description of what the product can do and what each
capability requires, so the UI and the Promotion Wizard stop re-encoding
"does this need a session?" logic in every view.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CapabilityStateOut(BaseModel):
    key: str
    title: str
    state: str  # available | partial | needs_setup | unavailable
    state_label: str
    requires: list[str] = Field(default_factory=list)
    satisfied: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    missing_fixes: list[str] = Field(default_factory=list)
    note: str = ""


__all__ = ["CapabilityStateOut"]
