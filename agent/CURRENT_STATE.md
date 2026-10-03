# CURRENT STATE — Telegram Channel Management Suite

> Persistent project memory. **A new agent must be able to continue from this
> file + git + code alone.** Update this after every major phase.

**Last updated:** 2026-10-03
**Current phase:** PHASE 1 — completed. Next: PHASE 2 (Telegram foundation).
**Repository status:** clean, committed.
**Branch:** `main`

---

## 1. Repository audit result

The repository started as an **empty project**: only a 1-line `README.md` and a
shallow clone of `main`. No code, no dependencies, no prior work existed.

Git: shallow clone → history may be incomplete. Run
`git rev-parse --is-shallow-repository` before history-dependent operations.

## 2. What exists now

### Documentation & memory (PHASE 0)
- `docs/` — `ARCHITECTURE.md`, `ROADMAP.md`, `SETUP.md`, `SECURITY.md`,
  `UI.md`, `API.md`, `TROUBLESHOOTING.md`.
- `agent/` — this file, `NEXT_TASK.md`, `DECISIONS.md` (D-001…D-016),
  `CHANGELOG.md`.
- `.gitignore` (secrets/sessions/data/logs/backups/models protected),
  `.env.example`, `README.md`.

### Backend application (PHASE 1) — runnable
Layered architecture: **core → db/models → db/repositories → services → api**.

- `backend/app/main.py` — FastAPI app factory + lifespan; mounts the built SPA;
  starts/stops the scheduler; `/health` and `/health/deep`.
- `backend/app/core/` — `paths.py` (predictable runtime dirs, `TCMS_ROOT`),
  `config.py` (pydantic-settings, `SecretStr`), `logging.py` (structured +
  **secret redaction filter**), `security.py` (secret-key validation, key
  derivation, HMAC signing).
- `backend/app/db/` — `base.py` (declarative base + naming convention),
  `session.py` (async engine, `init_models`, `session_scope`),
  `models/` (`setting`, `event`, `job`), `repositories/` (`settings`, `events`,
  `jobs`).
- `backend/app/services/` — `settings_service`, `events_service`,
  `queue_service`, `system_service` (Setup Wizard checks, plain-language).
- `backend/app/api/` — `errors.py` (uniform error envelope, no stack traces),
  `schemas/` (common/events/settings/jobs/system), `v1/` routers:
  `system`, `settings`, `events`, `queue`, aggregated in `v1/router.py`.
- `backend/app/scheduler/` — `scheduler.py`: pure-asyncio durable scheduler;
  recovers RUNNING jobs on startup, claims due jobs, runs registered handlers,
  records failures to the Event Center.
- `backend/app/providers/` — package + contracts placeholder (implementations in
  PHASE 2+).

### Frontend (PHASE 1) — Vue 3 + Vite + TypeScript
- `frontend/` — `package.json`, `vite.config.ts` (builds into
  `backend/app/static/`), `tsconfig.json`, `index.html`.
- `src/` — `main.ts`, `App.vue` (sidebar shell), `router.ts`,
  `api/client.ts` (typed client, uniform error handling), `stores/app.ts`
  (Pinia), `styles.css` (modern desktop look, responsive), views:
  `DashboardView`, `SystemView` (Setup Wizard table), `SettingsView`,
  `LogsView`, `QueueView`, `NotFoundView`.

### Ops / packaging (PHASE 1 foundation)
- `backend/requirements.txt`, `backend/requirements-dev.txt`.
- `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- `portable/run.bat`, `portable/stop.bat` (skeleton; full packaging PHASE 10).
- `docker/Dockerfile` (multi-stage: Node build → Python runtime, non-root),
  `docker/docker-compose.yml`, root `.dockerignore`.
- `pyproject.toml` (ruff config), `pytest.ini`.
- `tests/` — config, logging redaction, db/queue/events, API, scheduler.

## 3. What works (verified)

- App starts and serves `/health`, `/health/deep`, `/api/v1/*`, and the SPA.
- Setup Wizard checks return plain-language status for: runtime, database,
  filesystem, secret key, Telegram API, manager bot, AI.
- Settings CRUD, events (log/error center) list + resolve, queue list +
  retry/cancel.
- Durable queue recovers jobs after restart; scheduler executes handlers.
- `ruff check backend tests` → clean. `pytest` → **31 passed**.
- Frontend `npm run build` → outputs to `backend/app/static/` successfully.

## 4. What does NOT exist yet

- Any real Telegram integration (bot/MTProto providers are contracts only).
- Bots, sessions, audience, invites, reactions, rules, AI, analytics APIs/UI.
- Auth for the local UI / Mini App `initData`.
- Alembic migrations (currently `create_all` at startup).
- Backup/restore implementation, portable packaging, production HTTPS docs.

## 5. Next action

Start **PHASE 2 — Telegram foundation** (see `agent/NEXT_TASK.md` and
`docs/ROADMAP.md`): manager bot, Bot API adapter behind `TelegramBotProvider`,
channel connection, managed-bot support, bot inventory (model + repository +
service + API + UI), health checks, tests with a fake provider.

## 6. Locked decisions (do not break)

See `agent/DECISIONS.md`. Key ones:

- Provider/adapter abstraction for all Telegram access (D-001).
- SQLite now, PostgreSQL later, without business-logic rewrite (D-002).
- One SPA for Web UI and Mini App; one API (D-003).
- One backend for Windows/Linux/portable/Docker (D-004).
- AI optional and disableable (D-005).
- No bypassing Telegram FloodWait / privacy / admin restrictions (D-006).
- Durable DB-backed queue; recover unfinished jobs on startup (D-008).
- Secrets never committed or displayed; logging redaction mandatory (D-010).
- Frontend builds to static; no Node.js in production (D-012).

## 7. How to run / verify after opening a new chat

```bash
git status && git log --oneline -20
cat agent/CURRENT_STATE.md agent/NEXT_TASK.md agent/DECISIONS.md
cat docs/ROADMAP.md

python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest                       # must pass
python -m backend.app.main             # http://127.0.0.1:8000

cd frontend && npm install && npm run build && cd ..
```
