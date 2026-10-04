"""Schemas for invite-link campaigns and donor quality analytics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str
    channel_id: str = ""
    target: str = ""
    risk_mode: str = "standard"
    requires_approval: bool = False
    note: str = ""


class CampaignStatusIn(BaseModel):
    status: str


class CampaignLinkIn(BaseModel):
    label: str = ""
    join_request: bool = False
    member_limit: int = 0


class CampaignLinkOut(BaseModel):
    id: str
    label: str
    link: str
    status: str
    join_request: bool = False
    member_limit: int = 0
    joins_count: int = 0
    requests_count: int = 0
    last_error: str = ""


class CampaignOut(BaseModel):
    id: str
    name: str
    status: str
    channel_id: str = ""
    target_title: str = ""
    risk_mode: str
    links_count: int = 0
    joins_count: int = 0
    requests_count: int = 0
    conversion: float | None = None
    summary: str = ""


class CampaignDetailOut(BaseModel):
    campaign: CampaignOut
    links: list[CampaignLinkOut] = Field(default_factory=list)
    requests_pending: int = 0
    requests_approved: int = 0


class CampaignListOut(BaseModel):
    items: list[CampaignOut]
    total: int
    risk_modes: dict[str, str] = Field(default_factory=dict)


class DonorMetricOut(BaseModel):
    id: str
    source_id: str
    channel_id: str = ""
    title: str = ""
    subscribers: int = 0
    quality: str
    quality_title: str = ""
    quality_score: float = 0.0
    bot_probability: str
    confidence: str
    participant_data: bool = False
    bot_share_estimate: float | None = None
    signals: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    summary: str = ""
    source_completeness: str = ""
    last_analyzed: datetime | None = None


class DonorListOut(BaseModel):
    items: list[DonorMetricOut]
    total: int
    note: str = ""
