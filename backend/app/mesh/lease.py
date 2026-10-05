"""Job leases with fencing tokens (pure).

A job is leased to exactly one worker for a bounded time. If the worker dies or
the coordinator changes, the lease expires and a new worker takes it over with a
**higher fencing token**. The old worker's late commit is rejected because its
token is stale — so a zombie worker can never overwrite a newer result (the
classic fencing pattern, without any distributed lock service).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True)
class LeaseGrant:
    job_id: str
    owner: str
    fencing_token: int
    lease_until: datetime


def can_commit(
    *,
    lease_owner: str,
    lease_token: int,
    current_owner: str,
    current_token: int,
    expired: bool,
) -> bool:
    """Whether a worker holding ``lease_token`` may commit its result."""
    if expired:
        return False
    return lease_owner == current_owner and lease_token == current_token


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to aware UTC.

    SQLite drops tzinfo, so stored values come back naive while ``now`` is aware.
    Comparing the two directly raises, so coerce both to the same awareness.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def should_reclaim(*, lease_until: datetime | None, now: datetime, status: str) -> bool:
    """Whether an active lease has expired and may be handed to another worker."""
    if status != "active":
        return False
    if lease_until is None:
        return True
    return _as_utc(lease_until) <= _as_utc(now)


def next_fencing_token(current: int) -> int:
    return int(current) + 1


__all__ = ["LeaseGrant", "can_commit", "next_fencing_token", "should_reclaim"]
