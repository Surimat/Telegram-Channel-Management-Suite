"""Delay distribution tests (PHASE 3)."""

from __future__ import annotations

import random

from backend.app.rules.delays import (
    DelayPreset,
    UniformDelay,
    distribution_for,
    scaled_window,
)


def test_uniform_within_window() -> None:
    rng = random.Random(42)
    dist = UniformDelay()
    for _ in range(200):
        value = dist.sample(10.0, 20.0, rng)
        assert 10.0 <= value <= 20.0


def test_uniform_degenerate_window() -> None:
    rng = random.Random(1)
    assert UniformDelay().sample(5.0, 5.0, rng) == 5.0
    assert UniformDelay().sample(5.0, 1.0, rng) == 5.0


def test_scaled_window_stays_inside_source() -> None:
    for preset in DelayPreset:
        low, high = scaled_window(preset, 100.0, 1000.0)
        assert 100.0 <= low <= high <= 1000.0


def test_early_preset_is_earlier_than_spread() -> None:
    early_low, early_high = scaled_window(DelayPreset.EARLY, 0.0, 100.0)
    spread_low, spread_high = scaled_window(DelayPreset.SPREAD, 0.0, 100.0)
    assert early_high < spread_high
    assert early_low <= spread_low


def test_distribution_for_returns_distribution() -> None:
    for preset in DelayPreset:
        dist = distribution_for(preset)
        rng = random.Random(7)
        assert 0.0 <= dist.sample(0.0, 50.0, rng) <= 50.0


def test_deterministic_with_seed() -> None:
    a = UniformDelay().sample(0.0, 100.0, random.Random(123))
    b = UniformDelay().sample(0.0, 100.0, random.Random(123))
    assert a == b
