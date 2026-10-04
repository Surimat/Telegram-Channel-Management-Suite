"""Reaction Planner (PHASE 3).

Pure, deterministic-on-demand logic that turns a post + a reaction policy +
a list of active bots into a concrete list of planned reactions.

It performs **no** I/O and no Telegram calls, so it is trivially unit-testable.
Randomness comes from an injected :class:`random.Random` (``rng``), which makes
simulations and tests reproducible.

Guarantees:

* One reaction per bot per post (Telegram's own limit).
* Emoji chosen by weighted, deterministic logic — never by an LLM (D-005).
* Delays are spread out; bots never all fire at once.
* Categorised post can forbid emoji; forbidden emoji are never selected.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend.app.rules.delays import (
    DelayPreset,
    distribution_for,
    scaled_window,
)
from backend.app.rules.engine import RuleMatch


@dataclass(slots=True)
class PlanParams:
    """The subset of a profile the planner needs (kept free of ORM types)."""

    allowed_emoji: list[str] = field(default_factory=list)
    emoji_weights: dict[str, float] = field(default_factory=dict)
    participation_probability: float = 0.7
    skip_probability: float = 0.1
    delay_min: float = 30.0
    delay_max: float = 900.0
    delay_preset: DelayPreset = DelayPreset.NORMAL
    max_bots_per_post: int = 0
    # Channel reaction capabilities (product slice). ``None`` = unknown (the
    # profile set is used unchanged); a list = the emoji Telegram confirmed.
    channel_available: list[str] | None = None
    bot_compatible: list[str] | None = None


@dataclass(slots=True)
class PlannedReaction:
    """A single planned (or skipped) reaction, still without a DB row."""

    bot_id: str
    bot_username: str
    emoji: str
    delay_seconds: float
    scheduled_at: datetime
    status: str = "scheduled"  # "scheduled" | "skipped"


def _weighted_choice(
    emoji: list[str], weights: dict[str, float], rng: random.Random
) -> str:
    """Deterministic weighted choice over ``emoji`` (uniform when no weights)."""
    if not emoji:
        return ""
    total = 0.0
    for e in emoji:
        w = weights.get(e, 1.0)
        total += w if w > 0 else 0.0
    if total <= 0:
        return rng.choice(emoji)
    target = rng.uniform(0.0, total)
    acc = 0.0
    for e in emoji:
        w = weights.get(e, 1.0)
        if w <= 0:
            continue
        acc += w
        if target <= acc:
            return e
    return emoji[-1]


class ReactionPlanner:
    """Builds reaction plans. Instantiate with no state; pass an ``rng``."""

    def plan(
        self,
        *,
        post_id: str,
        bots: list[tuple[str, str]],
        params: PlanParams,
        match: RuleMatch | None = None,
        base_time: datetime,
        rng: random.Random,
    ) -> list[PlannedReaction]:
        """Return the planned reactions for one post.

        ``bots`` is a list of ``(bot_id, bot_username)`` pairs in a stable order.
        ``match`` (when given) supplies forbidden/preferred emoji constraints.
        """
        emoji_pool, weights = self._emoji_pool(params, match)
        forbidden = set(match.forbidden_reactions) if match else set()

        chosen: list[PlannedReaction] = []
        participants = 0
        max_bots = params.max_bots_per_post

        for bot_id, username in bots:
            # 1) Does this bot take part at all?
            if rng.random() >= params.participation_probability:
                continue
            if max_bots and participants >= max_bots:
                continue
            participants += 1

            # 2) Does it skip despite taking part?
            if rng.random() < params.skip_probability or not emoji_pool:
                chosen.append(
                    PlannedReaction(
                        bot_id=bot_id,
                        bot_username=username,
                        emoji="",
                        delay_seconds=0.0,
                        scheduled_at=base_time,
                        status="skipped",
                    )
                )
                continue

            # 3) Pick the emoji (weighted, deterministic).
            emoji = _weighted_choice(emoji_pool, weights, rng)
            if emoji in forbidden:  # defensive; pool already excludes these
                emoji = ""

            # 4) Pick the delay within the preset-scaled window.
            low, high = scaled_window(params.delay_preset, params.delay_min, params.delay_max)
            delay = distribution_for(params.delay_preset).sample(low, high, rng)

            chosen.append(
                PlannedReaction(
                    bot_id=bot_id,
                    bot_username=username,
                    emoji=emoji,
                    delay_seconds=round(delay, 3),
                    scheduled_at=base_time + timedelta(seconds=delay),
                    status="scheduled" if emoji else "skipped",
                )
            )

        # Stable, human-readable ordering: earliest planned reaction first.
        chosen.sort(key=lambda r: (r.status != "scheduled", r.scheduled_at, r.bot_username))
        return chosen

    # --- internals -----------------------------------------------------------
    @staticmethod
    def _emoji_pool(
        params: PlanParams, match: RuleMatch | None
    ) -> tuple[list[str], dict[str, float]]:
        """Combine the profile's emoji with the rule's allowed/forbidden policy.

        The channel's *real* capabilities (product slice) are applied first, so a
        profile can never schedule an emoji Telegram does not support in this
        channel. When the capability set is unknown (``None``), the profile set is
        used unchanged.
        """
        pool = list(params.allowed_emoji)
        if params.channel_available is not None:
            available = set(params.channel_available)
            pool = [e for e in pool if e in available]
        if params.bot_compatible is not None:
            compatible = set(params.bot_compatible)
            pool = [e for e in pool if e in compatible]
        if match and match.allowed_reactions:
            # Prefer the intersection when the rule restricts the profile.
            restricted = [e for e in pool if e in match.allowed_reactions]
            pool = restricted or [
                e for e in match.allowed_reactions if e in pool
            ] or list(match.allowed_reactions)
            if params.channel_available is not None:
                available = set(params.channel_available)
                pool = [e for e in pool if e in available]
        if match and match.forbidden_reactions:
            forbidden = set(match.forbidden_reactions)
            pool = [e for e in pool if e not in forbidden]
        weights = {e: params.emoji_weights.get(e, 1.0) for e in pool}
        return pool, weights


__all__ = ["PlanParams", "PlannedReaction", "ReactionPlanner"]
