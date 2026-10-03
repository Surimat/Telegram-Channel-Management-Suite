# CURRENT STATE — Telegram Channel Management Suite

> Persistent project memory. **A new agent must be able to continue from this
> file + git + code alone.** Update this after every major phase.

**Last updated:** 2026-10-03
**Current phase:** PHASE 3 — Reaction Manager: **COMPLETED** and committed.
**Repository status:** first GitHub sync done — `develop` pushed; development continues on `develop`.
**Branch:** `develop` (tracks `origin/develop`); `main` is untouched and only ever updated via pull request.

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
  `schemas/` (common/events/settings/jobs/system/bots/reactions), `v1/` routers:
  `system`, `settings`, `events`, `queue`, `bots`, `reactions`, aggregated in
  `v1/router.py`.
- `backend/app/scheduler/` — `scheduler.py`: pure-asyncio durable scheduler;
  recovers RUNNING jobs on startup, claims due jobs, runs registered handlers,
  records failures to the Event Center.
- `backend/app/providers/` — **PHASE 2**: `base.py` (`TelegramBotProvider`
  Protocol), `types.py` (DTOs), `errors.py` (friendly provider errors),
  `fake_bot.py` (`FakeTelegramBotProvider`, deterministic, no I/O),
  `aiogram_bot.py` (`AiogramBotProvider`, the only aiogram importer; covers the
  official managed-bot methods), `registry.py` (`build_bot_provider`).

### PHASE 2 — Telegram foundation (bots)
- `backend/app/db/models/bot.py` — `Bot` model (`kind` = manager|managed|ordinary,
  `enabled`, `telegram_id`, `username`, `title`, `token_encrypted` (sealed),
  `provider_name`, `owner_id`/`owner_username`, `can_manage_bots`,
  `health` enum, `health_message`/`health_hint`/`last_error`, `last_health_at`).
- `backend/app/db/repositories/bots.py` — CRUD + `get_manager`, `count_by_kind`.
- `backend/app/services/bot_service.py` — `BotService`: add (validate+seal),
  enable/disable, remove, `health_check`, `ensure_manager_bot`,
  `register_managed_bot`, `fetch_managed_bot_token`,
  `replace_managed_bot_token`, `manager_link`, `summary`.
- `backend/app/api/deps.py` — `get_provider_factory` (overridable in tests),
  `get_bot_service`.
- `backend/app/api/schemas/bots.py`, `backend/app/api/v1/bots.py` — full bot
  inventory + managed-bot endpoints (tokens never returned; `has_token` only).
- `backend/app/core/security.py` — `seal_secret`/`open_secret` (Fernet, key from
  `APP_SECRET_KEY`).
- `backend/app/api/errors.py` — `ApiError` carrying a friendly message + hint.
- `SystemService` — DB-backed `manager_bot_db_check`, `managed_bots_check`; wired
  into `/api/v1/system/status`, `/api/v1/system/setup`, `/health/deep`.
- `main.py` lifespan — best-effort `ensure_manager_bot()` from settings.

### PHASE 3 — Reaction Manager (rules + planner + scheduling + UI)
- `backend/app/rules/engine.py` — `RulesEngine`, `Category` (9 categories),
  `RuleSpec`, `RuleMatch`. Deterministic keyword/phrase/regex matching with
  exclusions, `min_confidence`, priority, language gate, `manual_override`.
- `backend/app/rules/delays.py` — `DelayPreset` (`early`/`normal`/`spread`),
  `scaled_window`, `distribution_for`, `UniformDelay`.
- `backend/app/rules/defaults.py` — `default_rule_specs()` seed RU+EN rules.
- `backend/app/db/models/post.py` — `Post` (text, category, confidence,
  classification_source, status, channel/message ids).
- `backend/app/db/models/reaction.py` — `ReactionProfile`, `ReactionRule`,
  `ReactionJob` (+ `ReactionJobStatus`): `post_id, bot_id, reaction,
  scheduled_at, status, attempts, error, completed_at, queue_job_id`.
- `backend/app/db/repositories/posts.py`, `repositories/reactions.py`.
- `backend/app/services/reaction_planner.py` — pure `ReactionPlanner` + RNG.
- `backend/app/services/reaction_service.py` — the vertical-slice service
  (profiles/rules CRUD, classify, simulate, ingest/plan, execute, recover, stats).
- `backend/app/api/schemas/reactions.py`, `api/v1/reactions.py`,
  `api/deps.py::get_reaction_service`, router registration.
- `backend/app/providers/*` — `set_reaction` on the provider protocol, fake
  (deterministic recorder + injectable failures) and aiogram implementations.
- `backend/app/scheduler/scheduler.py` — handlers receive `(session, job)`
  (fixes a nested-session SQLite deadlock; important on weak machines).
- `backend/app/services/system_service.py` — `reactions` Setup-Wizard check.
- `frontend/src/views/ReactionsView.vue` + reaction types/methods in
  `api/client.ts`, `/reactions` route, nav link, Dashboard Reactions card.

### Frontend (PHASE 1) — Vue 3 + Vite + TypeScript
- `frontend/` — `package.json`, `vite.config.ts` (builds into
  `backend/app/static/`), `tsconfig.json`, `index.html`.
- `src/` — `main.ts`, `App.vue` (sidebar shell), `router.ts`,
  `api/client.ts` (typed client, uniform error handling), `stores/app.ts`
  (Pinia), `styles.css` (modern desktop look, responsive), views:
  `DashboardView`, `SystemView` (Setup Wizard table), `SettingsView`,
  `LogsView`, `QueueView`, `NotFoundView`.
- **PHASE 2**: `src/views/BotsView.vue` (inventory, health, enable/disable,
  add, managed-bot workflow), bot types + methods in `api/client.ts`, `/bots`
  route, nav link, and a Telegram summary card on the Dashboard.

### Ops / packaging (PHASE 1 foundation)
- `backend/requirements.txt`, `backend/requirements-dev.txt`.
- `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- `portable/run.bat`, `portable/stop.bat` (skeleton; full packaging PHASE 10).
- `docker/Dockerfile` (multi-stage: Node build → Python runtime, non-root),
  `docker/docker-compose.yml`, root `.dockerignore`.
- `pyproject.toml` (ruff config), `pytest.ini`.
- `tests/` — config, logging redaction, db/queue/events, API, scheduler.
- **PHASE 2 tests**: `tests/test_providers.py`, `tests/test_bot_service.py`,
  `tests/test_bots_api.py`; `tests/conftest.py` gained a `bot_client` fixture
  that overrides `get_provider_factory` with the fake provider.

## 3. What works (verified)

- App starts and serves `/health`, `/health/deep`, `/api/v1/*`, and the SPA.
- Setup Wizard checks return plain-language status for: runtime, database,
  filesystem, secret key, Telegram API, manager bot, managed bots, AI.
- Settings CRUD, events (log/error center) list + resolve, queue list +
  retry/cancel.
- Durable queue recovers jobs after restart; scheduler executes handlers.
- **Bots**: add (validated + sealed), list/summary, enable/disable, remove,
  health check, managed-bot preview/register/fetch-token — verified live in
  offline mode (server + curl) and covered by tests.
- **Reactions (PHASE 3)**: profiles/rules CRUD, deterministic classification,
  weighted/randomized planning, simulation (no Telegram), ingest+plan creating
  durable jobs, execution via the provider with FloodWait handling, and startup
  recovery — verified live in offline mode (add bot → enable → ingest → job
  created) and covered by 48 tests.
- `ruff check backend tests` → clean. `pytest` → **108 passed**.
- Frontend `npm run build` → outputs to `backend/app/static/` successfully
  (`vue-tsc` clean).

## 4. What does NOT exist yet

- MTProto/user accounts (PHASE 4), channel binding, audience, invites,
  analytics APIs/UI, Tiny AI classifier (PHASE 7).
- Manager-bot runtime: the manager bot is registered from settings, but there is
  no command loop / admin whitelist / notification forwarding yet; `managed_bot`
  update ingestion is manual by Telegram ID.
- Auth for the local UI / Mini App `initData`.
- Alembic migrations (currently `create_all` at startup).
- Backup/restore implementation, portable packaging, production HTTPS docs.

## 5. Next action

Start **PHASE 4 — User Session Manager** (see `agent/NEXT_TASK.md` and
`docs/ROADMAP.md`): `SessionProvider` + Telethon + fake, interactive auth wizard
(api id/hash → phone → code → 2FA), session import/list/revoke/health, secure
storage. **First commit PHASE 3** (see NEXT_TASK finish checklist).

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
- Bot tokens sealed at rest with Fernet; never returned by the API (D-017).
- Managed bots only via the official API + user confirmation (D-018).
- Provider selection via config; `offline_mode`/`fake` for tests (D-019).
- Rules Engine is deterministic; categories/rules are editable data (D-020).
- Reaction planner is pure with an injectable RNG; emoji are deterministic (D-021).
- Reaction profiles are named, one default; preview is forgiving (D-022).

## 7. How to run / verify after opening a new chat

```bash
git fetch origin && git checkout develop   # development branch (not main)
git status && git log --oneline -20
cat agent/CURRENT_STATE.md agent/NEXT_TASK.md agent/DECISIONS.md
cat docs/ROADMAP.md

python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest                       # must pass
python -m backend.app.main             # http://127.0.0.1:8000

cd frontend && npm install && npm run build && cd ..
```

## 8. GitHub sync & branching

- Remote: `https://github.com/Surimat/Telegram-Channel-Management-Suite`.
- First sync (2026-10-03): PHASE 0–3 (commits `0daa91b`…`f06ba53`) pushed to
  `develop`; PR **#1** `develop → main` opened but **not merged** (needs explicit
  owner confirmation).
- **Never push directly to `main`.** All work goes to `develop` (or feature
  branches off it) and lands in `main` only via a reviewed pull request.
- `main` still points at the initial README commit (`b2436d6`) until PR #1 merges.
- No history rewrite, no force push.
- Secret audit before push: `.env`, `data/*.db`, session files and portable
  runtimes are git-ignored and confirmed absent from the remote; the mutable
  runtime dirs (`sessions/`, `logs/`, `data/`, `backups/`, `exports/`) contain
  only `.gitkeep` on the remote.
