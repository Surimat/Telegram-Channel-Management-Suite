"""Pydantic schemas for the LAN Mesh API (v1.3).

Secrets (pairing codes, shared secrets) are write-only: they appear in requests
but never in responses.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MeshStatusOut(BaseModel):
    enabled: bool
    mode: str
    mode_label: str
    role: str
    node_id: str
    name: str
    capabilities: list[str]
    priority: int
    host: str
    port: int
    coordinator_id: str
    peers_total: int
    peers_trusted: int
    peers_online: int
    discovery_enabled: bool
    note: str


class MeshPeerOut(BaseModel):
    id: str
    node_id: str
    name: str
    version: str
    capabilities: list[str]
    priority: int
    host: str
    port: int
    trusted: bool
    status: str
    status_label: str
    last_seen: datetime | None
    note: str


class MeshPeerListOut(BaseModel):
    items: list[MeshPeerOut]
    total: int


class MeshPeerManualIn(BaseModel):
    host: str
    port: int
    name: str = ""


class MeshPairIn(BaseModel):
    code: str
    node_id: str = ""
    host: str = ""
    port: int = 0
    name: str = ""
    capabilities: list[str] | None = None
    priority: int = 0
    version: str = ""


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime | None


class MeshLeaseOut(BaseModel):
    id: str
    job_id: str
    kind: str
    lease_owner: str
    lease_until: datetime | None
    fencing_token: int
    status: str
    attempts: int
    error: str


class MeshLeaseListOut(BaseModel):
    items: list[MeshLeaseOut]
    total: int


class MeshLeaseAcquireIn(BaseModel):
    job_id: str
    kind: str = ""
    requirements: dict = Field(default_factory=dict)


class MeshLeaseCompleteIn(BaseModel):
    job_id: str
    owner: str
    token: int
    error: str = ""


class MeshPingIn(BaseModel):
    from_node_id: str = ""
