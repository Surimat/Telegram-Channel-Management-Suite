"""Delay distributions for reaction scheduling (PHASE 3).

A distribution turns a per-bot delay window into a concrete delay in seconds.
Only ``uniform`` is required; the abstraction leaves room for triangular / beta /
exponential shapes later without touching the planner.

The random source is injectable (:class:`random.Random`) so tests are fully
deterministic and the planner never depends on global RNG state.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class DelayPreset(StrEnum):
    """Human-friendly presets shown in the UI.

    * ``early``  — bots react quickly, packed close together.
    * ``normal`` — balanced spread over the window.
    * ``spread`` — reactions trickle out over the whole window.
    """

    EARLY = "early"
    NORMAL = "normal"
    SPREAD = "spread"


#: Scale factor applied to a bot's delay window per preset (start, span).
_PRESET_SCALE: dict[DelayPreset, tuple[float, float]] = {
    DelayPreset.EARLY: (0.0, 0.35),
    DelayPreset.NORMAL: (0.15, 0.7),
    DelayPreset.SPREAD: (0.0, 1.0),
}

PRESET_TITLES: dict[DelayPreset, str] = {
    DelayPreset.EARLY: "Быстро — боты реагируют почти сразу",
    DelayPreset.NORMAL: "Обычно — равномерно по времени",
    DelayPreset.SPREAD: "Растянуто — реакции распределены по окну",
}


@runtime_checkable
class DelayDistribution(Protocol):
    """Produces a delay (seconds) inside ``[low, high]``."""

    def sample(self, low: float, high: float, rng: random.Random) -> float:
        """Return a delay in seconds within the window."""


@dataclass(slots=True)
class UniformDelay:
    """Uniform distribution over the delay window (the default)."""

    def sample(self, low: float, high: float, rng: random.Random) -> float:
        if high <= low:
            return max(0.0, low)
        return rng.uniform(low, high)


def distribution_for(preset: DelayPreset) -> DelayDistribution:
    """Map a UI preset to a concrete distribution.

    All presets currently use :class:`UniformDelay`; the preset only rescales the
    window. This keeps behaviour predictable while reserving the interface for
    non-uniform distributions later.
    """
    return UniformDelay()


def scaled_window(
    preset: DelayPreset, low: float, high: float
) -> tuple[float, float]:
    """Apply the preset scale to a ``[low, high]`` window (seconds).

    The preset picks a starting fraction and a span fraction of the full window,
    so every preset stays inside ``[low, high]`` even if its scale is over 1.0.
    """
    low = max(0.0, low)
    high = max(low, high)
    start_f, span_f = _PRESET_SCALE.get(preset, (0.0, 1.0))
    span = high - low
    new_low = low + span * start_f
    new_high = new_low + span * span_f
    new_high = min(new_high, high)
    return new_low, max(new_low, new_high)


__all__ = [
    "PRESET_TITLES",
    "DelayDistribution",
    "DelayPreset",
    "UniformDelay",
    "distribution_for",
    "scaled_window",
]
