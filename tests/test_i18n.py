"""i18n catalog tests (v1.5).

The catalog is the single source of truth for backend-produced user strings.
Every key must have both RU and EN text, and translation must fall back safely.
"""

from __future__ import annotations

from backend.app.core import i18n


def test_catalog_has_no_missing_languages() -> None:
    assert i18n.missing_keys() == {}


def test_translate_returns_russian_by_default() -> None:
    assert i18n.translate("cap.channel") == "Канал"


def test_translate_returns_english() -> None:
    assert i18n.translate("cap.channel", "en") == "Channel"


def test_unknown_key_returns_key_or_default() -> None:
    assert i18n.translate("does.not.exist") == "does.not.exist"
    assert i18n.translate("does.not.exist", default="fallback") == "fallback"


def test_normalize_language_falls_back_to_russian() -> None:
    assert i18n.normalize_language(None) == "ru"
    assert i18n.normalize_language("de") == "ru"
    assert i18n.normalize_language("EN") == "en"
    assert i18n.normalize_language("ru-RU") == "ru"


def test_risk_wording_is_single_sourced() -> None:
    text = i18n.translate("risk.user_account")
    assert "ограничениям" in text
    assert "безопасного лимита" in text
