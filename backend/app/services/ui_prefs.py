"""UI preferences (novice mode).

Small, non-secret, UI-facing preferences stored in the ``settings`` table so
they are shared by the Web UI, the Mini App and the Setup Wizard. Today there is
one: ``show_explanations`` ("Показывать пояснения"), which is **on by default**
so a beginner always sees the plain-language help. Turning it off keeps the
interface clean for an experienced user without losing any feature.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.services.settings_service import SettingsService

SHOW_EXPLANATIONS = "show_explanations"

_TITLES = {
    SHOW_EXPLANATIONS: "Показывать пояснения",
}

_DESCRIPTIONS = {
    SHOW_EXPLANATIONS: (
        "Показывать рядом с важными элементами краткое объяснение простыми словами: "
        "что это, зачем нужно и что будет, если выключить. Полезно новичкам."
    ),
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

    async def as_dict(self) -> dict[str, bool]:
        return {SHOW_EXPLANATIONS: await self.get_show_explanations()}


__all__ = ["SHOW_EXPLANATIONS", "UiPrefsService"]
