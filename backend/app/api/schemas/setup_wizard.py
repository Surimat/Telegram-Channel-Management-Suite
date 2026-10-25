"""Schemas for the end-to-end Setup Wizard (D-128)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SetupStepOut(BaseModel):
    key: str
    title: str
    description: str
    status: str
    status_title: str
    verified: bool
    message: str = ""
    how_to_fix: str = ""
    route: str = ""
    verified_at: str | None = None
    attempts: int = 0


class SetupWizardStateOut(BaseModel):
    steps: list[SetupStepOut] = Field(default_factory=list)
    completed_steps: int
    total_steps: int
    ready: bool
    progress_percent: int
    current_step: str
    test_publication_available: bool
    test_publication_hint: str = ""
    notes: list[str] = Field(default_factory=list)


class SetupStepRunIn(BaseModel):
    account_id: str = ""


class TestPublicationIn(BaseModel):
    confirmed: bool = False


class TestPublicationOut(BaseModel):
    ok: bool
    message: str
    how_to_fix: str = ""
    publication_id: str = ""
    channel_id: str = ""
    channel_label: str = ""
