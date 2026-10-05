"""Worker capability matching (pure).

A job declares which capabilities it needs (e.g. ``telegram`` for anything that
talks to Telegram, ``ai`` for the mini classifier). A node advertises a set of
capabilities. A node may run the job only if it advertises every required
capability — so a phone/weak PC without the AI runtime never gets an AI job.
"""

from __future__ import annotations

import json

from backend.app.db.models.mesh import ALL_CAPABILITIES


def parse_capabilities(raw: str | list[str] | None) -> list[str]:
    """Parse a JSON list (stored form) into a normalised capability list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        values = [str(v).strip().lower() for v in raw]
    else:
        text = (raw or "").strip()
        if not text:
            return []
        try:
            loaded = json.loads(text)
        except (ValueError, TypeError):
            loaded = list(text.split(","))
        values = [str(v).strip().lower() for v in loaded]
    known = set(ALL_CAPABILITIES)
    return [v for v in values if v in known]


def serialize_capabilities(values: list[str] | None) -> str:
    return json.dumps(sorted(set(parse_capabilities(values))))


def capability_matches(required: list[str] | None, available: list[str] | None) -> bool:
    """True when ``available`` satisfies every capability in ``required``."""
    need = set(required or [])
    have = set(available or [])
    return need.issubset(have)


__all__ = ["capability_matches", "parse_capabilities", "serialize_capabilities"]
