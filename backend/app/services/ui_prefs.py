"""UI preferences (novice mode + language).

Small, non-secret, UI-facing preferences stored in the ``settings`` table so
they are shared by the Web UI, the Mini App and the Setup Wizard. Today there
are two: ``show_explanations`` ("Показывать пояснения"), **on by default** so a
beginner always sees the plain-language help, and ``language`` (RU/EN, default
RU). Turning explanations off keeps the interface clean for an experienced user
without losing any feature.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import i18n
from backend.app.services.settings_service import SettingsService

SHOW_EXPLANATIONS = "show_explanations"
LANGUAGE = "language"

_TITLES = {
    SHOW_EXPLANATIONS: "Показывать пояснения",
    LANGUAGE: "Язык интерфейса",
}

_DESCRIPTIONS = {
    SHOW_EXPLANATIONS: (
        "Показывать рядом с важными элементами краткое объяснение простыми словами: "
        "что это, зачем нужно и что будет, если выключить. Полезно новичкам."
    ),
    LANGUAGE: "Язык подсказок и служебных сообщений (русский или английский).",
}


class UiPrefsService:
    """Typed access to UI preferences (defaults applied when unset)."""

    def __init__(self, session: AsyncSession) -> None:
        self.settings = SettingsService(session)

    async def get_show_explanations(self) -> bool:
        value = await self.settings.get_typed(SHOW_EXPLANATIONS, True)
        return bool(value)

    async def set_show_explanations(self, enabled: bool) -> bool:
        await self.settings.repo.upsert(
            SHOW_EXPLANATIONS,
            "true" if enabled else "false",
            value_type="bool",
            title=_TITLES[SHOW_EXPLANATIONS],
            description=_DESCRIPTIONS[SHOW_EXPLANATIONS],
            default_value="true",
        )
        return enabled

    async def get_language(self) -> str:
        value = await self.settings.get_typed(LANGUAGE, i18n.DEFAULT_LANGUAGE)
        return i18n.normalize_language(str(value))

    async def set_language(self, language: str) -> str:
        normalized = i18n.normalize_language(language)
        await self.settings.repo.upsert(
            LANGUAGE,
            normalized,
            value_type="string",
            title=_TITLES[LANGUAGE],
            description=_DESCRIPTIONS[LANGUAGE],
            default_value=i18n.DEFAULT_LANGUAGE,
        )
        return normalized

    async def as_dict(self) -> dict[str, object]:
        return {
            SHOW_EXPLANATIONS: await self.get_show_explanations(),
            LANGUAGE: await self.get_language(),
            "available_languages": i18n.available_languages(),
        }


__all__ = ["LANGUAGE", "SHOW_EXPLANATIONS", "UiPrefsService"]
