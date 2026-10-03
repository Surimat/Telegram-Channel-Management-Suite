# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 3 — Reaction Manager
**Previous phase:** PHASE 2 — completed (Telegram foundation / bots, committed)

---

## Goal of this phase

Let the owner configure **automatic reactions** on channel posts, executed by
several bot identities, each bot adding at most one reaction per message, with
deterministic-but-randomized scheduling over the durable queue.

The phase delivers a full vertical slice: **rules + reaction profiles -> planner
-> scheduler/queue -> provider (TelegramBotProvider.set_reaction) -> API -> Web
UI**, with simulation/preview and logs. All of it testable with the fake provider.

## Constraints / reminders

- **D-001**: reaction application goes through `TelegramBotProvider` (extend it
  with `set_reaction`); `FakeTelegramBotProvider` gets a deterministic recorder.
  No aiogram import outside the provider adapter.
- **D-006**: never bypass FloodWait; on `FloodWaitError`, pause the affected bot
  and surface the wait time.
- **D-008**: reaction jobs are durable DB rows (`reaction_jobs`) and are recovered
  after restart.
- **D-005**: emoji choice is **deterministic weighted logic**, never the LLM.
- **D-014**: UI is RU-first, plain language, with help/tooltips.
- Keep the app runnable at the end (`pytest` passes, app starts).

## Deliverables

### Domain / DB
- [ ] `db/models/reaction.py` — `ReactionProfile` (named config) and
      `ReactionJob` with fields: `post_id`, `bot_id`, `reaction`, `scheduled_at`,
      `status`, `attempts`, `error`, `completed_at`.
- [ ] Repositories + `ReactionService` (profiles CRUD, plan, enqueue, pause).

### Planner / scheduler
- [ ] Deterministic weighted emoji selection (weights, allowed/forbidden,
      skip probability, probability gate).
- [ ] Delay randomization (min/max, ranges) so reactions are not simultaneous.
- [ ] Simulation/preview: given a post + profile, return the planned jobs
      without contacting Telegram.
- [ ] Queue integration + retry/error handling on the durable scheduler.

### Provider / API / UI
- [ ] `TelegramBotProvider.set_reaction(...)` + fake + aiogram impl.
- [ ] `api/v1/reactions.py` — profiles CRUD, preview/simulate, queue list,
      start/pause/stop.
- [ ] Frontend `ReactionsView.vue` — profile editor (weights, delays, skip),
      simulation panel, queue status, plain-language help.

### Tests
- [ ] planner tests (weights/distribution, skip, delays, forbidden emoji).
- [ ] reaction service + scheduler tests.
- [ ] reactions API tests (using `bot_client` fake-provider fixture).

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`; run `ruff` + `pytest`; `git diff` review; commit.

## After PHASE 3

PHASE 4 — User Session Manager (Telethon, interactive auth, secure session
storage, health). See `docs/ROADMAP.md`.
