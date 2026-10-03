"""Reaction Planner tests: weighted selection, skip, delays, uniqueness.

All randomness is injected, so every assertion is deterministic.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from backend.app.rules.delays import DelayPreset
from backend.app.rules.engine import Category, RuleMatch
from backend.app.services.reaction_planner import PlanParams, ReactionPlanner

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
BOTS = [("b1", "Bot 01"), ("b2", "Bot 02"), ("b3", "Bot 03"), ("b4", "Bot 04")]


def _params(**overrides: object) -> PlanParams:
    values: dict[str, object] = {
        "allowed_emoji": ["👍", "❤️", "🔥"],
        "emoji_weights": {},
        "participation_probability": 1.0,
        "skip_probability": 0.0,
        "delay_min": 10.0,
        "delay_max": 20.0,
        "delay_preset": DelayPreset.NORMAL,
    }
    values.update(overrides)
    return PlanParams(**values)  # type: ignore[arg-type]


def test_one_reaction_per_bot() -> None:
    plan = ReactionPlanner().plan(
        post_id="p", bots=BOTS, params=_params(), base_time=BASE, rng=random.Random(1)
    )
    # One entry per bot (the plan is sorted by scheduled time, not bot order).
    assert sorted(p.bot_id for p in plan) == sorted(b[0] for b in BOTS)
    assert all(p.emoji in {"👍", "❤️", "🔥"} for p in plan)


def test_zero_participation_means_no_participants() -> None:
    plan = ReactionPlanner().plan(
        post_id="p",
        bots=BOTS,
        params=_params(participation_probability=0.0),
        base_time=BASE,
        rng=random.Random(1),
    )
    assert plan == []


def test_full_skip_probability_skips_everyone() -> None:
    plan = ReactionPlanner().plan(
        post_id="p",
        bots=BOTS,
        params=_params(skip_probability=1.0),
        base_time=BASE,
        rng=random.Random(1),
    )
    assert len(plan) == len(BOTS)
    assert all(p.status == "skipped" and p.emoji == "" for p in plan)


def test_delays_are_within_window_and_not_all_equal() -> None:
    plan = ReactionPlanner().plan(
        post_id="p", bots=BOTS, params=_params(), base_time=BASE, rng=random.Random(3)
    )
    deltas = [(p.scheduled_at - BASE).total_seconds() for p in plan]
    assert all(10.0 <= d <= 20.0 for d in deltas)
    assert len(set(deltas)) > 1  # spread out, not simultaneous


def test_forbidden_reactions_never_chosen() -> None:
    match = RuleMatch(
        category=Category.DONATION,
        confidence=0.9,
        allowed_reactions=["👍", "❤️", "🔥"],
        forbidden_reactions=["🔥"],
    )
    plan = ReactionPlanner().plan(
        post_id="p",
        bots=BOTS,
        params=_params(),
        match=match,
        base_time=BASE,
        rng=random.Random(5),
    )
    assert all(p.emoji != "🔥" for p in plan)


def test_rule_allowed_restricts_profile_pool() -> None:
    match = RuleMatch(
        category=Category.DONATION,
        confidence=0.9,
        allowed_reactions=["❤️"],
    )
    plan = ReactionPlanner().plan(
        post_id="p",
        bots=BOTS,
        params=_params(),
        match=match,
        base_time=BASE,
        rng=random.Random(2),
    )
    assert all(p.emoji == "❤️" for p in plan if p.status == "scheduled")


def test_weighted_choice_favours_heavier_emoji() -> None:
    params = _params(allowed_emoji=["👍", "❤️"], emoji_weights={"👍": 0.0, "❤️": 100.0})
    plan = ReactionPlanner().plan(
        post_id="p", bots=BOTS, params=params, base_time=BASE, rng=random.Random(9)
    )
    assert all(p.emoji == "❤️" for p in plan)


def test_max_bots_per_post_cap() -> None:
    plan = ReactionPlanner().plan(
        post_id="p",
        bots=BOTS,
        params=_params(max_bots_per_post=2),
        base_time=BASE,
        rng=random.Random(4),
    )
    assert len(plan) == 2


def test_deterministic_with_same_seed() -> None:
    params = _params(participation_probability=0.6, skip_probability=0.2)
    a = ReactionPlanner().plan(
        post_id="p", bots=BOTS, params=params, base_time=BASE, rng=random.Random(77)
    )
    b = ReactionPlanner().plan(
        post_id="p", bots=BOTS, params=params, base_time=BASE, rng=random.Random(77)
    )
    assert [(x.bot_id, x.emoji, x.delay_seconds) for x in a] == [
        (x.bot_id, x.emoji, x.delay_seconds) for x in b
    ]


def test_empty_emoji_pool_skips_participants() -> None:
    plan = ReactionPlanner().plan(
        post_id="p",
        bots=BOTS,
        params=_params(allowed_emoji=[]),
        base_time=BASE,
        rng=random.Random(1),
    )
    assert all(p.status == "skipped" for p in plan)
