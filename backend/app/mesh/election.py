"""Deterministic coordinator election (pure).

Every trusted, online node runs the same rule, so they converge on one
coordinator without a central server:

1. only nodes that advertise the ``telegram`` capability are eligible (a node
   that cannot talk to Telegram must not own Telegram pollers);
2. among the eligible, the highest ``priority`` wins;
3. ties are broken by the lowest ``node_id`` (stable, no flapping).

The election is *soft state*: any node can recompute it at any time, so losing
the coordinator never loses data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ElectionCandidate:
    node_id: str
    priority: int = 0
    capabilities: list[str] | None = None
    online: bool = True

    def eligible(self, required_capability: str = "telegram") -> bool:
        if not self.online:
            return False
        return required_capability in set(self.capabilities or [])


def elect_coordinator(
    candidates: list[ElectionCandidate], *, required_capability: str = "telegram"
) -> str | None:
    """Return the elected coordinator's node id, or None when nobody qualifies."""
    eligible = [c for c in candidates if c.eligible(required_capability)]
    if not eligible:
        return None
    eligible.sort(key=lambda c: (-int(c.priority), c.node_id))
    return eligible[0].node_id


def is_coordinator(
    candidates: list[ElectionCandidate], node_id: str, *, required_capability: str = "telegram"
) -> bool:
    return elect_coordinator(candidates, required_capability=required_capability) == node_id


__all__ = ["ElectionCandidate", "elect_coordinator", "is_coordinator"]
