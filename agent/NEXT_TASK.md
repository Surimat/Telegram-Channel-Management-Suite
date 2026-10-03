# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 6 — Invite Manager (queue, dry-run, confirmation, error handling, pause/resume, UI)
**Previous phase:** PHASE 5 — Audience (completed; commit pending on `develop`).

---

## Repository sync status (2026-10-03)

PHASE 0–5 live on the `develop` branch. A PR (`develop → main`, #1) is open —
**not merged** pending owner confirmation. Continue on `develop` (feature
branches off it as needed). **Never push directly to `main`.**

---

## PHASE 5 — done (checklist)

- [x] `AudienceProvider` + `SessionAudienceProvider` + `FakeAudienceProvider`;
      registry wiring; friendly audience errors/DTOs.
- [x] `AudienceSource` / `AudienceUser` / `SourceUserLink` models (+ enums);
      repositories with filters/search/sort/pagination/bulk ops.
- [x] `AudienceService`: sources CRUD, check, dry-run preview, chunked durable
      scan (pause/resume/cancel, restart recovery), completeness, tags, scoring,
      dashboard/stats, streaming export, import.
- [x] API `/api/v1/audience/*` + schemas + deps + router registration.
- [x] Setup-Wizard `audience` check; startup recovery for interrupted scans.
- [x] Tests: **212 passed**; `ruff check backend tests` clean.
- [ ] **Commit PHASE 5** on `develop` (single stable commit; do not push to `main`).
- [ ] (Deferred) Dedicated Audience/Sources **frontend views** — tracked with the
      frontend rollout, not blocking PHASE 6.

---

## Goal of PHASE 6 — Invite Manager

Let the owner turn a filtered audience slice into a controlled invite run:
choose account(s), source(s) and target channel, apply filters, **dry-run** and
see a mandatory confirmation summary (source, target, user count, account count,
filters, planned operations), then start a durable invite queue with per-account
and per-user status, pause/resume/stop, logs, and safe retry. FloodWait, privacy
and admin restrictions are respected (pause + show wait), never bypassed.

## Constraints / reminders

- **D-001/D-026**: all Telegram access via providers. Invites use the PHASE 4
  `SessionProvider.invite_to_channel`; extend the fake for deterministic
  success/FloodWait/privacy outcomes — tests never need a real account.
- **D-006**: never bypass FloodWait / privacy / admin. Pause the affected
  account/queue and surface the wait time; store privacy errors as user status.
- **D-008**: invites run as durable queue jobs that recover after restart.
- **D-010/D-025/D-029**: never store/display session contents, api_hash, tokens or
  raw phones; keep secrets sealed and out of logs/UI/errors.
- **Mass-operation safeguards** (`docs/SECURITY.md` §7): a confirmation summary is
  mandatory before any bulk run; all limits are configurable.
- Keep the app runnable at the end (`pytest` passes, app starts, SPA builds).

## Deliverables

### DB
- [ ] `db/models/invite.py` — `InviteJob` (account selection, source/target,
      filters snapshot, status, counters, confirmation) and `InviteTask`
      (per-user status/attempts/last_error). Durable queue.
- [ ] `db/repositories/invites.py` — CRUD, claim/batch, counters, status queries.

### Service
- [ ] `services/invite_service.py` — preview/dry-run summary, create job (requires
      confirmation), start/pause/resume/stop, chunked execution through the
      provider, FloodWait → pause account + record wait, privacy/admin → user
      status, safe retry where technically appropriate, `recover()` on startup.

### API + Setup
- [ ] `api/schemas/invites.py` + `api/v1/invites.py`: list, preview, create,
      start/pause/resume/stop, per-user tasks. Friendly envelope, no secret leaks.
- [ ] Setup-Wizard `invites` check in plain language.

### Frontend
- [ ] `InvitesView.vue` (build a run: source→target→accounts→filters→preview→
      confirm; live queue with per-account/user status, pause/resume/stop).

### Tests
- [ ] invite model/repo, service (dry-run counts, confirmation required, FloodWait
      pause, privacy status, pause/resume), API, restart recovery.

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`, and the relevant `docs/*`; run `ruff` + `pytest`; build the
      SPA; `git diff` review; commit on `develop`.

## After PHASE 6

PHASE 7 — Tiny AI (rules fast path + optional tiny GGUF classifier, strict JSON,
confidence routing, enable/disable). See `docs/ROADMAP.md`.
