"""Schemas for backup destinations, promotion wizard and auto-update."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.api.schemas.capability import CapabilityStateOut


class DestinationIn(BaseModel):
    kind: str
    label: str = ""
    enabled: bool = True
    config: dict[str, object] = Field(default_factory=dict)
    token: str = ""


class DestinationUpdate(BaseModel):
    enabled: bool | None = None
    label: str | None = None
    config: dict[str, object] | None = None
    token: str | None = None


class DestinationOut(BaseModel):
    id: str
    kind: str
    title: str
    label: str
    enabled: bool
    status: str
    account_label: str = ""
    config: dict[str, object] = Field(default_factory=dict)
    last_backup_at: str | None = None
    last_error: str = ""
    available_space: int | None = None


class DestinationListOut(BaseModel):
    items: list[DestinationOut]
    total: int
    available_kinds: list[dict[str, object]] = Field(default_factory=list)


class DeliveryResultOut(BaseModel):
    destination_id: str
    kind: str
    ok: bool
    message: str


class WizardStepOut(BaseModel):
    key: str
    title: str
    description: str
    status: str
    status_title: str
    how_to_fix: str = ""
    route: str = ""
    requires_session: bool = False


class WizardStateOut(BaseModel):
    preset: str
    preset_title: str
    preset_description: str
    has_session: bool
    mode: str
    completed: bool
    dismissed: bool
    current_step: str
    completed_steps: int
    total_steps: int
    steps: list[WizardStepOut] = Field(default_factory=list)
    session_optional_note: str = ""
    session_risk_note: str = ""
    capabilities: list[CapabilityStateOut] = Field(default_factory=list)


class PresetOut(BaseModel):
    id: str
    title: str
    description: str
    requires_session: bool


class WizardPresetIn(BaseModel):
    preset: str


class WizardStepIn(BaseModel):
    step: str


class UpdateStatusOut(BaseModel):
    enabled: bool
    state: str
    state_title: str
    current_version: str
    latest_version: str = ""
    update_available: bool = False
    release_url: str = ""
    release_notes: str = ""
    staged_file: str = ""
    staged_sha256: str = ""
    last_checked_at: str | None = None
    message: str = ""
    last_error: str = ""


class UpdateToggleIn(BaseModel):
    enabled: bool
