"""AI API schemas (PHASE 7, RU-first).

Complex settings carry plain-language help in ``*_help`` so the UI explains what
each control does, why it exists, what happens at large values, and a safe
default — without hardcoding copy in the frontend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AiSettingHelp(BaseModel):
    key: str
    title: str
    value_type: str
    value: str
    default_value: str
    what_it_does: str
    why: str
    large_value_effect: str
    safe_default: str


class AiSettingIn(BaseModel):
    value: object


class AiStatusOut(BaseModel):
    enabled: bool
    backend: str
    runtime_available: bool
    model_path: str
    model_exists: bool
    model_size_bytes: int
    model_size_human: str
    model_loaded: bool
    effective: bool
    reason: str
    how_to_fix: str


class AiModelOut(BaseModel):
    name: str
    path: str
    size_bytes: int
    size_human: str


class AiModelCheckOut(BaseModel):
    ok: bool
    runtime_available: bool
    model_exists: bool
    message: str
    how_to_fix: str
    size_bytes: int = 0
    load_ms: int = 0


class AiMetricsOut(BaseModel):
    rules_count: int = 0
    ai_count: int = 0
    fallback_count: int = 0
    manual_count: int = 0
    ai_error_count: int = 0
    average_latency_ms: int = 0
    last_latency_ms: int = 0
    model_load_ms: int = 0
    total_classifications: int = 0


class AiClassifyIn(BaseModel):
    text: str = Field(description="Текст поста для анализа.")
    mode: str = Field(default="auto", description="auto | rules | encoder | ai")


class AiClassifyOut(BaseModel):
    category: str
    category_title: str
    tone: str
    intent: str = ""
    suggested_emoji: str = ""
    confidence: float
    source: str
    source_title: str
    model: str
    processing_time_ms: int
    mode: str
    ai_attempted: bool
    ai_used: bool
    encoder_attempted: bool = False
    encoder_used: bool = False
    fallback_used: bool
    ai_error: str

    model_config = ConfigDict(from_attributes=True)


class AiRecordOut(BaseModel):
    id: str
    source: str
    category: str
    tone: str
    confidence: float
    model: str
    latency_ms: int
    mode: str
    ok: bool
    detail: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AiOverviewOut(BaseModel):
    status: AiStatusOut
    metrics: AiMetricsOut
    today: AiMetricsOut


class EncoderStatusOut(BaseModel):
    """v1.1 lightweight encoder install status (honest, never a guess)."""

    runtime_available: bool
    installed: bool
    ready: bool
    model_dir: str
    size_bytes: int
    size_human: str
    missing: list[str] = []
    message: str
    how_to_fix: str
    repo: str = ""
    license: str = ""


class EncoderActionResultOut(BaseModel):
    ok: bool
    message: str
    how_to_fix: str = ""
    downloaded: int = 0
    status: EncoderStatusOut


class AiHistoryOut(BaseModel):
    items: list[AiRecordOut]
    total: int


class AiSettingsOut(BaseModel):
    items: list[AiSettingHelp]


class AiSettingsUpdate(BaseModel):
    values: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "AiClassifyIn",
    "AiClassifyOut",
    "AiHistoryOut",
    "AiMetricsOut",
    "AiModelCheckOut",
    "AiModelOut",
    "AiOverviewOut",
    "AiRecordOut",
    "AiSettingHelp",
    "AiSettingsOut",
    "AiSettingsUpdate",
    "AiStatusOut",
]
