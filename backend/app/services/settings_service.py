"""Settings service: typed access to UI-editable configuration."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.setting import Setting
from backend.app.db.repositories.settings import SettingRepository


class SettingsService:
    """Read/write application settings stored in the database.

    Values are stored as strings and converted according to ``value_type``.
    Secrets are never stored here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.repo = SettingRepository(session)

    async def all(self) -> list[Setting]:
        return await self.repo.list_all()

    async def get_raw(self, key: str) -> str | None:
        setting = await self.repo.get(key)
        return setting.value if setting else None

    async def get_typed(self, key: str, default: object = None) -> object:
        setting = await self.repo.get(key)
        if setting is None:
            return default
        return self._convert(setting.value, setting.value_type, default)

    async def set(self, key: str, value: object) -> Setting:
        existing = await self.repo.get(key)
        value_type = existing.value_type if existing else self._infer_type(value)
        serialized = self._serialize(value, value_type)
        return await self.repo.upsert(
            key, serialized, value_type=value_type, title=existing.title if existing else ""
        )

    @staticmethod
    def _infer_type(value: object) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, (dict, list)):
            return "json"
        return "string"

    @staticmethod
    def _serialize(value: object, value_type: str) -> str:
        if value_type == "json":
            return json.dumps(value)
        if value_type == "bool":
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _convert(raw: str, value_type: str, default: object) -> object:
        try:
            if value_type == "int":
                return int(raw)
            if value_type == "float":
                return float(raw)
            if value_type == "bool":
                return raw.strip().lower() in {"1", "true", "yes", "on"}
            if value_type == "json":
                return json.loads(raw) if raw else default
            return raw
        except (ValueError, json.JSONDecodeError):
            return default
