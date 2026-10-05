"""Intent → reaction policy (v1.1).

The AI (rules, the lightweight encoder or the LLM) may report a communicative
*intent* for a post. Intent never chooses an emoji by itself (D-032); it only
*narrows* the set of emoji a profile may use, exactly like the category rule does.

The final reaction is always::

    profile allowed
      ∩ intent allowed (when the AI reported a non-neutral intent)
      ∩ channel available reactions (when verified)
      ∩ bot-compatible reactions   (when verified)
      − forbidden reactions

If the intersection is empty the caller skips the reaction and shows the reason —
it never forces an emoji the channel or the intent does not support.
"""

from __future__ import annotations

from backend.app.ai.types import Intent

#: Emoji a given intent permits. ``None``/neutral means "no narrowing" so a post
#: with no clear intent keeps the full profile/category policy.
INTENT_REACTIONS: dict[str, tuple[str, ...]] = {
    Intent.SUPPORT.value: ("❤", "❤️", "🙏", "👍", "🔥", "💪", "🤝"),
    Intent.SYMPATHY.value: ("😢", "🙏", "❤", "❤️", "💔"),
    Intent.JOY.value: ("🎉", "🥳", "❤", "❤️", "🔥", "👍", "😍"),
    Intent.HUMOR.value: ("😂", "🤣", "😄", "😁", "👍", "🔥"),
    Intent.ANGER.value: ("😡", "😠", "👎", "🤬"),
    Intent.SURPRISE.value: ("😮", "😲", "🤯", "🔥", "👀"),
    Intent.LOVE.value: ("❤", "❤️", "😍", "🥰", "😘", "💋"),
    Intent.NEUTRAL.value: (),  # no narrowing
}


def allowed_reactions_for_intent(intent: str) -> list[str] | None:
    """Return the emoji an intent permits, or ``None`` when it does not narrow.

    ``None`` means "keep the profile/category policy unchanged"; an empty list is
    never returned (neutral intents simply do not restrict).
    """
    key = (intent or "").strip().lower()
    if not key or key == Intent.NEUTRAL.value:
        return None
    values = INTENT_REACTIONS.get(key)
    if not values:
        return None
    return list(values)


def intent_narrows(intent: str) -> bool:
    """True when the intent restricts the reaction set."""
    return allowed_reactions_for_intent(intent) is not None


__all__ = ["INTENT_REACTIONS", "allowed_reactions_for_intent", "intent_narrows"]
