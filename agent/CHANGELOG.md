# CHANGELOG — Telegram Channel Management Suite

All notable changes, newest first. Format loosely follows Keep a Changelog.
Dates are ISO-8601.

---

## [Unreleased]

_No unreleased changes._

---

## [0.2.0] — 2026-10-03 — PHASE 2: Telegram foundation (manager/managed bots)

### Added — Telegram provider layer (D-001, D-019)
- `providers/base.py` — `TelegramBotProvider` Protocol: `get_me`, `get_bot`,
  `send_message`, `get_managed_bots`, `get_managed_bot_token`,
  `replace_managed_bot_token`, `get/set_managed_bot_access_settings`, `close`.
- `providers/fake_bot.py` — `FakeTelegramBotProvider` (deterministic, no network).
- `providers/aiogram_bot.py` — `AiogramBotProvider` (the only aiogram importer;
  wraps the official managed-bot methods; translates exceptions).
- `providers/errors.py` / `types.py` — friendly, library-agnostic error types and
  DTOs; `providers/registry.py` — `build_bot_provider` from config.

### Added — Bots vertical slice (DB → service → API → UI)
- `db/models/bot.py` (`Bot`, `BotKind`, `BotHealth`), `db/repositories/bots.py`.
- `services/bot_service.py` — add/validate/seal, enable/disable/remove,
  `health_check`, `ensure_manager_bot`, managed-bot register/token/replace,
  `manager_link`, `summary`.
- `api/deps.py`, `api/schemas/bots.py`, `api/v1/bots.py` — bot inventory +
  managed-bot endpoints; tokens are never returned (only `has_token`).
- `ApiError` (message + actionable hint) in `api/errors.py`.
- Setup Wizard: DB-backed `manager_bot` + `managed_bots` checks in
  `/api/v1/system/{status,setup}` and `/health/deep`.
- `main.py` lifespan registers the manager bot from settings (best-effort).

### Added — Security
- Bot tokens **sealed at rest** with Fernet keyed from `APP_SECRET_KEY`
  (`core/security.py::seal_secret/open_secret`) — D-017.

### Added — Frontend
- `views/BotsView.vue` (inventory, health, enable/disable, add, managed-bot
  workflow), bot types/methods in `api/client.ts`, `/bots` route + nav link, and
  a Telegram summary card on the Dashboard.

### Added — Tests
- `tests/test_providers.py`, `tests/test_bot_service.py`, `tests/test_bots_api.py`
  and a `bot_client` fixture overriding the provider factory with the fake.
- Suite: **60 passed**; `ruff check backend tests` clean.

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
