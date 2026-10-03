# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 5 — Audience (sources, parsing, database, filters, tags, exports)
**Previous phase:** PHASE 4 — User Session Manager (completed; commit pending on `develop`).

---

## Repository sync status (2026-10-03)

PHASE 0–4 live on the `develop` branch. A PR (`develop → main`, #1) is open —
**not merged** pending owner confirmation. Continue on `develop` (feature
branches off it as needed). **Never push directly to `main`.**

---

## Finish PHASE 4 first (checklist)

- [x] `SessionProvider` protocol + DTOs/errors (user accounts).
- [x] `TelethonSessionProvider` (only Telethon importer) + `FakeSessionProvider`.
- [x] `UserSession` model + `SessionStatus` + repository (secrets sealed).
- [x] `SessionService`: auth wizard (start → code → 2FA), import (+rollback),
      health, enable/disable, delete, logout, `recover()`.
- [x] API `/api/v1/sessions/*` + schemas + deps + router registration.
- [x] Setup-Wizard checks: `telethon`, `sessions_dir`, `accounts`; startup recovery.
- [x] Frontend `SessionsView.vue` + route + nav + Dashboard card; SPA builds.
- [x] Tests: **153 passed**; `ruff check backend tests` clean; live smoke test.
- [ ] **Commit PHASE 4** on `develop` (single stable commit; do not push to `main`).

---

## Goal of PHASE 5

Let the owner register **audience sources** (public channels/groups, entities by
username/ID), **parse** their participants through a user account, store them in
the **audience database** with de-duplication, and explore them via filters, tags,
search, sorting, export/import and per-source statistics — all through provider
abstractions so tests never need a real account.

## Constraints / reminders

- **D-001**: all Telegram access goes through providers. Audience parsing uses the
  `SessionProvider` already added in PHASE 4 (`resolve_entity`, `get_participants`);
  `FakeSessionProvider` must be extended to serve deterministic participant lists
  for tests/offline mode.
- **D-006**: never bypass Telegram FloodWait / privacy / admin restrictions. On
  FloodWait, stop the affected queue/account and surface the wait time; store
  privacy errors as a user status, never work around them.
- **D-010 / D-017 / D-025**: never store or display session contents, api_hash or
  full phone numbers; keep secrets sealed and out of logs/UI/errors.
- Keep the app runnable at the end (`pytest` passes, app starts, SPA builds).

## Deliverables

### Providers
- [ ] Extend `SessionProvider` / `FakeSessionProvider` with deterministic
      participant iteration + entity resolution used by parsing (limit/paging,
      injectable FloodWait/privacy failures).
- [ ] Map Telegram errors to friendly provider errors (`FloodWaitError`,
      `PrivacyRestrictedError`, `EntityNotFoundError`, ...).

### DB
- [ ] `db/models/audience.py` — `AudienceSource` (title, username, type, status,
      last_scan, participants_found, errors) and `AudienceMember`
      (telegram_user_id, username, first/last name, source, date_found, is_bot,
      is_deleted, is_mutual, tags, score, invite_status, last_error) with a unique
      constraint for de-duplication.
- [ ] `db/repositories/audience.py` — CRUD, upsert/dedup, filtered+searched+
      sorted+paginated queries, tag operations, per-source statistics.

### Service
- [ ] `services/audience_service.py` — add/remove sources; parse a source through
      the account provider with error handling; dedup on upsert; filters, tags,
      search, export (CSV/JSON) and import; source statistics. Long scans run as
      durable queue jobs (recover on restart, D-008).

### API
- [ ] `api/schemas/audience.py` + `api/v1/audience.py`: sources (`GET/POST/DELETE`),
      parse (`POST /sources/{id}/scan`), members (`GET` with filters/sort/page),
      tags, `GET /members/export`, `POST /members/import`, `GET /sources/stats`.
      Uniform friendly error envelope; never leak account/session details.

### Setup Wizard
- [ ] Add an `audience` check (sources present / members found) in plain language.

### Frontend
- [ ] `SourcesView.vue` (add/manage sources, scan, per-source stats) and
      `AudienceView.vue` (member table: filters, search, sort, pagination, tags,
      export/import, empty/loading states). Routes + nav + Dashboard card.

### Tests
- [ ] audience model/repo, fake-provider parsing, service (dedup, filters, tags,
      export/import, FloodWait/privacy handling), API, restart recovery.

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`, and the relevant `docs/*`; run `ruff` + `pytest`; build the
      SPA; `git diff` review; commit on `develop`.

## After PHASE 5

PHASE 6 — Invite Manager (queue, dry-run, manual approval, account assignment,
error handling, pause/resume, UI). See `docs/ROADMAP.md`.
