# CHANGELOG — Telegram Channel Management Suite

All notable changes, newest first. Format loosely follows Keep a Changelog.
Dates are ISO-8601.

---

## [Unreleased]

_No unreleased changes._

---

## [0.1.0] — 2026-10-03 — PHASE 1: application skeleton (runnable)

### Added — Backend
- `backend/app/main.py` FastAPI app factory + lifespan (starts/stops the
  scheduler, initialises the DB, mounts the built SPA); `/health`, `/health/deep`.
- `core/`: `paths.py` (predictable runtime dirs via `TCMS_ROOT`), `config.py`
  (pydantic-settings + `SecretStr`), `logging.py` (structured logging + secret
  redaction filter), `security.py` (secret-key validation, key derivation, HMAC).
- `db/`: declarative base + naming convention, async engine/session, models
  (`Setting`, `Event`, `Job`), repositories (`settings`, `events`, `jobs`).
- `services/`: `settings_service`, `events_service` (log/error center),
  `queue_service`, `system_service` (Setup Wizard checks with plain-language
  "what it means / how to fix").
- `api/`: uniform error envelope + handlers (no stack traces to clients),
  schemas, and v1 routers `system`, `settings`, `events`, `queue`.
- `scheduler/`: durable asyncio scheduler that recovers unfinished jobs on start,
  claims due jobs, runs registered handlers, and records failures as events.
- `providers/`: package + contracts placeholder (implementations in PHASE 2).

### Added — Frontend
- Vue 3 + Vite + TypeScript SPA: app shell with sidebar, router, typed API
  client, Pinia store, RU-first styles; views Dashboard, System (Setup Wizard
  table), Settings, Logs, Queue, NotFound.
- Build outputs to `backend/app/static/` (served by FastAPI; no Node in prod).

### Added — Ops / packaging
- `backend/requirements.txt`, `backend/requirements-dev.txt`.
- `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- `portable/run.bat`, `portable/stop.bat` (skeleton; full packaging PHASE 10).
- `docker/Dockerfile` (multi-stage Node→Python, non-root),
  `docker/docker-compose.yml`, root `.dockerignore`.
- `pyproject.toml` (ruff), `pytest.ini`.

### Added — Tests
- config, logging-redaction, database/queue/events, scheduler, and API tests
  with isolated temporary SQLite databases. **31 tests pass; ruff clean.**

### Changed
- Dropped APScheduler from runtime requirements in favour of the minimal asyncio
  scheduler (see D-015). Anchored the AI-models `.gitignore` rule to `/models/`
  so backend source packages are no longer accidentally ignored.

### Security
- Secret redaction filter masks registered secrets in all log output.
- Settings API returns masked values for secrets; errors never expose internals.

---

## [0.0.1] — 2026-10-03 — PHASE 0: audit, architecture, persistent memory

### Added
- Repository audit (repo was empty except a stub README).
- `docs/ARCHITECTURE.md` — architecture, stack, provider abstraction, data model,
  reliability principles, deployment targets, security model.
- `docs/ROADMAP.md` — PHASE 0–11 plan.
- `docs/SETUP.md` — local / Windows portable / VPS-Docker setup.
- `docs/SECURITY.md` — secret & limits policy, checklists.
- `docs/UI.md` — UI/UX principles, section map, Setup Wizard UX.
- `docs/API.md` — REST API contract.
- `docs/TROUBLESHOOTING.md` — plain-language fixes + recovery guide.
- `agent/CURRENT_STATE.md`, `agent/NEXT_TASK.md`, `agent/DECISIONS.md` (D-001…D-014),
  `agent/CHANGELOG.md`.
- `.gitignore` protecting secrets, session files, data, logs, backups, models.
- `.env.example` — annotated configuration template.
- Directory skeleton: `backend/`, `frontend/`, `tests/`, `scripts/`, `docker/`,
  `portable/`, `data/`, `sessions/`, `backups/`, `logs/`, `exports/`.

### Notes
- No application code yet; repository intentionally starts with architecture and
  memory first, per the project brief.
