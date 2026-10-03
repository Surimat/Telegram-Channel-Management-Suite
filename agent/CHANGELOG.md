# CHANGELOG — Telegram Channel Management Suite

All notable changes, newest first. Format loosely follows Keep a Changelog.
Dates are ISO-8601.

---

## [Unreleased]

_No unreleased changes._

---

## [0.10.0] — 2026-10-03 — PHASE 10: Portable Windows packaging + backup/restore

### Added — Backend
- `backend/app/services/backup_service.py` — `BackupService`:
  - `create_backup()` writes a single `.tcmsbak` zip (SQLite DB + `manifest.json`)
    with a unique filename; `backup_retention` prunes older files.
  - `list_backups()` / `delete_backup()` / `restore_backup()` — restore always
    writes a safety backup of the current state first.
  - `export_config()` / `import_config()` — JSON transfer of user-owned rows
    (`settings`, `reaction_profiles`, `reaction_rules`) only.
  - Path-traversal protection; sessions excluded unless explicitly requested.
- `backend/app/api/v1/backup.py` + `backend/app/api/schemas/backup.py` —
  `/api/v1/backup` (info, list, create, download, restore, delete) and
  `/api/v1/backup/config/{export,import}`. Friendly RU errors, no secrets.
- `backend/app/api/deps.py` — `get_backup_service`; router registered.
- `backend/app/core/config.py` — `backup_dir`, `backup_retention`,
  `backup_include_sessions`.
- `backend/app/core/paths.py` — `static_dir()` now resolved package-relative so
  code can live under `app/` in a portable build.

### Added — Frontend
- `frontend/src/views/BackupView.vue` (Резервные копии): plain-language help,
  create (with session opt-in + confirmation), list/download/restore/delete,
  configuration export/import. Route + sidebar link + API client methods/types.

### Added — Portable / tooling
- `portable/run.bat` (sets `TCMS_ROOT` + `PYTHONPATH`, creates `.env`, opens the
  browser), `portable/stop.bat` (graceful shutdown), `portable/README.txt`.
- `scripts/build_portable.sh` — assembles the portable tree.
- `tests/test_portable_smoke.py` — spawns the real app with `TCMS_ROOT` in a temp
  dir, asserts `/health`, runtime dirs, and a clean graceful shutdown.

### Tests
- `tests/test_backup_service.py` (9) and `tests/test_backup_api.py` (7). Full
  suite: **330 passed**. `ruff` clean. Frontend builds.

---

## [0.9.0] — 2026-10-03 — PHASE 9: Telegram Mini App (same SPA, one API)

### Added — Backend
- `backend/app/miniapp/` package:
  - `auth.py` — `verify_init_data()` verifies the Telegram `initData`
    HMAC-SHA256 signature (`HMAC_SHA256(bot_token, "WebAppData")`), rejects
    stale/future `auth_date`, and parses the Telegram user. Pure and
    unit-testable (no FastAPI/Telegram imports).
  - `sessions.py` — signed session tokens (`issue_session`/`verify_session`)
    using a key derived from `APP_SECRET_KEY` (`derive_key`); no JWT dependency.
  - `service.py` — `MiniAppService`: reads the sealed manager-bot token, applies
    the owner allow-list, issues sessions, and reports plain-language
    availability (`enabled`/`available`/`reason`/`how_to_fix`).
- `backend/app/api/schemas/miniapp.py` + `api/v1/miniapp.py`:
  `GET /api/v1/miniapp/config`, `POST /api/v1/miniapp/auth` (sets an `HttpOnly`
  session cookie), `GET /api/v1/miniapp/me`, `POST /api/v1/miniapp/logout`.
- Setup Wizard `miniapp` check (`SystemService.miniapp_check`) and
  `get_miniapp_service` dependency.
- Settings: `miniapp_enabled` (off by default), `miniapp_initdata_max_age`,
  `miniapp_session_ttl`, `miniapp_public_url` (env + `.env.example`).
  `miniapp_enabled` and `miniapp_public_url` are DB-overridable.

### Added — Frontend
- `src/telegram.ts` — typed wrapper over the Telegram WebApp SDK (`isTelegramMiniApp`,
  `initTelegramWebApp`).
- `src/stores/miniapp.ts` — Pinia store that bootstraps auth only when
  `initData` is present; inert in a normal browser.
- `App.vue` — friendly loading/error gate inside Telegram; mobile bottom
  navigation (Панель, Боты, Реакции, Очередь, Аналитика, Система, Настройки);
  shows the signed-in user.
- `index.html` — loads the official Telegram WebApp SDK (inert outside Telegram);
  `viewport-fit=cover` for safe areas.
- Mini App types + client methods in `api/client.ts`; responsive + Telegram dark
  theme styles in `styles.css`.

### Tests
- `tests/test_miniapp_auth.py` — valid/tampered/wrong-token/expired/missing
  `initData`, and session issue/verify/expiry/tamper.
- `tests/test_miniapp_api.py` — config/auth/me/logout round-trip, non-owner
  rejection, and a no-secret/no-`initData`-leak assertion. 313 passed total;
  `ruff` clean; SPA builds.

---

## [0.8.0] — 2026-10-03 — PHASE 8: Analytics (content, reactions, audience)

### Added — Backend
- `backend/app/db/repositories/analytics.py` (`AnalyticsRepository`): read-only
  aggregate queries over posts, reaction jobs, audience sources/users/links and
  invite tasks, with portable Python-side per-day bucketing.
- `backend/app/services/analytics_service.py` (`AnalyticsService`): `content()`,
  `reactions()`, `audience()` and `overview()`; RU plain-language summaries,
  percent-change vs. the previous window, titled category/source/status counts.
- `backend/app/api/schemas/analytics.py` + `api/v1/analytics.py`:
  `GET /api/v1/analytics/overview|content|reactions|audience?days=1..365`.
- Registered the analytics router; added `get_analytics_service` dependency.

### Added — Frontend
- `AnalyticsView.vue` (period switch, headline metrics, charts, category/emoji
  bars, audience status, source effectiveness) + `/analytics` route and nav link.
- Dependency-free `Sparkline.vue` and `BarList.vue` inline-SVG chart components.
- Dashboard now shows a "Что показывают цифры" block with the backend summary and
  two sparklines, linking to the full Analytics page.
- Analytics types + client methods in `api/client.ts`; analytics UI styles.

### Tests
- `tests/test_analytics_service.py` (content/reactions/audience/overview, empty
  DB, day clamping, percent-change helpers) and `tests/test_analytics_api.py`
  (all four endpoints, `days` validation, no secret/PII leak). 294 passed total;
  `ruff` clean; SPA builds.

### Decisions
- D-036 (read-only aggregate analytics + backend-owned plain-language summaries),
  D-037 (dependency-free inline-SVG charts).

---

## [0.7.0] — 2026-10-03 — PHASE 7: Tiny AI classifier (rules-first, optional)

### Added — Backend
- `backend/app/ai/` package: `types.py` (`Classifier` Protocol,
  `ClassificationResult`, `ClassificationContext`, `Tone`, source/mode
  vocabularies), `errors.py` (friendly, non-leaking AI errors), `schema.py`
  (strict JSON contract parsing), `classifiers.py` (`RulesClassifier`,
  `LlmClassifier`, `FakeClassifier`), `router.py` (`RoutingClassifier`,
  `RoutingOutcome`, `category_title`), `inference.py` (single-worker bounded
  executor, `run_bounded`), `backends/` (`base.py`, `fake.py`, `llama_cpp.py`,
  registry `build_backend`).
- `backend/app/db/models/ai.py` (`AiMetric`, `AiRecord`) + `repositories/ai.py`
  (`AiRepository`: metrics counters, recent records, trim).
- `backend/app/services/ai_service.py` (`AiService`: effective config, status,
  model list/check/load/unload, routing, metrics/history, events) and
  `ai_help.py` (plain-language setting help, `human_size`).
- `backend/app/api/schemas/ai.py` + `api/v1/ai.py` (status, overview, settings
  GET/PUT, classify, test, models, model check/load/unload, metrics, history),
  registered in `v1/router.py`.
- `Settings` — full AI block (enabled, backend, model path, models dir, threads,
  context, temperature, max tokens, timeout, keep-loaded, both thresholds,
  history limit); `resolve_models_dir()`; `paths.models_dir()`.
- `ReactionService` now classifies through the AI router; `simulate`/`ingest_post`
  accept a mode; Setup Wizard reports an `ai` check.
- `main.py` lifespan now shuts down the AI inference executor on exit.

### Added — Frontend
- `frontend/src/views/AiView.vue` (Обзор / Модель / Настройки / Проверка /
  Диагностика) + AI types/methods in `api/client.ts`, `/ai` route, sidebar link
  «Мини-ИИ». Simulation result types extended with AI fields.

### Added — Tests
- `tests/test_ai_classifier.py` (schema, classifiers, routing policy, inference
  bounds) and `tests/test_ai_api.py` (status/overview/settings/classify/models/
  metrics/history, reaction simulation AI fields, setup check). **281 tests pass;
  `ruff check backend tests` clean.**

### Notes
- The Rules Engine remains the deterministic default. AI is opt-in, consulted only
  when rules are unsure, never picks emoji, and always degrades gracefully
  (D-031…D-035). Models are user-provided `.gguf` assets (gitignored, never
  auto-downloaded).

---

## [0.6.1] — 2026-10-03 — Second GitHub sync (PHASE 4–6 to `develop`)

### Changed
- Pushed PHASE 4–6 to `origin/develop` (`92d94e4`…`3ddc299`) as a fast-forward;
  no force push, no history rewrite.
- `origin/develop` HEAD is now `3ddc299`; `develop` is 0 ahead / 0 behind.
- PR **#1** (`develop → main`) auto-updated to head `3ddc299`; left **open** and
  **unmerged**.

### Verified
- Pre-push secret audit: no `.env`, real tokens, `api_hash` values, `.session`
  files, database files, audience exports or private-data logs are tracked or
  present in the pushed diff; mutable runtime dirs carry only `.gitkeep`.
- `main` was not touched.

_No functional changes in this sync._

---

## [0.6.0] — 2026-10-03 — PHASE 6: Invite Manager

### Added — DB
- `backend/app/db/models/invite.py` — `InviteJob` (target, account/source
  selection, filter snapshot, status, counters, confirmation, `wait_until`) and
  `InviteTask` (per-user status, attempts, scheduled/completed, `wait_until`,
  error); `InviteJobStatus`, `InviteStatus`, `TERMINAL_INVITE_STATUSES`.
- `backend/app/db/repositories/invites.py` — `InviteJobRepository` (CRUD, list,
  active, count_by_status), `InviteTaskRepository` (listing, status counts,
  `claim_batch`, `pending_count`, `unfinished_count`, `next_due`, `retry_failed`).

### Added — service
- `backend/app/services/invite_service.py` — `InviteService`: `preview` (dry-run
  summary), `create_job` (draft + task planning, per-account randomized spacing),
  `confirm_and_start`, `start/pause/resume/stop`, `retry_failed`, `run_tick`
  (bounded durable batch, returns `done`/`more`/`paused`), `recover`, `summary`,
  `explain_job`. FloodWait pauses the run + records the wait; privacy/admin become
  per-user statuses; transient network errors stay pending.

### Added — API + setup
- `backend/app/api/schemas/invites.py`, `backend/app/api/v1/invites.py` —
  preview, summary, list, create, detail, confirm, pause/resume/stop, retry,
  tasks. Friendly envelope; no secret leaks.
- `api/deps.py::get_invite_service`; router registered in `v1/router.py`.
- `main.py` lifespan — `InviteService.recover()` (pauses interrupted runs) and the
  `invite.batch` durable job handler (re-schedules while work remains).
- `services/system_service.py` — new Setup-Wizard `invites` check (plain language).
- `providers/errors.py` / `fake_session.py` / `telethon_session.py` — invite error
  coverage (`ChatAdminRequiredError`, `AlreadyParticipantError` mapping, fake
  `FakeInviteScenario`).
- `core/config.py` — invite settings (`invite_delay_min/max`, `invite_batch_size`,
  `invite_max_total`, `invite_max_per_account`).

### Added — frontend
- `frontend/src/views/InvitesView.vue` — build a run (target, accounts, filters,
  limits, dry-run) → preview summary → create draft → confirm/start → monitor with
  per-status counters and task table; pause/resume/stop/retry. Invite types +
  methods in `api/client.ts`; `/invites` route; sidebar «Приглашения».

### Tests
- `tests/test_invite_service.py`, `tests/test_invite_api.py`; `conftest.py` gained
  an `invite_client` fixture. Suite: **238 passed**; `ruff check backend tests`
  clean.

---

## [0.5.0] — 2026-10-03 — PHASE 5: Audience (sources, parsing, database, export)

### Added — provider abstraction (Telethon stays isolated)
- `backend/app/providers/audience_base.py` — `AudienceProvider` protocol
  (`resolve_entity`, `iter_participant_pages`).
- `backend/app/providers/session_audience.py` — `SessionAudienceProvider`, a thin
  adapter over the PHASE 4 `SessionProvider` (no Telethon import here).
- `backend/app/providers/fake_audience.py` — pure `FakeAudienceProvider` +
  `FakeAudienceScenario` (deterministic paging, hidden participants, injectable
  FloodWait/privacy errors). `fake_session.py` gained `FakeAudienceScenario` +
  `make_fake_users` and participant-page support.
- `providers/registry.py` — `build_audience_provider(...)`; new audience errors
  (`EntityNotFoundError`, `PrivacyRestrictedError`, `ChatAdminRequiredError`) and
  extended DTOs (`EntityRef.participants_count/hidden`, `ParticipantPage`).

### Added — DB
- `backend/app/db/models/audience.py` — `AudienceSource`, `AudienceUser`,
  `SourceUserLink` (+ `SourceType`, `ScanStatus`, `Completeness`, `MemberStatus`);
  dedup via unique `telegram_user_id`, membership via unique `(source_id, user_id)`.
- `backend/app/db/repositories/audience.py` — source/user/link repositories
  (filters, search, sort, pagination, batch streaming, counts, bulk tag ops).
- `backend/app/db/session.py` — Unicode-aware SQLite `lower`/`upper` so
  case-insensitive Cyrillic search works.

### Added — service & API
- `backend/app/services/audience_service.py` — `AudienceService`: sources CRUD,
  `check_source`, `preview_scan` (dry-run), chunked durable scanning with per-chunk
  commits, honest completeness, pause/resume/cancel, `recover()`, tags, explainable
  scoring, dashboard/statistics, streaming CSV/JSON export, CSV/JSON import.
- `backend/app/api/schemas/audience.py`, `backend/app/api/v1/audience.py`,
  `api/deps.py`, router registration. Responses never leak secrets/raw phones; PII
  export is off by default and gated by the `AUDIENCE_STORE_PII` setting.
- `backend/app/services/system_service.py` — Setup-Wizard `audience` check.
- `backend/app/main.py` — registered the `audience.scan` durable job handler and
  best-effort `AudienceService.recover()` (interrupted scans → paused).

### Added — tests
- `tests/test_audience_models.py`, `test_audience_service.py`,
  `test_audience_api.py`, `test_audience_providers.py`,
  `test_audience_security.py`; `conftest.py` gained an `audience_client` fixture.

### Fixed
- Empty final scan page no longer misreported as `NO_ACCESS`.
- Enum-name normalization in repository counts so status tallies are correct.

### Notes
- Suite: **212 passed**; `ruff check backend tests` clean.
- Dedicated Audience/Sources frontend views deferred to the frontend rollout.

---

## [0.4.0] — 2026-10-03 — PHASE 4: User Session Manager (MTProto accounts)

### Added — provider abstraction (Telethon isolated)
- `backend/app/providers/session_base.py` — `SessionProvider` protocol (send_code,
  sign_in, sign_in_password, get_me, health, export_session, resolve_entity,
  get_participants, invite_to_channel, aclose) mirroring `TelegramBotProvider`.
- `backend/app/providers/telethon_session.py` — the **only** module that imports
  Telethon; lazy per-operation connect/disconnect; friendly translation of
  Telethon errors (FloodWait, code/password invalid/expired, api credentials,
  phone banned/invalid, session invalid).
- `backend/app/providers/fake_session.py` — deterministic `FakeSessionProvider` +
  `FakeAuthScenario` for tests and offline mode (no network).
- `providers/registry.py` — `build_session_provider(...)`; new user-account
  errors/DTOs in `providers/errors.py` and `providers/types.py`.

### Added — DB & service
- `db/models/session.py` — `UserSession` + `SessionStatus` enum (online,
  auth_required, disconnected, flood_wait, error, disabled); registered in
  `db/models/__init__.py`.
- `db/repositories/sessions.py` — `SessionRepository` (list/count/by-status/
  by-telegram-id/delete).
- `services/session_service.py` — `SessionService`: durable guided auth wizard
  (api_id/hash + phone → code → optional 2FA), `.session` import with rollback,
  health checks, enable/disable, delete (+ file removal), logout/re-auth,
  `recover()` for interrupted flows. Secrets sealed via `core.security`; full
  phone stored sealed, only masked form in plaintext.

### Added — API & Setup Wizard
- `api/schemas/sessions.py` + `api/v1/sessions.py`:
  `GET /sessions`, `/sessions/summary`, `/sessions/{id}`,
  `POST /sessions/auth/start`, `/sessions/{id}/code`, `/sessions/{id}/password`,
  `/sessions/import`, `/sessions/{id}/health`, `/enable`, `/disable`, `/logout`,
  `DELETE /sessions/{id}`. Responses never contain api_hash, session contents or
  the full phone number (only `phone_masked` + `has_*` booleans).
- `system_service.py` — new Setup-Wizard checks `telethon`, `sessions_dir`,
  `accounts` (plain-language, with "what to do").
- `main.py` lifespan — best-effort `SessionService.recover()` on startup.

### Added — Frontend
- `SessionsView.vue` — guided wizard (API ID/Hash → phone → code → 2FA),
  `.session` import, account list with owner/health/last-check, check/enable/
  disable/re-auth/delete actions, plain-language hints.
- Route `/sessions`, sidebar link «Аккаунты», Dashboard accounts card; new API
  types/methods in `api/client.ts`.

### Added — Tests
- `test_fake_session_provider.py`, `test_session_service.py`,
  `test_sessions_api.py`, `test_session_security.py` (auth flows incl. 2FA,
  import + rollback, health, enable/disable, delete, logout, restart recovery,
  secret redaction, secret-never-leaked-in-API). Total suite: **153 passed**.

### Notes
- `requirements.txt` adds `telethon` (installed 1.45.0).
- No functional change to PHASE 1–3 behaviour; all prior tests stay green.

---

## [0.3.1] — 2026-10-03 — First GitHub sync (develop branch + PR)

### Added / Changed
- Pushed the full local history (PHASE 0–3, commits `0daa91b`…`f06ba53`) to the
  remote branch **`develop`** — the first sync with
  `github.com/Surimat/Telegram-Channel-Management-Suite`.
- Opened PR **#1** (`develop → main`); **not merged** (requires owner confirmation).
- `main` was intentionally left untouched (no direct push, no history rewrite, no
  force push).
- Fixed the local `origin` fetch refspec (`+refs/heads/*:refs/remotes/origin/*`)
  so all remote branches are tracked.
- Pre-push secret audit confirmed: `.env`, `data/*.db`, session files, tokens and
  portable runtimes are git-ignored and absent from the remote; mutable runtime
  dirs contain only `.gitkeep`.
- Documentation/persistent memory updated: development now proceeds on `develop`;
  `agent/CURRENT_STATE.md` gained a "GitHub sync & branching" section.

_No functional changes in this sync._

---

## [0.3.0] — 2026-10-03 — PHASE 3: Reaction Manager (rules, planner, scheduling, UI)

### Added — Rules Engine (deterministic, editable)
- `backend/app/rules/engine.py` — `RulesEngine`, `Category` (9 categories),
  `RuleSpec`, `RuleMatch`; keyword/phrase/regex matching with exclusions,
  `min_confidence`, priority, language gate, and `manual_override` (always wins).
  Confidence is a transparent matched-terms score; unknown text → `neutral`.
- `backend/app/rules/delays.py` — `DelayPreset` (`early`/`normal`/`spread`),
  `scaled_window`, `distribution_for`, `UniformDelay`.
- `backend/app/rules/defaults.py` — `default_rule_specs()`: the seed RU+EN rule
  set (donation/news/funny/sad/angry/cute/support/announcement) with
  allowed/preferred/forbidden reactions.

### Added — Data model & repositories
- `db/models/post.py` — `Post` (`text`, `category`, `confidence`,
  `classification_source`, `status`, `channel_id`, `telegram_message_id`, …).
- `db/models/reaction.py` — `ReactionProfile`, `ReactionRule`, `ReactionJob`
  (+ `ReactionJobStatus`); job stores `post_id`, `bot_id`, `reaction`,
  `scheduled_at`, `status`, `attempts`, `error`, `completed_at`, `queue_job_id`.
- `db/repositories/posts.py`, `db/repositories/reactions.py` (profiles, rules
  incl. `clear_defaults`, jobs incl. `for_post`).

### Added — Planner & service (vertical slice)
- `services/reaction_planner.py` — pure `ReactionPlanner` with injectable RNG:
  participation gate, skip gate, weighted emoji choice, per-bot delay from the
  profile window/preset, `max_bots_per_post` cap, one reaction per bot/message.
- `services/reaction_service.py` — `ReactionService`: profile CRUD + validation,
  rule CRUD + seeding, `resolve_profile`, `_classify` (DB rules w/ default
  fallback), `simulate` (no Telegram), `ingest_post`/`plan_post` (durable jobs),
  `execute_reaction_job` (via provider; FloodWait never bypassed), `recover`,
  global enable/disable, `stats`.
- `providers/types.py`/`base.py`/`fake_bot.py`/`aiogram_bot.py` — added
  `set_reaction`; the fake records `(chat_id, message_id, emoji)` deterministically
  and can be told to fail per emoji.

### Added — Scheduling
- `scheduler/scheduler.py` — handlers now receive `(session, job)` so a handler
  runs in the scheduler's own transaction (fixes a nested-session SQLite deadlock
  on slow/weak machines).
- `main.py` — registers the `reaction.job` handler; seeds default rules and a
  default profile; recovers interrupted reaction jobs on startup.

### Added — API
- `api/schemas/reactions.py`, `api/v1/reactions.py` — profiles/rules/posts/jobs,
  `simulate`, `status`, `enable`/`disable`, `categories`; `api/deps.py` gained
  `get_reaction_service`; router registered in `v1/router.py`.
- `services/system_service.py` — new `reactions` Setup-Wizard check with
  plain-language meaning + hint.

### Added — Frontend
- `views/ReactionsView.vue` — tabs: Обзор (global switch + counters), Профили
  (editor with sliders/tooltips), Правила (full editor incl. allowed/forbidden
  reactions), Симуляция (preview table + "ingest & plan"), Очередь (status
  filter). Reaction types/methods in `api/client.ts`, `/reactions` route, nav
  link, and a Reactions card on the Dashboard.

### Added — Tests (48 new; suite 60 → 108)
- `tests/test_rules_engine.py`, `tests/test_delays.py`,
  `tests/test_reaction_planner.py`, `tests/test_reaction_service.py`,
  `tests/test_reactions_api.py` — including fake-provider execution, FloodWait
  handling, restart recovery, determinism, and an end-to-end scheduler→provider
  test. `ruff check backend tests` clean.

### Changed
- `tests/test_scheduler.py` updated for the `(session, job)` handler signature.

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
