"""Reaction policy: intersect a profile with the channel's *real* capabilities.

Pure, dependency-free logic (no I/O, no Telegram) so it is trivially testable and
reusable by both the planner and the UI preview.

The order is exactly what the product requires::

    requested (profile)
      ∩ channel available reactions   (when known)
      ∩ bot-compatible reactions      (when known)
      ∩ profile allowed reactions
      − forbidden reactions

If nothing survives the intersection, the policy does **not** invent a reaction:
it returns an empty candidate set plus a plain-language reason, and the caller
skips the reaction instead of failing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ReactionPolicyResult:
    """The usable emoji for one channel, with an honest explanation."""

    candidates: list[str] = field(default_factory=list)
    channel_known: bool = False
    skipped_reason: str = ""

    @property
    def can_react(self) -> bool:
        return bool(self.candidates)


def intersect_reactions(
    *,
    requested: list[str],
    profile_allowed: list[str] | None = None,
    channel_available: list[str] | None = None,
    bot_compatible: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> ReactionPolicyResult:
    """Return the emoji usable in this channel for this profile.

    ``channel_available``/``bot_compatible`` of ``None`` mean "unknown" — in that
    case the profile set is used unchanged (the bot will find out at send time),
    but ``channel_known`` is False so the UI can say the set was not verified.
    An *empty list* is different from ``None``: it means Telegram confirmed there
    are no usable reactions, so the result is empty with a clear reason.
    """
    base = list(dict.fromkeys(requested or []))
    if profile_allowed:
        allowed = set(profile_allowed)
        base = [e for e in base if e in allowed]

    channel_known = channel_available is not None
    if channel_available is not None:
        available = set(channel_available)
        base = [e for e in base if e in available]

    if bot_compatible is not None:
        compat = set(bot_compatible)
        base = [e for e in base if e in compat]

    if forbidden:
        banned = set(forbidden)
        base = [e for e in base if e not in banned]

    if not base:
        return ReactionPolicyResult(
            candidates=[],
            channel_known=channel_known,
            skipped_reason=_reason(channel_known, channel_available, bot_compatible),
        )
    return ReactionPolicyResult(candidates=base, channel_known=channel_known)


def _reason(
    channel_known: bool,
    channel_available: list[str] | None,
    bot_compatible: list[str] | None,
) -> str:
    if channel_known and not channel_available:
        return "В этом канале нет доступных реакций."
    if bot_compatible is not None and not bot_compatible:
        return "Ни одну из реакций профиля нельзя поставить от имени бота."
    if channel_known:
        return (
            "Ни одна из реакций профиля не поддерживается этим каналом. "
            "Проверьте набор реакций канала."
        )
    return "Нет подходящих реакций после применения правил профиля."


def describe_available(available: list[str], *, limit: int = 8) -> str:
    """A short, UI-friendly list like ``❤️ 👍 🔥`` (truncated when long)."""
    if not available:
        return ""
    shown = available[:limit]
    text = " ".join(shown)
    if len(available) > limit:
        text += f" и ещё {len(available) - limit}"
    return text


__all__ = ["ReactionPolicyResult", "describe_available", "intersect_reactions"]
