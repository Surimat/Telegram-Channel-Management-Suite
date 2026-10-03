"""Permission-probe schemas (post-1.0 hardening)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PermissionCheckIn(BaseModel):
    account_id: str = Field(description="ID пользовательского аккаунта.")
    target: str = Field(
        default="",
        description="Канал, группа или пользователь (@name, ссылка или ID). "
        "Можно не указывать, если задан channel_id.",
    )
    channel_id: str = Field(
        default="",
        description="Канал из общего реестра «Каналы» (подставит цель проверки).",
    )


class PermissionResultOut(BaseModel):
    status: str
    status_label: str
    account_id: str
    account_label: str
    target: str
    target_title: str = ""
    registry_channel_id: str = ""
    channel_found: bool = False
    authorized: bool = False
    can_read_info: bool = False
    can_read_participants: bool = False
    can_invite: bool = False
    session_ok: bool = False
    channel_id: int | None = None
    channel_username: str = ""
    channel_kind: str = ""
    participants_count: int | None = None
    message: str = ""
    how_to_fix: str = ""
    retry_after: int | None = None
    checked_at: datetime | None = None
    check_id: str | None = None

    @classmethod
    def from_result(cls, r: object) -> PermissionResultOut:
        return cls(
            status=r.status,  # type: ignore[attr-defined]
            status_label=r.status_label,  # type: ignore[attr-defined]
            account_id=r.account_id,  # type: ignore[attr-defined]
            account_label=r.account_label,  # type: ignore[attr-defined]
            target=r.target,  # type: ignore[attr-defined]
            target_title=r.target_title,  # type: ignore[attr-defined]
            registry_channel_id=r.registry_channel_id,  # type: ignore[attr-defined]
            channel_found=r.channel_found,  # type: ignore[attr-defined]
            authorized=r.authorized,  # type: ignore[attr-defined]
            can_read_info=r.can_read_info,  # type: ignore[attr-defined]
            can_read_participants=r.can_read_participants,  # type: ignore[attr-defined]
            can_invite=r.can_invite,  # type: ignore[attr-defined]
            session_ok=r.session_ok,  # type: ignore[attr-defined]
            channel_id=r.channel_id,  # type: ignore[attr-defined]
            channel_username=r.channel_username,  # type: ignore[attr-defined]
            channel_kind=r.channel_kind,  # type: ignore[attr-defined]
            participants_count=r.participants_count,  # type: ignore[attr-defined]
            message=r.message,  # type: ignore[attr-defined]
            how_to_fix=r.how_to_fix,  # type: ignore[attr-defined]
            retry_after=r.retry_after,  # type: ignore[attr-defined]
            checked_at=r.checked_at,  # type: ignore[attr-defined]
            check_id=r.check_id,  # type: ignore[attr-defined]
        )


class PermissionHistoryOut(BaseModel):
    items: list[PermissionResultOut]
    latest: PermissionResultOut | None = None
