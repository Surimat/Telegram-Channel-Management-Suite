# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 4 — User Session Manager
**Previous phase:** PHASE 3 — Reaction Manager (code complete, tests green; commit
pending — see "Finish PHASE 3 first").

---

## Finish PHASE 3 first (one commit)

Everything below is done and verified; the only remaining step is the commit.

- [x] Rules Engine (`rules/engine.py`, `rules/delays.py`, `rules/defaults.py`).
- [x] Models/repos: `Post`, `ReactionProfile`, `ReactionRule`, `ReactionJob`.
- [x] Pure `ReactionPlanner` (weights, probability, skip, delays, cap) with RNG.
- [x] `ReactionService`: CRUD, classify, simulate, ingest/plan, execute, recover.
- [x] Provider `set_reaction` (fake + aiogram); durable-queue execution.
- [x] Scheduler handler signature `(session, job)`; startup seeding + recovery.
- [x] API (`/api/v1/reactions/*`) + `reactions` Setup-Wizard check.
- [x] Frontend `ReactionsView.vue` + route + nav + Dashboard card.
- [x] Tests: **108 passed**; `ruff check backend tests` clean; SPA builds.
- [ ] **Commit PHASE 3** (`git add -A && git commit`), then move to PHASE 4.

---

## Goal of PHASE 4

Let the owner add a **Telegram user account (MTProto)** through a guided wizard
in the Web UI, store its session securely, and monitor its health — all through
the `SessionProvider` abstraction so tests never need a real account.

## Constraints / reminders

- **D-001**: all MTProto access goes through `SessionProvider`; exactly one
  Telethon module imports Telethon (`providers/telethon_user.py`); a
  `FakeSessionProvider` backs tests and offline mode.
- **D-010 / D-017**: session files and api_hash live only outside git, in
  `sessions/` (git-ignored, excluded from the Docker image), never printed in UI,
  logs, errors or API responses. Store api_hash sealed like the bot token.
- **D-006**: never bypass FloodWait / privacy / admin restrictions.
- Keep the app runnable at the end (`pytest` passes, app starts).

## Deliverables

### Provider / DB
- [ ] `providers/base.py` — `SessionProvider` protocol (send_code, sign_in,
      sign_in_password, get_me, health, export_session, close).
- [ ] `providers/telethon_user.py` — Telethon impl (the only Telethon importer);
      friendly error translation. `providers/fake_session.py` for tests/offline.
- [ ] `db/models/session.py` — `UserSession` (phone, api_id, api_hash_encrypted,
      session_path, owner username/user_id, health, last_health_at, enabled).
- [ ] `db/repositories/sessions.py`, `services/session_service.py`.

### Auth wizard (stateful, resumable)
- [ ] API: `POST /api/v1/sessions/start` (api_id/hash + phone → code sent),
      `POST /api/v1/sessions/{id}/code`, `POST /api/v1/sessions/{id}/password`
      (2FA), `POST /api/v1/sessions/{id}/import` (existing `.session` file).
- [ ] Never return secrets or session contents; expose `has_session` + status.

### Management / health
- [ ] List with owner labels, enable/disable, delete + best-effort revoke,
      `POST /api/v1/sessions/{id}/health`, permissions probe (read/post rights).

### Frontend
- [ ] `SessionsView.vue` — guided wizard (api id/hash → phone → code → 2FA),
      import, list with owner/health, revoke/delete, plain-language help.

### Tests
- [ ] `FakeSessionProvider` tests + `session_service` + sessions API tests
      (start → code → password flows, import, health, secret-never-leaked).

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`; run `ruff` + `pytest`; `git diff` review; commit.

## After PHASE 4

PHASE 5 — Audience (sources, parsing, database, filters, tags, search, export).
See `docs/ROADMAP.md`.
