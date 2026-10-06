"""Help / explanations schemas (novice mode)."""

from __future__ import annotations

from pydantic import BaseModel


class HelpTopicOut(BaseModel):
    """One beginner-facing explanation."""

    key: str
    title: str
    what: str
    why: str = ""
    effect: str = ""
    when_off: str = ""
    safe_default: str = ""


class UiPrefsOut(BaseModel):
    """UI preferences shared by the Web UI, Mini App and Setup Wizard."""

    show_explanations: bool = True
    language: str = "ru"
    available_languages: list[str] = ["ru", "en"]


class UiPrefsUpdate(BaseModel):
    show_explanations: bool | None = None
    language: str | None = None
