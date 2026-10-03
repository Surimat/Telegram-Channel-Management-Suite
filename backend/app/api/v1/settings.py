"""Settings router. Secret values are never returned (masked)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas.settings import SettingOut, SettingsUpdate
from backend.app.db.session import get_session
from backend.app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])

_MASK = "********"


@router.get("", response_model=list[SettingOut])
async def list_settings(session: AsyncSession = Depends(get_session)) -> list[SettingOut]:
    service = SettingsService(session)
    rows = await service.all()
    out: list[SettingOut] = []
    for row in rows:
        value = _MASK if row.is_secret and row.value else row.value
        out.append(
            SettingOut(
                key=row.key,
                value=value,
                value_type=row.value_type,
                title=row.title,
                description=row.description,
                default_value=row.default_value,
                is_secret=row.is_secret,
            )
        )
    return out


@router.patch("", response_model=list[SettingOut])
async def update_settings(
    payload: SettingsUpdate, session: AsyncSession = Depends(get_session)
) -> list[SettingOut]:
    service = SettingsService(session)
    for key, value in payload.values.items():
        await service.set(key, value)
    await session.commit()
    return await list_settings(session)
