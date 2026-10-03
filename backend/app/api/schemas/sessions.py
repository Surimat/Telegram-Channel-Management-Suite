"""User-session API schemas (PHASE 4).

Responses NEVER include the session file contents, the API hash, the full phone
number or any credential (decisions D-010, D-025). ``has_session`` /
``has_api_hash`` indicate presence without revealing values; ``phone_masked``
carries a display-safe form.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    telegram_user_id: int | None = None
    username: str = ""
    display_name: str = ""
    phone_masked: str = ""
    api_id: str = ""
    status: str
    enabled: bool
    auth_step: str = "idle"
    has_session: bool = False
    has_api_hash: bool = False
    session_file_exists: bool = False
    session_file_size: int = 0
    status_message: str = ""
    status_hint: str = ""
    last_error: str = ""
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls, account: object, *, file_exists: bool = False, file_size: int = 0
    ) -> SessionOut:
        return cls(
            id=account.id,  # type: ignore[attr-defined]
            telegram_user_id=account.telegram_user_id,  # type: ignore[attr-defined]
            username=account.username,  # type: ignore[attr-defined]
            display_name=account.display_name,  # type: ignore[attr-defined]
            phone_masked=account.phone_masked,  # type: ignore[attr-defined]
            api_id=account.api_id,  # type: ignore[attr-defined]
            status=account.status.value,  # type: ignore[attr-defined]
            enabled=account.enabled,  # type: ignore[attr-defined]
            auth_step=account.auth_step,  # type: ignore[attr-defined]
            has_session=account.has_session,  # type: ignore[attr-defined]
            has_api_hash=account.has_api_hash,  # type: ignore[attr-defined]
            session_file_exists=file_exists,
            session_file_size=file_size,
            status_message=account.status_message,  # type: ignore[attr-defined]
            status_hint=account.status_hint,  # type: ignore[attr-defined]
            last_error=account.last_error,  # type: ignore[attr-defined]
            last_checked_at=account.last_checked_at,  # type: ignore[attr-defined]
            created_at=account.created_at,  # type: ignore[attr-defined]
            updated_at=account.updated_at,  # type: ignore[attr-defined]
        )


class SessionSummary(BaseModel):
    total: int
    active: int
    online: int
    auth_required: int
    disabled: int
    error: int
    by_status: dict[str, int]


class AccountIdentityOut(BaseModel):
    """Display-only identity (no phone number, no secrets)."""

    id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""


class AuthStartIn(BaseModel):
    api_id: str = Field(description="API ID с https://my.telegram.org")
    api_hash: str = Field(description="API Hash с https://my.telegram.org")
    phone: str = Field(description="Номер телефона в международном формате, например +79991234567")
    display_name: str = ""


class AuthStartOut(BaseModel):
    account_id: str | None = None
    next_step: str
    message: str
    how_to_fix: str = ""
    phone_masked: str = ""


class AuthCodeIn(BaseModel):
    code: str


class AuthPasswordIn(BaseModel):
    password: str


class AuthStepOut(BaseModel):
    account_id: str
    next_step: str
    done: bool
    message: str
    how_to_fix: str = ""
    identity: AccountIdentityOut | None = None


class SessionImportIn(BaseModel):
    api_id: str
    api_hash: str
    phone: str = ""
    session_file_path: str = Field(
        description="Путь к существующему .session файлу на этом компьютере."
    )
    display_name: str = ""


class SessionHealthOut(BaseModel):
    account_id: str
    ok: bool
    status: str
    message: str
    how_to_fix: str = ""
