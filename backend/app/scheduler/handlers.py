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
from backend.app.services.bot_factory import (
    BOT_FACTORY_JOB_KIND,
    BotFactoryService,
)
from backend.app.services.invite_service import INVITE_JOB_KIND, InviteService
from backend.app.services.posting_service import POSTING_JOB_KIND, PostingService
from backend.app.services.queue_service import QueueService
from backend.app.services.reaction_service import REACTION_JOB_KIND, ReactionService

#: How far ahead the Content Studio posting tick re-schedules itself. Small
#: enough that a scheduled publication fires close to its time, large enough
#: that an idle install does not spin.
POSTING_TICK_SECONDS = 15

#: Pause between two bot-creation operations in the queue. Kept deliberately
#: modest so the durable queue paces itself instead of hammering Telegram.
BOT_FACTORY_TICK_SECONDS = 2

#: Durable-queue kind for the LAN Mesh maintenance tick.
MESH_TICK_JOB_KIND = "mesh.tick"


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


async def _handle_posting(session: AsyncSession, job: Job) -> None:
    # One bounded pass over due publications, auto-deletions and comments. The
    # pass always re-schedules itself a short interval ahead, so the loop is a
    # durable periodic tick that survives restarts (D-008 style) without a
    # second scheduler primitive — and a publication scheduled later still fires
    # without needing a restart.
    await PostingService(session).tick()
    await QueueService(session).enqueue(
        kind=POSTING_JOB_KIND,
        payload={},
        scheduled_at=utcnow() + timedelta(seconds=POSTING_TICK_SECONDS),
        max_attempts=1,
    )


async def _handle_mesh_tick(session: AsyncSession, job: Job) -> None:
    # Maintenance pass: probe trusted peers, recompute the coordinator and release
    # expired leases. Only runs when the mesh is enabled; otherwise it is a no-op
    # that still re-schedules so enabling the mesh later needs no restart.
    from backend.app.core.config import get_settings

    settings = get_settings()
    if settings.mesh_enabled and settings.mesh_mode != "standalone":
        from backend.app.mesh.service import MeshService

        service = MeshService(session, settings=settings)
        await service.ensure_node()
        for peer in await service.peers.list_all(trusted=True):
            await service.probe_peer(peer.id)
        await service.elect()
        await service.reclaim_expired()
    await QueueService(session).enqueue(
        kind=MESH_TICK_JOB_KIND,
        payload={},
        scheduled_at=utcnow() + timedelta(seconds=max(5, settings.mesh_tick_interval)),
        max_attempts=1,
    )


async def _handle_bot_factory(session: AsyncSession, job: Job) -> None:
    # One creation operation per tick so a large queue never blocks the scheduler
    # and a restart resumes where it stopped (D-008 style). While queued work
    # remains, a follow-up job is scheduled ahead of time.
    payload = json.loads(job.payload or "{}")
    batch_id = payload.get("batch_id")
    if not batch_id:
        return
    service = BotFactoryService(session)
    via_deeplink = bool(payload.get("via_deeplink", False))
    await service.run_queue_once(batch_id, via_deeplink=via_deeplink)
    progress = await service.queue_progress(batch_id)
    # Deep-link batches are completed by the owner in Telegram, so there is
    # nothing for the queue to keep ticking on.
    if progress["queued"] > 0 and not via_deeplink:
        await QueueService(session).enqueue(
            kind=BOT_FACTORY_JOB_KIND,
            payload={"batch_id": batch_id, "via_deeplink": via_deeplink},
            scheduled_at=utcnow() + timedelta(seconds=BOT_FACTORY_TICK_SECONDS),
            group_key=batch_id,
            max_attempts=1,
        )


def register_handlers(scheduler: Scheduler) -> None:
    """Register every durable-queue handler on ``scheduler``."""
    scheduler.register(REACTION_JOB_KIND, _handle_reaction)
    scheduler.register(SCAN_JOB_KIND, _handle_scan)
    scheduler.register(INVITE_JOB_KIND, _handle_invite)
    scheduler.register(POSTING_JOB_KIND, _handle_posting)
    scheduler.register(BOT_FACTORY_JOB_KIND, _handle_bot_factory)
    scheduler.register(MESH_TICK_JOB_KIND, _handle_mesh_tick)


__all__ = ["MESH_TICK_JOB_KIND", "register_handlers"]
