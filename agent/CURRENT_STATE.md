# CURRENT STATE — Telegram Channel Management Suite

> Persistent project memory. **A new agent must be able to continue from this
> file + git + code alone.** Update this after every major phase.

**Last updated:** 2026-10-03
**Current phase:** PHASE 7 — Tiny AI classifier: **COMPLETED** (commit pending).
**Repository status:** `develop` carries PHASE 0–7; `main` only via pull request.
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

### PHASE 4 — User Session Manager (MTProto accounts)
- `backend/app/providers/session_base.py` — `SessionProvider` protocol
  (send_code, sign_in, sign_in_password, get_me, health, export_session,
  resolve_entity, get_participants, invite_to_channel, aclose).
- `backend/app/providers/telethon_session.py` — `TelethonSessionProvider`: the
  **only** Telethon importer; lazy per-operation connect/disconnect; Telethon
  errors translated to friendly provider errors.
- `backend/app/providers/fake_session.py` — `FakeSessionProvider` +
  `FakeAuthScenario` (deterministic, no I/O) for tests/offline mode.
- `backend/app/providers/registry.py` — `build_session_provider(...)`;
  `providers/errors.py` + `providers/types.py` extended with user-account
  errors/DTOs (`ApiCredentialsInvalidError`, `AuthCode*`, `Password*`,
  `PhoneNumber*`, `SessionInvalidError`; `UserIdentity`, `SendCodeResult`,
  `SignInResult`, `SessionFileInfo`, `EntityRef`).
- `backend/app/db/models/session.py` — `UserSession` + `SessionStatus`
  (online/auth_required/disconnected/flood_wait/error/disabled). Full phone and
  api_hash stored **sealed**; only `phone_masked` + `api_id` in plaintext;
  `session_ref` is a UUID basename.
- `backend/app/db/repositories/sessions.py` — `SessionRepository`.
- `backend/app/services/session_service.py` — `SessionService`: durable guided
  auth wizard (api_id/hash + phone → code → optional 2FA), `.session` import
  (with rollback on failure), health checks, enable/disable, delete (+ file
  removal), logout/re-auth, `recover()` for interrupted flows.
- `backend/app/api/schemas/sessions.py`, `backend/app/api/v1/sessions.py`,
  `api/deps.py::get_session_service` / `get_session_provider_factory`, router
  registration. Responses never expose secrets (only `phone_masked`, `has_*`).
- `backend/app/services/system_service.py` — new Setup-Wizard checks `telethon`,
  `sessions_dir`, `accounts` (plain-language).
- `backend/app/main.py` lifespan — best-effort `SessionService.recover()`.
- `frontend/src/views/SessionsView.vue` + session types/methods in
  `api/client.ts`, `/sessions` route, sidebar «Аккаунты», Dashboard card.
- `tests/` — `test_fake_session_provider.py`, `test_session_service.py`,
  `test_sessions_api.py`, `test_session_security.py`; `conftest.py` gained a
  `session_client` fixture (fake session provider).

### PHASE 5 — Audience (sources + parsing + database + export)
- `backend/app/providers/audience_base.py` — `AudienceProvider` protocol
  (`resolve_entity`, `iter_participant_pages`).
- `backend/app/providers/session_audience.py` — `SessionAudienceProvider`: thin
  adapter over the PHASE 4 `SessionProvider` (no Telethon import here).
- `backend/app/providers/fake_audience.py` — `FakeAudienceProvider` +
  `FakeAudienceScenario` (pure, offline); `fake_session.py` gained
  `FakeAudienceScenario` + `make_fake_users` and participant-page support.
- `backend/app/providers/registry.py` — `build_audience_provider(...)`; `errors.py`
  + `types.py` gained audience errors/DTOs (`EntityNotFoundError`,
  `PrivacyRestrictedError`, `ChatAdminRequiredError`; `EntityRef` extended with
  `participants_count`/`participants_hidden`, `ParticipantPage`).
- `backend/app/db/models/audience.py` — `AudienceSource`, `AudienceUser`,
  `SourceUserLink` (+ enums `SourceType`, `ScanStatus`, `Completeness`,
  `MemberStatus`); dedup via unique `telegram_user_id` and unique
  `(source_id, user_id)` links.
- `backend/app/db/repositories/audience.py` — `AudienceSourceRepository`,
  `AudienceUserRepository`, `SourceUserLinkRepository` (filters, pagination,
  sorting, counts, batch streaming, bulk ops; enum-key normalization).
- `backend/app/services/audience_service.py` — `AudienceService`: sources CRUD,
  `check_source`, `preview_scan` (dry-run), durable scanning with per-chunk
  commits, completeness logic, pause/resume/cancel, `recover()`, tags, explainable
  scoring, dashboard/statistics, streaming CSV/JSON export, CSV/JSON import.
- `backend/app/api/schemas/audience.py`, `backend/app/api/v1/audience.py`,
  `api/deps.py::get_audience_service`, router registration. Responses never
  expose secrets or raw phones; PII export gated by settings.
- `backend/app/services/system_service.py` — new Setup-Wizard `audience` check.
- `backend/app/main.py` lifespan — `AudienceService.recover()` (pauses
  interrupted scans) + registered the `audience.scan` durable job handler.
- `backend/app/db/session.py` — SQLite `lower`/`upper` registered as Python
  functions so case-insensitive Cyrillic search works (SQLite's built-in `lower`
  is ASCII-only).
- `tests/` — `test_audience_models.py`, `test_audience_service.py`,
  `test_audience_api.py`, `test_audience_providers.py`,
  `test_audience_security.py`; `conftest.py` gained an `audience_client` fixture.

### PHASE 6 — Invite Manager (queue + confirmation + safe execution)
- `backend/app/db/models/invite.py` — `InviteJob` (`target`, `account_ids`/
  `source_ids`/`filters` snapshots, `status`, counters, `confirmed_at`/
  `confirmed_summary`, `waiting_account_id`/`wait_until`, `queue_job_id`) and
  `InviteTask` (`job_id`, `user_id`, `telegram_user_id`, `account_id`, `status`,
  `attempts`, `scheduled_at`, `completed_at`, `wait_until`, `error`); enums
  `InviteJobStatus`, `InviteStatus`, `TERMINAL_INVITE_STATUSES`.
- `backend/app/db/repositories/invites.py` — `InviteJobRepository` and
  `InviteTaskRepository` (list/filter, status counts, `claim_batch`, `pending_count`,
  `unfinished_count`, `next_due`, `retry_failed`).
- `backend/app/services/invite_service.py` — `InviteService`: `preview` (dry-run
  summary: source/target/users/accounts/filters/planned ops), `create_job` (draft +
  task planning with randomized per-account spacing), `confirm_and_start`,
  `start`/`pause`/`resume`/`stop`, `retry_failed`, `run_tick` (one bounded batch per
  tick → `done`/`more`/`paused`), `recover`, `summary`, `explain_job`. FloodWait
  pauses + records the wait; privacy/admin become non-retryable user statuses.
- `backend/app/api/schemas/invites.py`, `backend/app/api/v1/invites.py`,
  `api/deps.py::get_invite_service`, router registration. No secret leaks.
- `providers/errors.py` + `fake_session.py` (`FakeInviteScenario`) +
  `telethon_session.py` — invite error coverage.
- `main.py` lifespan — `InviteService.recover()` + `invite.batch` durable handler
  (re-schedules itself while work remains).
- `services/system_service.py` — Setup-Wizard `invites` check.
- `frontend/src/views/InvitesView.vue` + invite types/methods in `api/client.ts`,
  `/invites` route, sidebar «Приглашения».
- `tests/` — `test_invite_service.py`, `test_invite_api.py`; `conftest.py` gained an
  `invite_client` fixture.

### PHASE 7 — Tiny AI classifier (rules-first, optional)
- `backend/app/ai/` — the whole AI layer, free of Telegram/FastAPI imports:
  - `types.py` — `Classifier` Protocol, `ClassificationResult`
    (`category`/`tone`/`confidence`/`source`), `ClassificationContext`, `Tone`,
    and the source/mode vocabularies (`rules`/`llm`/`manual`/`fallback`/`default`;
    `auto`/`rules`/`ai`).
  - `errors.py` — friendly, non-leaking errors (`AiDisabledError`,
    `ModelNotConfigured/NotFoundError`, `RuntimeUnavailableError`,
    `InferenceTimeoutError`, `InvalidModelOutputError`, `ModelLoadError`).
  - `schema.py` — `parse_classification`: tolerant about framing, strict about
    values (unknown category/tone, non-numeric/bool/out-of-range confidence →
    `InvalidModelOutputError`).
  - `classifiers.py` — `RulesClassifier` (wraps the Rules Engine),
    `LlmClassifier` (prompt + `run_bounded` + strict parse), `FakeClassifier`.
  - `router.py` — `RoutingClassifier` (rules fast path → AI only when unsure →
    graceful fallback), explainable `RoutingOutcome`, `category_title`.
  - `inference.py` — `run_bounded`: one shared single-worker executor; timeout
    raises `InferenceTimeoutError`; `shutdown_executor()` on app exit.
  - `backends/` — `base.LlmBackend`, `FakeLlmBackend` (data-block-only keyword
    heuristic; scriptable failures), `LlamaCppBackend` (the only `llama_cpp`
    importer; lazy load, lock-serialized, optional), registry `build_backend`.
- `backend/app/db/models/ai.py` (`AiMetric` single-row counters, `AiRecord` recent
  diagnostics) + `repositories/ai.py` (`AiRepository`).
- `backend/app/services/ai_service.py` — `AiService`: effective (DB-overridable)
  config, `status`, `list_models`/`check_model`/`load_model`/`unload_model`,
  `router(mode)`, `classify`, metrics/history, event recording, `_backend()`
  cache. `ai_help.py` — per-setting plain-language help + `human_size`.
- `backend/app/api/schemas/ai.py` + `api/v1/ai.py` — 11 routes: `/ai/status`,
  `/ai/overview`, `/ai/settings` (GET/PUT), `/ai/classify`, `/ai/test`,
  `/ai/models`, `/ai/model/check|load|unload`, `/ai/metrics`, `/ai/history`;
  registered in `v1/router.py`.
- `Settings` — AI block + `resolve_models_dir()`; `paths.models_dir()`
  (`MODELS_DIRNAME`). Model files live in gitignored `/models/`, never
  auto-downloaded.
- `ReactionService` — `_classify` routes through `RoutingClassifier`
  (`_route`/`_result_to_match`/`_public_source`); `simulate` and `ingest_post`
  accept `mode`/`force_category`; simulation response carries the AI fields.
- `services/system_service.py` — `ai_check_async` (live service) wired into the
  Setup Wizard's `ai` check (off = OK, missing runtime/model = warning, never an
  error).
- `frontend/src/views/AiView.vue` — tabs Обзор / Модель / Настройки / Проверка /
  Диагностика; AI types + methods in `api/client.ts`; `/ai` route; sidebar «Мини-ИИ».
- `tests/` — `test_ai_classifier.py` (schema/classifiers/routing/inference) and
  `test_ai_api.py` (service + API + reaction simulation AI fields + setup check).

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
- `ruff check backend tests` → clean. `pytest` → **281 passed**.
- Frontend `npm run build` → outputs to `backend/app/static/` successfully
  (`vue-tsc` clean).
- **Sessions (PHASE 4)**: guided auth wizard (start → code → 2FA), `.session`
  import (+ rollback), health, enable/disable, delete, logout, startup recovery —
  verified live in offline mode (start → code → list; no secret in responses) and
  covered by 45 tests.
- **Audience (PHASE 5)**: sources CRUD, `check`, dry-run preview, chunked durable
  scan (pause/resume/cancel, restart recovery), dedup, filters/search/sort/tags,
  bulk status, dashboard/statistics, streaming export, import — verified in
  offline mode and covered by API/service/model/provider/security tests. No
  secret or raw phone appears in responses, exports default to no PII.
- **Invites (PHASE 6)**: dry-run preview, draft→confirm→start, bounded durable
  execution (one batch per tick, re-scheduled), per-account/per-user statuses,
  pause/resume/stop, safe retry, FloodWait pause + recorded wait, privacy/admin
  statuses, and restart recovery (`recover()` pauses running jobs) — covered by
  `test_invite_service.py` + `test_invite_api.py`; responses never leak secrets.
- **Tiny AI (PHASE 7)**: rules-first routing (AI only when rules are unsure),
  strict-JSON classification, optional GGUF backend that degrades gracefully when
  llama.cpp/the model is absent, model check/load/unload, DB-overridable UI
  settings, metrics/history, and an `ai` Setup-Wizard check — verified live in
  offline mode (status → enable fake → classify via rules and via AI) and covered
  by 43 AI tests. The SPA builds with the new «Мини-ИИ» page.

## 4. What does NOT exist yet

- Dedicated Audience/Sources **frontend views** (API is complete; views land with
  the frontend rollout) and the Telegram Mini App.
- Channel binding and Analytics APIs/UI (PHASE 8).
- Account permission probe (read/post rights on a channel) — the SessionProvider
  exposes `resolve_entity`/`get_participants`/`invite_to_channel`, and invites now
  use `invite_to_channel`, but there is no standalone "check permissions" flow.
- Manager-bot runtime: the manager bot is registered from settings, but there is
  no command loop / admin whitelist / notification forwarding yet.
- Auth for the local UI / Mini App `initData`.
- Alembic migrations (currently `create_all` at startup).
- Backup/restore implementation, portable packaging, production HTTPS docs.

## 5. Next action

Start **PHASE 8 — Analytics** (see `agent/NEXT_TASK.md` and `docs/ROADMAP.md`):
content analytics (posts, reactions, categories, activity over time), audience
analytics (sources, growth, engagement indicators available via the Telegram API),
charts in the Web UI, and a plain-language Dashboard that explains the numbers.
Reuse the existing data (posts, reaction jobs, audience sources/users) — no new
infrastructure.

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
- User accounts use lazy, per-operation MTProto connections (D-023).
- The auth wizard is a durable, resumable state machine (D-024).
- Account secrets are sealed; the API exposes only presence (D-025).
- Audience parsing goes through `AudienceProvider`, a thin adapter over the
  PHASE 4 `SessionProvider`; scans are chunked and restart-safe (D-026).
- Audience scans have a dry-run preview; completeness is reported honestly
  (`complete`/`partial`/`no_access`) and FloodWait pauses rather than loops (D-027).
- Audience dedup key is the unique `telegram_user_id`; membership is a
  many-to-many `source_user_links` table (D-028).
- Audience PII is masked at rest, exports are local-only and PII-off by default
  (D-029).
- Invites require server-side confirmation and run as bounded durable batches;
  limits are never bypassed (D-030).
- The Tiny AI is an optional adapter behind a `Classifier` Protocol; the Rules
  Engine stays the deterministic default (D-031/D-032).
- AI output is strictly validated JSON; the LLM never picks emoji (D-033).
- AI config is UI-editable and DB-overridable with plain-language help; models are
  user-provided `.gguf` assets, never committed/downloaded (D-034).
- AI inference is single-concurrency and bounded, and always degrades gracefully
  (D-035).

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
- **Second sync (2026-10-03):** PHASE 4–6 pushed to `develop` as a fast-forward
  (`92d94e4`…`3ddc299`; no force). PHASE 6's functional commit is `3ddc299`;
  `origin/develop` contains PHASE 4 (`92d94e4`), PHASE 5 (`8197f33`) and PHASE 6
  (`3ddc299`). One or more sync-record doc commits sit above `3ddc299` (e.g.
  `5cb6386`); `develop` is **0 ahead / 0 behind** `origin/develop`.
- PR **#1** (`develop → main`) tracks `develop`'s head automatically (currently a
  sync-record doc commit above `3ddc299`); still **open**, `merged: false` —
  **not merged** (awaiting owner confirmation).
  URL: https://github.com/Surimat/Telegram-Channel-Management-Suite/pull/1
- **Never push directly to `main`.** All work goes to `develop` (or feature
  branches off it) and lands in `main` only via a reviewed pull request.
- `main` still points at the PHASE 3 commit (`f06ba53`) until PR #1 merges.
- No history rewrite, no force push.
- Secret audit before push: `.env`, `data/*.db`, session files and portable
  runtimes are git-ignored and confirmed absent from the remote; the mutable
  runtime dirs (`sessions/`, `logs/`, `data/`, `backups/`, `exports/`) contain
  only `.gitkeep` on the remote. The PHASE 5–6 diff contained no real tokens,
  api_hash values, session strings, passwords or exported PII (only code
  parameter names such as `api_hash`).
