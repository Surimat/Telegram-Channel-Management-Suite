"""Settings schemas. Secrets are never exposed; secret rows are masked."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    value_type: str
    title: str
    description: str
    default_value: str
    is_secret: bool


class SettingsUpdate(BaseModel):
    values: dict[str, str]
