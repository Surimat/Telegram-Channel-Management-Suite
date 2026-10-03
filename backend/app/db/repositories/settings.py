"""Setting repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.setting import Setting


class SettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Setting]:
        result = await self.session.execute(select(Setting).order_by(Setting.key))
        return list(result.scalars().all())

    async def get(self, key: str) -> Setting | None:
        result = await self.session.execute(select(Setting).where(Setting.key == key))
        return result.scalar_one_or_none()

    async def upsert(
        self,
        key: str,
        value: str,
        *,
        value_type: str = "string",
        title: str = "",
        description: str = "",
        default_value: str = "",
        is_secret: bool = False,
    ) -> Setting:
        setting = await self.get(key)
        if setting is None:
            setting = Setting(
                key=key,
                value=value,
                value_type=value_type,
                title=title,
                description=description,
                default_value=default_value,
                is_secret=is_secret,
            )
            self.session.add(setting)
        else:
            setting.value = value
            if title:
                setting.title = title
            if description:
                setting.description = description
            if default_value:
                setting.default_value = default_value
        await self.session.flush()
        return setting
