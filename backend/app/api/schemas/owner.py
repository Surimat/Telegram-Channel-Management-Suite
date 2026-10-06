"""Owner Auth + Config Sync API schemas (v1.6).

No schema ever carries a password, verifier, token or key. Responses describe
state only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OwnerStatusOut(BaseModel):
    exists: bool
    enabled: bool
    locked: bool
    method: str
    method_title: str
    display_name: str
    last_login_at: str
    failed_attempts: int
    locked_until: str
    recovery_hint: str
    auth_required: bool
    #: A short, non-secret explanation shown by the UI.
    local_only_note: str = ""


class OwnerSetupIn(BaseModel):
    secret: str = Field(min_length=4)
    method: str = "password"
    display_name: str = ""
    recovery_hint: str = ""


class OwnerSecretIn(BaseModel):
    secret: str = Field(min_length=1)


class OwnerChangeIn(BaseModel):
    current: str = Field(min_length=1)
    new_secret: str = Field(min_length=4)


class OwnerEnabledIn(BaseModel):
    enabled: bool


class OwnerTokenOut(BaseModel):
    token: str
    status: OwnerStatusOut


class SyncStatusOut(BaseModel):
    state: str
    state_label: str
    provider: str
    provider_label: str
    connected: bool
    enabled: bool
    owner_ready: bool
    local_revision: int
    cloud_revision: int
    device_id: str
    device_name: str
    cloud_device: str
    cloud_updated_at: str
    last_sync_at: str
    last_status: str
    message: str
    needs_reconnect: bool
    conflict: bool
    no_live_db_note: str = ""
    appdata_scope_note: str = ""


class SyncConfigureIn(BaseModel):
    provider: str
    enabled: bool = True


class SyncSecretIn(BaseModel):
    secret: str = Field(min_length=1)


class SyncApplyIn(BaseModel):
    secret: str = Field(min_length=1)
    keep_local: bool = False


class SyncGoogleConnectIn(BaseModel):
    access_token: str = Field(min_length=1)
    refresh_token: str = ""


class SyncGoogleAuthOut(BaseModel):
    configured: bool
    authorization_url: str
    state: str


class ConflictOut(BaseModel):
    local_revision: int
    cloud_revision: int
    cloud_device: str
    cloud_updated_at: str
    local_device: str
    detected: bool


class RestorePreviewOut(BaseModel):
    revision: int
    device_id: str
    device_name: str
    updated_at: str
    settings: dict[str, object]
    ui: dict[str, object]
    bot_count: int
    channel_count: int
    differing: list[str]


__all__ = [
    "ConflictOut",
    "OwnerChangeIn",
    "OwnerEnabledIn",
    "OwnerSecretIn",
    "OwnerSetupIn",
    "OwnerStatusOut",
    "OwnerTokenOut",
    "RestorePreviewOut",
    "SyncApplyIn",
    "SyncConfigureIn",
    "SyncGoogleAuthOut",
    "SyncGoogleConnectIn",
    "SyncSecretIn",
    "SyncStatusOut",
]
