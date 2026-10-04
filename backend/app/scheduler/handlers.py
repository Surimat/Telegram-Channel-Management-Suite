"""Durable-queue job handler registration.

Kept separate from ``main.py`` so the same wiring can be reused when the
scheduler is restarted from the UI (Diagnostics → safe maintenance actions).
"""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.job import Job
from backend.app.scheduler.scheduler import Scheduler
from backend.app.services.audience_service import SCAN_JOB_KIND, AudienceService
from backend.app.services.invite_service import INVITE_JOB_KIND, InviteService
from backend.app.services.queue_service import QueueService
from backend.app.services.reaction_service import REACTION_JOB_KIND, ReactionService


async def _handle_reaction(session: AsyncSession, job: Job) -> None:
    payload = json.loads(job.payload or "{}")
    reaction_job_id = payload.get("reaction_job_id")
    if reaction_job_id:
        await ReactionService(session).execute_reaction_job(reaction_job_id)


async def _handle_scan(session: AsyncSession, job: Job) -> None:
    # The service streams one bounded chunk per tick, committing progress so an
    # interrupted scan can resume (decision D-028).
    await AudienceService(session).run_scan_chunk()


async def _handle_invite(session: AsyncSession, job: Job) -> None:
    # One bounded batch per tick. While work remains, re-schedule a follow-up
    # job at the next due time so per-account delays are honoured and the run
    # stays restart-safe (decision D-008).
    payload = json.loads(job.payload or "{}")
    invite_job_id = payload.get("invite_job_id")
    if not invite_job_id:
        return
    action, delay = await InviteService(session).run_tick(invite_job_id)
    if action == "more":
        await QueueService(session).enqueue(
            kind=INVITE_JOB_KIND,
            payload={"invite_job_id": invite_job_id},
            scheduled_at=utcnow() + timedelta(seconds=delay),
            group_key=invite_job_id,
            max_attempts=1,
        )


def register_handlers(scheduler: Scheduler) -> None:
    """Register every durable-queue handler on ``scheduler``."""
    scheduler.register(REACTION_JOB_KIND, _handle_reaction)
    scheduler.register(SCAN_JOB_KIND, _handle_scan)
    scheduler.register(INVITE_JOB_KIND, _handle_invite)


__all__ = ["register_handlers"]
