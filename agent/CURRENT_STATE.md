# CURRENT STATE — Telegram Channel Management Suite

> Persistent project memory. **A new agent must be able to continue from this
> file + git + code alone.** Update this after every major phase.

**Last updated:** 2026-10-06
**Current phase:** **v1.x maintenance (no new phases).** **v1.5.1 forensic-audit fixes are released** — reviewed `develop → main` PR #12 (merge `f41ebc8`), tag `v1.5.1`; the Release workflow (run `37453582161`) created the GitHub Release and attached the Windows portable ZIP (24 796 203 bytes, sha256 `b46f9333…68dee`) + `.sha256` (D-060). It fixes five confirmed discrepancies found by an independent audit of v1.5.0 (D-095…D-098): a capability with no implementation can never report `available` (`config_sync`/`media_conversion` → `not_implemented`, guarded by a CI check); a consistency check that raises is an `error` finding, never silently skipped; the stored `language` preference is actually consumed (capability graph + a Settings RU/EN selector); source-comparison checks report `audit.source_unavailable` as `info` when the runtime image has no frontend/docs source (so Docker `/api/v1/consistency` is `pass`); and `README.md` version drift. Version strings read **1.5.1**. Suite **731 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean; Docker smoke clean; artifact/secret scan clean.
Previous: **v1.5.0 Capability graph + i18n + Consistency Auditor is released** — reviewed `develop → main` PR #11 (merge `ad24bc6`), tag `v1.5.0`; the Release workflow (run `37442056281`) created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds (D-092…D-094): It adds three small, additive cross-cutting layers: a machine-readable **capability graph** (`services/capability_graph.py`, `GET /api/v1/capability-graph`, embedded in the Promotion Wizard's `WizardState.capabilities` and shown on the Dashboard as "Что уже доступно"); a bilingual RU/EN **i18n catalog** (`core/i18n.py`) with a stored `language` preference on `/api/v1/help/prefs`; and a **Consistency Auditor** (`services/consistency_checks.py` static + `services/consistency.py` runtime, `GET /api/v1/consistency`, Diagnostics "Проверка целостности" panel) whose static checks run in `pytest` so cross-module drift fails a PR. Version strings read **1.5.0**. Suite **726 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean; Docker smoke clean; artifact/secret scan clean.
Previous: **v1.4.0 Notification Center + Tray Agent + Editorial Workspace is released** — reviewed `develop → main` PR #10 (merge `306672e`), tag `v1.4.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds the **Notification Center** (D-084…D-086): a durable, queryable history of important events with categories, priorities, per-category routing (owner DM / notification group / Windows toast), quiet hours that postpone only non-urgent messages, anti-spam aggregation, a dashboard and a history API/UI; the **TCMS Tray Agent** (D-087/D-088): a light Windows supervisor that starts the backend hidden, waits for `/health` (never a fixed sleep), restarts a crashed backend with a bounded backoff (5/hour), offers optional Startup-folder autostart (no admin) and writes only a secret-free `data/tray.json` snapshot surfaced in Diagnostics; and the **Editorial Workspace** (D-089…D-091): a linked Telegram forum supergroup where the owner, editors and moderators work the same publication queue as the Web UI (honest, verified bot rights; roles by numeric Telegram id; optimistic-version moves; a full audit trail; publishing reuses the Content Studio posting path). None of these features register accounts or bypass Telegram limits.
Earlier: **v1.3.0 Bot Factory + LAN Mesh is released** — PR #9 (`develop → main`, merge `7788125`), tag `v1.3.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds the **Bot Factory** (D-077/D-078): plan a set of worker bots, check usernames with Telegram, create each bot through the official owner-confirmed @BotFather flow and adopt it, then bind it through the existing binding rules; and the **optional LAN Mesh / offline control plane** (D-079…D-082): deterministic identity, bounded broadcast discovery + manual peers, one-time-code pairing, deterministic coordinator election, fencing leases, a `mesh.tick` maintenance job and a guard so only the coordinator polls Telegram. Standalone (one computer) stays the default. New API (`/api/v1/bot-factory/*`, `/api/v1/mesh/*`), two RU-first UI pages (`/bot-factory`, `/mesh`) and offline tests. Pre-release hardening (D-083): pairing never persists/returns anything derived from a secret, and `/api/v1/mesh/ping` authenticates the shared secret; help topics `bot_factory` / `lan_mesh` added.
Earlier: **v1.2.0 Content Studio is released** — PR #8 (`develop → main`, merge `ea6c161`), tag `v1.2.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds the v1.2 **content-studio foundation** (D-071…D-076): content sources (Telegram / RSS / Atom / manual) with deduplication, a deterministic explainable cleaner, usage-rights tracking + attribution, Telegram markup validation + a Telegram-like preview, inline button sets, per-source moderation (blocked keywords + quiet hours), multi-channel planning/calendar, publishing through a `PostingProvider` (bot by default; user account only in the expanded mode), durable auto-delete and first comments, and a bounded restart-safe posting tick (`content.posting`). Nothing is published without an explicit owner action; protected content keeps only its link (D-006/D-074); the AI narrows, it never picks emoji (D-033/D-076).
Earlier: **v1.1.0 is released** — PR #7 (`develop → main`, merge commit `3438305`), tag `v1.1.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It carries the multi-format **Account Hub** importer (`.session`, `.session`+JSON, StringSession, optional TDATA; D-070), optional per-account **network routes (proxies)** (D-065), **donor discovery** (candidate proposals only, D-066), a **lightweight local encoder** classifier mode (D-067) with the optional **ruBERT-tiny2** embedding backend + install flow (D-068), and the bot-only/risk UX (D-069). The v1.0.5 **product slice** (D-064): bot↔channel **bindings** + channel **reaction capabilities**, session-free invite **Кампании** + explainable **donor quality**, **backup delivery destinations**, a resumable first-run **Setup Wizard**, and a conservative, off-by-default **auto-update**. `v1.0.0`–`v1.1.0` stay immutable (D-050).
Version string is **1.5.1** across `backend/app/__init__.py`, `pyproject.toml`, `frontend/package.json` + lock.
All gates pass: `pytest` **731 passed**, `ruff` clean, `vue-tsc` + `npm run build` clean; **GitHub Actions CI** (D-053) enforces the backend and frontend gates.

### Forensic audit of v1.5.0 (2026-10-06, D-095…D-098)

An independent audit verified the claimed v1.5.0 state against the code and fixed
five confirmed discrepancies (all additive, no new features):

1. **False capability (fixed):** `config_sync` reported **`available` on an empty
   install** while no sync implementation existed; `media_conversion` was listed
   but no ffmpeg/media tooling exists. Both are now `implemented=False` →
   `not_implemented` ("Не реализовано"), and `check_capability_implementation()`
   fails CI if any capability claims `implemented` without code (D-095).
2. **Silent failure (fixed):** `_runtime_findings` (and `run_static_checks`)
   swallowed check exceptions with `except Exception: continue`; a check that
   never ran looked like a pass. A raising check is now an `error` finding
   `audit.check_failed.<name>` (D-096).
3. **Write-only language preference (fixed):** the stored `language` preference and
   the i18n catalog were never consumed by the UI. `GET /api/v1/capability-graph`
   now honours the saved preference, and Settings has a real RU/EN selector
   (D-097). Scope is honest: the RU-first help catalog stays RU (not
   machine-translated).
4. **Runtime-image false failure (fixed):** the Docker smoke surfaced that the new
   no-silent-failure runner reported `overall: fail` in the runtime image (it
   ships no `frontend/`/`docs/` source). Source-comparison checks now report
   `audit.source_unavailable.<name>` as **info** and are skipped, so the Docker
   report is `pass`; the dev checkout and CI still run every check (D-098).
5. **Doc drift (fixed):** `README.md` still said "Current stable release: `v1.4.0`"
   in two places; updated to `v1.5.0`/`v1.5.1`.

Evidence: `pytest` **731 passed** (was 726; +5 audit tests), `ruff` clean,
`vue-tsc` + `npm run build` clean, capability graph on an empty DB reports
`config_sync`/`media_conversion` as `not_implemented`, the EN preference returns
EN capability labels end-to-end, and the Docker `/api/v1/consistency` report is
`pass` (5 info, 0 error).
**Repository status:** `main` carries the v1.5.1 release merge (`f41ebc8`, PR #12); `develop` is that merge (synced back); tags `v1.0.0`–`v1.5.1`; each GitHub Release carries the Windows portable ZIP + `.sha256` (built by CI, D-060).
**Branch:** develop (working branch); main is released and updated only via pull request.
**Latest work (v1.5.1 forensic-audit fixes — released):** `services/capability_graph.py` (`implemented` flag + `STATE_NOT_IMPLEMENTED`), `services/consistency_checks.py` (`check_capability_implementation` + `_SOURCE_CHECKS` runtime-image guard + no-silent-failure runner), `services/consistency.py` (no-silent-failure runtime auditor), `api/v1/capability_graph.py` (language from the saved UI preference), `core/i18n.py` (`cap.state.not_implemented`), `services/ui_prefs.py` (`language` preference consumed), `frontend/src/stores/help.ts` + `SettingsView.vue` (RU/EN selector), `DashboardView.vue` (renders the `not_implemented` note). Tests: `test_unimplemented_capabilities_are_never_available`, `test_capability_graph_language_follows_ui_preference` (`test_consistency.py`), `test_capabilities_have_implementations`, `test_auditor_never_swallows_a_failed_check`, `test_missing_source_tree_is_info_not_error` (`test_architecture_consistency.py`). Suite **731 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean. Released via a reviewed `develop → main` PR #12 (merge `f41ebc8`), tag `v1.5.1`; Release workflow (run `37453582161`) attached the Windows portable ZIP (24 796 203 bytes, sha256 `b46f9333…68dee`) + `.sha256`. Docker smoke: `/health` → `1.5.1`, SPA `200`, `/api/v1/capability-graph` → `not_implemented` for `config_sync`/`media_conversion`, `/api/v1/consistency` → `pass`; artifact scan clean (no sessions/TDATA/DB/model).

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
- `agent/` — this file, `NEXT_TASK.md`, `DECISIONS.md` (D-001…D-064),
  `CHANGELOG.md`.
- `.gitignore` (secrets/sessions/data/logs/backups/models protected),
  `.env.example`, `README.md`.
- `.github/workflows/ci.yml` — CI on pushes/PRs to `main`/`develop`: backend
  (`ruff` + `pytest`) and frontend (`npm ci` + `npm run build`).

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

### PHASE 8 — Analytics (content, reactions, audience + Dashboard insight)
- `backend/app/db/repositories/analytics.py` — `AnalyticsRepository`: read-only
  aggregates over posts, reaction jobs, audience sources/users/links and invite
  tasks. Per-day series are bucketed in Python (`_buckets`/`_day_key`) for
  portability; helpers `_rows`/`_scalar`/`_scalars`/`_value`. Every query takes an
  optional `channel_id` (D-055) and scopes via `_scoped_posts`/`_scoped_reactions`/
  `_scoped_audience_users`/`_channel_source_ids`.
- `backend/app/services/analytics_service.py` — `AnalyticsService`:
  `content()`/`reactions()`/`audience()`/`overview()` (all accept `channel_id`),
  RU plain-language summaries, percent-change vs. the previous window, titled
  counts (`_CATEGORY_TITLES`/`_SOURCE_TITLES`/`_AUDIENCE_STATUS_TITLES`),
  `_clamp_days`.
- `backend/app/api/schemas/analytics.py` + `api/v1/analytics.py` —
  `GET /api/v1/analytics/overview|content|reactions|audience?days=1..365&channel_id=`;
  registered in `v1/router.py`; `api/deps.py::get_analytics_service`.
  `AnalyticsOverviewOut` echoes `channel_id`.
- `frontend/src/views/AnalyticsView.vue` — channel + period switches, headline
  metrics, sparklines, category/emoji bars, audience status, source effectiveness
  table; `/analytics` route + sidebar «Аналитика».
- `frontend/src/components/Sparkline.vue` + `BarList.vue` — dependency-free
  inline-SVG/CSS charts (D-037).
- `frontend/src/views/DashboardView.vue` — new "Что показывают цифры" block
  (backend summary + two sparklines) linking to `/analytics`.
- Analytics types + client methods in `frontend/src/api/client.ts`; analytics
  styles appended to `frontend/src/styles.css`.
- `tests/` — `test_analytics_service.py`, `test_analytics_api.py` (13 tests).

### PHASE 9 — Telegram Mini App (same SPA, one API)
- `backend/app/miniapp/auth.py` — `verify_init_data()`: HMAC-SHA256
  (`HMAC_SHA256(bot_token, "WebAppData")`) over sorted pairs, constant-time
  compare, `auth_date` freshness, user parse. `MiniAppAuthError`, `MiniAppUser`.
- `backend/app/miniapp/sessions.py` — `issue_session`/`verify_session`: HMAC
  tokens keyed by `derive_key("miniapp-session")`; `MiniAppSessionError`.
- `backend/app/miniapp/service.py` — `MiniAppService`: sealed manager-token read,
  owner allow-list (`settings.admin_ids`), DB-overridable `miniapp_enabled` /
  `miniapp_public_url`, plain-language `MiniAppStatus`, and `setup()` — the
  one-click registration helper (D-054) that points the manager bot's Web App
  menu button at a public HTTPS URL.
- `backend/app/api/schemas/miniapp.py` + `api/v1/miniapp.py` —
  `GET /config`, `POST /setup` (register menu button), `POST /auth` (sets
  `HttpOnly` `tcms_miniapp` cookie), `GET /me`, `POST /logout`; registered in
  `v1/router.py`; `api/deps.py::get_miniapp_service`.
- `backend/app/providers/base.py` — `TelegramBotProvider.set_menu_button`;
  implemented by `aiogram_bot.py` (`set_chat_menu_button`) and `fake_bot.py`.
- `backend/app/services/system_service.py` — `miniapp_check` added to the Setup
  Wizard checks.
- `backend/app/core/config.py` + `.env.example` — `miniapp_enabled` (off by
  default), `miniapp_initdata_max_age`, `miniapp_session_ttl`,
  `miniapp_public_url`.
- `frontend/src/telegram.ts` — typed Telegram WebApp SDK wrapper;
  `frontend/src/stores/miniapp.ts` — Pinia bootstrap store (inert in a browser).
- `frontend/src/App.vue` — Telegram gate + mobile bottom nav + user line;
  `index.html` loads the WebApp SDK and uses `viewport-fit=cover`;
  Mini App types/methods in `api/client.ts`; responsive + dark styles in
  `styles.css`.
- `tests/` — `test_miniapp_auth.py`, `test_miniapp_api.py` (19 tests).

### PHASE 10 — Portable packaging + backup/restore
- `backend/app/services/backup_service.py` — `BackupService`: `.tcmsbak` zip
  (DB + `manifest.json`), unique filenames, retention prune, safety backup on
  restore, config export/import (`settings`/`reaction_profiles`/`reaction_rules`
  only), path-traversal guard, sessions excluded by default.
- `backend/app/api/schemas/backup.py` + `api/v1/backup.py` — `/backup`
  info/list/create/download/restore/delete + `/backup/config/{export,import}`;
  `api/deps.py::get_backup_service`; registered in `v1/router.py`.
- `backend/app/core/config.py` + `.env.example` — `backup_dir`,
  `backup_retention`, `backup_include_sessions`.
- `backend/app/core/paths.py` — `static_dir()` now package-relative.
- `frontend/src/views/BackupView.vue` (Резервные копии) + route + nav + client
  types/methods.
- `portable/run.bat` (sets `TCMS_ROOT`/`PYTHONPATH`, opens browser),
  `portable/stop.bat`, `portable/README.txt`.
- **Release-engineering packaging (D-056/D-057):** `scripts/build_portable.sh`
  is now cross-platform and emits a versioned ZIP (+ `.sha256`);
  `scripts/build_win_runtime.py` stages the embedded Windows CPython + pinned
  `win_amd64` wheels from `scripts/win-requirements.lock` (extracted flat, no
  compiler — `pyaes` comes from its pure-Python sdist);
  `scripts/fetch_embedded_python.sh` retained (now with `--no-deps`).
  `.github/workflows/release.yml` builds and attaches the ZIP to the GitHub
  Release on a `v*` tag.
- `tests/` — `test_backup_service.py` (9), `test_backup_api.py` (7),
  `test_portable_smoke.py` (1 startup smoke + offline-tree/ZIP-layout + builder
  dry-runs).

### PHASE 11 — VPS / Docker production config
- `docker/Dockerfile` — multi-stage (Node SPA build → `python:3.12-slim`,
  non-root uid 10001). Built and smoke-tested locally.
- `docker/docker-compose.yml` — one `app` service; optional `.env`; bind-mounted
  `data/ sessions/ backups/ logs/ exports/`; `/health` healthcheck;
  `restart: unless-stopped`; publishes `127.0.0.1:8000` only.
- `docker/docker-compose.proxy.yml` + `docker/Caddyfile` — optional TLS overlay
  (Caddy, automatic Let's Encrypt) fronting `app:8000`.
- Docs: `docs/SETUP.md` (mode C full walkthrough + nginx alt), `docs/SECURITY.md`
  (VPS specifics), `docs/TROUBLESHOOTING.md` (container issues),
  `docs/ARCHITECTURE.md` (§11 Docker/VPS).

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
- **Post-roadmap polish**: `src/views/SourcesView.vue` (source list, add, check,
  scan confirmation + progress, pause/resume/cancel) and
  `src/views/AudienceView.vue` (paginated user table, search/filters/presets,
  tags, bulk actions, detail, export/import); `/sources` and `/audience` routes,
  sidebar + Mini App nav entries, and audience types/methods in `api/client.ts`.

### Ops / packaging (PHASE 1 foundation)
- `backend/requirements.txt`, `backend/requirements-dev.txt`.
- `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- `portable/run.bat`, `portable/stop.bat`, `portable/README.txt` — completed in
  PHASE 10 (see the PHASE 10 section above).
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
- `ruff check backend tests` → clean. `pytest` → **413 passed** (after the hardening tests).
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
- **Analytics (PHASE 8)**: read-only `/api/v1/analytics/*` aggregates over posts,
  reactions, audience and invites, with RU plain-language summaries and
  percent-change; the «Аналитика» page (charts, bars, tables) and a Dashboard
  "Что показывают цифры" block render them. Verified in offline mode (server +
  curl → `/analytics/overview`, SPA `/analytics` → 200) and covered by 13 tests.
  Responses contain only aggregate counts (no secrets/PII).
- **Mini App (PHASE 9)**: the same SPA detects Telegram WebApp `initData`,
  authenticates via `/api/v1/miniapp/auth` (server-side HMAC verification),
  and shows a mobile bottom-nav layout inside Telegram while the desktop Web UI
  is unchanged. Verified in offline mode (`/miniapp/config` → 200 with a
  plain-language unavailable reason, `/miniapp/me` → `authenticated:false`, SPA
  `/` → 200) and covered by 19 tests. No token/`initData` leak in responses.

## 4. What does NOT exist yet

- **Worker Mesh remote dispatch/execution — PARTIAL (verified 2026-10-05).** The
  LAN Mesh ships the *worker primitives* (the `WORKER` role, capability
  advertisement/matching, fencing-token leases that a worker can acquire/complete,
  `reclaim_expired`, coordinator election, and the coordinator-only poller guard
  in `main.py`), but there is **no remote job-dispatch + worker-execution loop**:
  `MeshTransport` is used only for the `/api/v1/mesh/ping` liveness probe, and
  leases are acquired/completed locally through `/api/v1/mesh/leases/*`, not pulled
  from a coordinator and executed on a peer. **VPS Worker mode** (`MeshMode.VPS_WORKER`)
  is a declared enum/config value only — there is no PostgreSQL control plane
  (SQLite-now/Postgres-later, D-002). So the LAN Mesh is a real *coordination layer*
  for the owner's own computers, not a distributed job mesh.
- Mini App: BotFather Web App **menu-button** registration is automated
  (`POST /api/v1/miniapp/setup`, D-054); providing a public HTTPS URL remains the
  owner's deployment step. The Mini App is off by default.
- Reactions/audience store their own channel text in places; invites, posts,
  audience sources, the permission probe and analytics consume the registry.
- ~~Channel binding registry/UI~~ — **done** (hardening, see §2b).
- ~~Alembic migrations~~ — **done** (hardening, see §2b).
- ~~Account permission probe~~ — **done** (post-1.0 hardening, see §2a).
- ~~Manager-bot runtime / command loop / notifications~~ — **done** (post-1.0
  hardening, see §2a).
- ~~Owner-facing diagnostics / redacted support report~~ — **done** (v1.0.3,
  see §2d).

## 2a. Post-1.0 hardening (2026-10-03) — complete in code

**Account permission probe.**
- `backend/app/providers/session_base.py` — `SessionProvider` gained
  `probe_permissions(...)`; `providers/types.py` gained `PermissionReport`;
  implemented in `telethon_session.py` and the fake (`FakePermissionScenario`).
- `backend/app/db/models/permission.py` (`PermissionCheck`) +
  `db/repositories/permissions.py`.
- `backend/app/services/permission_service.py` — `MODULE="permissions"`; maps
  provider errors to `ok|partial|no_access|auth_required|admin_required|
  privacy_restricted|flood_wait|error`; stores each check; `latest()`/`history()`.
- `backend/app/api/schemas/permissions.py`, `api/v1/permissions.py`,
  `api/deps.py::get_permission_service`, router registered in `v1/router.py`.
- Frontend: permission-probe panel in `SessionsView.vue`.

**Manager-bot runtime + notifications.**
- `backend/app/manager/bus.py` — bounded, non-blocking `NotificationBus`; six
  categories (`system|telegram|reactions|audience|invites|ai`); `MODULE_TO_CATEGORY`,
  `category_for_module`, `publish`, `reset_notification_bus`.
- `backend/app/manager/service.py` — `ManagerBotService`: admin whitelist
  (`MANAGER_BOT_ADMIN_IDS`), RU commands, provider construction,
  `deliver_pending`, `notification_settings`/`update_notification_settings`
  (stored in the existing `settings` table).
- `backend/app/manager/runtime.py` — `ManagerBotRuntime` (one asyncio task, short
  polling, exponential backoff, graceful stop).
- `backend/app/api/schemas/manager.py`, `api/v1/manager.py` (`/manager/status`,
  `/manager/notifications`), `api/deps.py` deps, router registered.
- `backend/app/main.py` — starts/stops the runtime in lifespan (gated by
  `MANAGER_RUNTIME_ENABLED`); publishes start/stop notifications.
- Provider extensions: `TelegramBotProvider.get_managed_bots`, update/command
  support (aiogram + fake). Notifications wired into `events_service`,
  `ai_service`, `backup_service`.
- Frontend: notification toggles in `SettingsView.vue`; manager card in
  `SystemView.vue`; types/methods in `api/client.ts`.
- Config: `manager_runtime_enabled`, `manager_runtime_poll_interval`.
- Tests: `tests/test_manager_bot.py` (26), `tests/test_permission_service.py` (13),
  `tests/test_hardening_api.py` (9); `conftest.py` gained `permission_client` /
  `manager_client` fixtures and sets `MANAGER_RUNTIME_ENABLED=false`.

Decisions: D-047, D-048, D-049.

## 2b. Hardening (2026-10-03) — versioned migrations + Channel Registry

**Versioned Alembic migrations (replace `create_all` at startup).**
- `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, and a baseline
  revision under `migrations/versions/` autogenerated from the models (revision id
  changes whenever the baseline is regenerated).
- `backend/app/db/migrate.py` — guarded runner: fresh install / existing
  `create_all` DB (adopt + stamp) / normal upgrade, pre-migration backup,
  transaction-per-migration, DB state constants.
- `backend/app/core/paths.py` — `project_root()`, `code_root()`, `alembic_ini()`
  (migration dir resolved relative to code, not the mutable data root).
- `backend/app/main.py` — startup applies migrations (no `create_all`).
- `backend/app/services/system_service.py` — DB check is migration-aware;
  `api/schemas/system.py` + `api/v1/system.py` expose migration status/upgrade.
- `docker/Dockerfile` ships `alembic.ini` + `migrations/`; `scripts/build_portable.sh`
  copies them into the portable bundle.
- Docs: `docs/database-migrations.md`. Tests: `tests/test_migrations.py`.

**Channel Registry (one shared channel identity).**
- `backend/app/db/models/channel.py` (`Channel`, `ChannelKind`, `ChannelStatus`) —
  reference/telegram_id/username/title/kind/status/is_default/modules(JSON)/
  verification fields/participants_count/note; registered in models `__init__`.
- `backend/app/db/repositories/channels.py`, `services/channel_service.py`
  (`normalize_reference`, add/verify/set_modules/set_default/delete/list/summary),
  `api/schemas/channels.py`, `api/v1/channels.py`, `api/deps.py::get_channel_service`,
  router registered. Verification reuses `PermissionService` (never bypasses limits).
- Invite integration: `invite_jobs.channel_id` added; invite create/preview resolve
  the target from the chosen registry channel (fallback to a typed target).
- Post ingestion + audience sources: `posts.registry_channel_id` and
  `audience_sources.channel_id` link to the registry; the API resolves the
  channel's reference/username from a chosen registry id (friendly 404 if
  unknown). Migration `e3b5890e407e`.
- Permission probe: `permission_checks.registry_channel_id` links a probe to the
  chosen registry channel; `POST /api/v1/permissions/check` accepts `channel_id`
  and `ChannelService.verify` links its probe. Migration `6816b29afc76`.
- Frontend: RU-first "Каналы" page (`ChannelsView.vue`, nav + route), channel
  types/methods in `api/client.ts`; invite form, audience source form, reactions
  simulation/ingest panel and the Sessions permission panel each gained a channel
  picker.
- Tests: `tests/test_channels.py` (21) + `tests/test_permission_service.py` + `conftest.py::channel_client`.

Decisions: D-051, D-052.

**Migration adoption fix (high severity).** A v1.0.0 install (built with
`create_all`, no `channels` table) was stamped at Alembic *head* without running
the registry migration, so the app crashed on the missing `channels` table.
`migrate.py` is now **baseline-aware**: it stamps such a database at the baseline
revision and upgrades through the deltas, and `database_status` reports a pending
upgrade. Migration history: `0191baf5265f` (baseline = v1.0.0 schema) →
`561f0631d045` (channel registry) → `e3b5890e407e` (registry links for sources
and posts) → `6816b29afc76` (registry link for permission checks). Regression
test upgrades a v1.0.0-shaped database with existing rows. Decisions: D-052.

## 2c. Release engineering (2026-10-04) — reproducible, installable packaging

**Version is `1.0.2`** across `backend/app/__init__.py`,
`pyproject.toml`, `frontend/package.json` and `frontend/package-lock.json`
(was `1.0.1`; D-057, D-060).

**Cross-platform, reproducible Windows portable runtime.**
- `scripts/build_win_runtime.py` — downloads the official Windows **embeddable**
  CPython (`python-3.12.7-embed-amd64.zip`) and the pinned `win_amd64` wheels,
  extracts them flat into `runtime/site-packages`, and writes `python312._pth`
  (`python312.zip`, `.`, `../app`, `site-packages`, `import site`). No compiler:
  `pyaes` (Telethon dep, sdist-only) is extracted from its pure-Python sdist.
- `scripts/win-requirements.lock` — pinned Windows runtime set (uvicorn base, not
  `[standard]`; see D-056).
- `scripts/build_portable.sh` — cross-platform; builds the SPA, stages the app +
  runtime, and writes a versioned ZIP
  (`Telegram-Channel-Management-Suite-Windows-Portable-<version>.zip`) plus
  `.sha256`. New flags `--no-runtime`, `--no-zip`, `--no-frontend`.
- `scripts/fetch_embedded_python.sh` — retained (host-driven path), gained
  `--no-deps`.

**CI/release automation.**
- `.github/workflows/release.yml` — on a `v*` tag (or manual dispatch): verify
  (ruff + pytest + SPA build), build the portable ZIP, upload it as an artifact
  and attach it (+ checksum) to the GitHub Release.
- `.github/workflows/ci.yml` (D-053) unchanged.

**Dependencies.** `backend/requirements.txt` now uses base `uvicorn` instead of
`uvicorn[standard]` (the app uses no WebSockets and the default asyncio loop;
this removes uvloop/httptools/watchfiles/websockets and keeps the portable
runtime small and cross-buildable). `--reload` now needs `watchfiles`
(documented).

**Verification (this pass).** `pytest` **427 passed**; `ruff` clean; `vue-tsc` +
`npm run build` clean; `docker build` succeeded and the container served
`/health` + the SPA; the staged portable tree started end-to-end from a path with
spaces and Cyrillic, applied migrations, created a backup, restored it, and shut
down gracefully via `/api/v1/system/shutdown`. Decisions: D-056, D-057.

## 2d. Product polish (v1.0.3, 2026-10-04) — Diagnostics + redacted report

**Version is `1.0.3`** across `backend/app/__init__.py`, `pyproject.toml`,
`frontend/package.json` + `package-lock.json`.

**Backend.**
- `backend/app/core/redaction.py` — reusable redaction: masks bot tokens
  (`\d{6,}:[A-Za-z0-9_-]{30,}`), `api_hash`/`api_id` key-value pairs, Telethon
  session strings, E.164 phones, registered secrets, and long hex/base64 blobs.
  `redact_text`, `redact_mapping` (drops forbidden keys), `scan` (finds leaks) and
  `redact_and_verify` (redact + re-scan safety gate).
- `backend/app/services/diagnostics_service.py` — `DiagnosticsService`: aggregates
  14 subsystem checks (application, database via `migrate.database_status`,
  telegram_api, manager_bot, managed_bots, sessions, channels, audience, reactions,
  invites, ai, scheduler, storage, portable_runtime) into `DiagnosticsReport`; the
  report payload (`build_report_payload`) plus `build_report(fmt)` for
  json/txt/zip; and the safe actions `restart_scheduler`, `recheck_telegram`,
  `recheck_channels`, `cleanup_jobs`.
- `backend/app/scheduler/handlers.py` — `register_handlers(scheduler)` (the
  durable-queue handlers moved out of `main.py`) so a UI scheduler restart rewires
  identically.
- `backend/app/api/v1/diagnostics.py` + `api/schemas/diagnostics.py` +
  `api/deps.py::get_diagnostics_service` — endpoints under `/api/v1/diagnostics`.
- `backend/app/db/repositories/jobs.py` — added read/safe-mutation helpers:
  `list_stuck_running`, `list_overdue`, `cancel_many`, `status_counts`,
  `kind_counts`, `failed_since`, `oldest_pending_at`.
- **Frontend** — `frontend/src/views/DiagnosticsView.vue` (`/diagnostics`, sidebar
  «Диагностика»), diagnostics types + methods in `api/client.ts`.

**Report safety.** The report is redacted then re-scanned; if `clean` is false no
file is produced (`DiagnosticsError` → HTTP 500 with a friendly message). It
contains no tokens, keys, session data, phones, passwords, DB contents, audience
records or private logs. Header `X-Diagnostics-Redacted: true`.

**Tests.** `tests/test_diagnostics.py` — redaction of every secret kind, mapping
key-dropping, the safety scan, report generation (json/txt/zip), absence of
secrets/DB contents, status aggregation, the API, non-destructive cleanup, and
graceful degradation (a failing check or report section yields a friendly row /
safe empty section instead of HTTP 500). Full suite: **462 passed**, `ruff`
clean, `vue-tsc` + `npm run build` clean.

**UI wording.** Audience page title → «Аудитория»; invites task list → «Задания»;
Queue page → Russian labels for job kinds/statuses (one term per entity;
`docs/UI.md` §11). Decisions: D-061.

## 2e. v1.0.4 — startup robustness + beginner polish (2026-10-04, released)

Patch release (merge `3f42c3d`, PR #5, tag `v1.0.4`). No new phases/features.

- **Corrupt database is explained, not fatal.** A damaged `data/app.db` used to
  make the Diagnostics page return HTTP 500 (the exact case it exists to explain)
  and could abort scheduler recovery during startup. Now every DB-backed check in
  `DiagnosticsService.collect` is guarded (`_guarded`) and degrades to a friendly
  `error` row; the report's DB-backed sections fall back to safe empty values
  (`_safe`); `SystemService.database_check` reports a damaged file distinctly
  (via `_schema_readable`) with a concrete recovery step; and
  `Scheduler.start()` guards `_recover()`. The app now starts and explains.
- **Queue page labels** — `frontend/src/views/QueueView.vue` maps raw job kinds
  (`reaction.job`, `audience.scan`, `invite.batch`) and statuses to plain Russian.
- **Beginner polish** (from the prior maintenance session): a startup readiness
  wait (`core/startup.py`), in-UI help hints (`InfoHint`, `services/help_topics.py`,
  `/api/v1/help`), and a novice-mode setting.
- `docs/TROUBLESHOOTING.md` gained a damaged-database entry; `docs/ROADMAP.md`
  corrected stale Alembic/PHASE-2 claims; `docs/RELEASE_CHECKLIST.md` records the
  v1.0.3 results and a v1.0.4 section.
- Tests added: `tests/test_diagnostics.py` (degradation), `tests/test_scheduler.py`
  (recovery-failure resilience), `tests/test_startup_readiness.py`,
  `tests/test_help.py`.
- Verified: Docker image builds and runs (health, SPA, migrations, persistent
  volumes, graceful + SIGKILL restart all OK); `scripts/build_portable.sh`
  produced a clean v1.0.4 ZIP (no `.env`/`.db`/`.session`/`.gguf`; empty runtime
  dirs; `sha256sum -c` OK); the automated Release workflow attached the ZIP +
  `.sha256` to the GitHub Release.

## 2f. v1.0.5 — product slice (2026-10-04, released)

Product-slice release (D-064). No new phase. Makes the suite useful **without a
user (MTProto) account**, plus a first-run guide and a conservative updater. One
Alembic migration (`7cb72d22d35b`, autogenerate-drift clean) adds every new table.

- **Bot↔channel bindings + reaction capabilities** — `bot_channel_bindings` +
  `channel_capabilities` tables, repositories, `binding_service` /
  `capability_service`, `/api/v1/bindings*` + `/api/v1/capabilities/*`. The
  reaction planner intersects the profile emoji with the channel's confirmed set
  (`reaction_policy.intersect_reactions`), so it never schedules an unsupported
  reaction.
- **Invite campaigns (session-free)** — `invite_campaigns` / `invite_links` /
  `join_requests` + `campaign_service` + `/api/v1/campaigns*`, with conservative
  risk modes and Bot-API-only link actions.
- **Donor quality** — `donor_metrics` + `donor_heuristics` / `donor_service` +
  `/api/v1/donors*`; explainable bands, and the bot-share estimate stays `null`
  when member data is unavailable (never invented).
- **Backup delivery destinations** — `backup_destinations` +
  `destination_service` + `services/backup_backends/*` (local, Telegram, Google
  Drive, Яндекс.Диск) + `/api/v1/backup/destinations*`; credentials sealed, a
  local destination auto-created and non-deletable. Fixed delivery so the archive
  bytes (not raw DB bytes) reach every enabled destination.
- **Setup Wizard** — `promotion_progress` + `promotion_service` +
  `/api/v1/promotion*`; resumable, preset-driven, reflects real state, session
  steps become `optional` without a session.
- **Conservative auto-update** — `update_state` + `update_service` +
  `core/versioning` + `/api/v1/update*`; off by default, checks GitHub releases
  and stages a SHA-256-verified file, never auto-installs.
- **Diagnostics** — new subsystem rows (`bindings`, `capabilities`,
  `backup_destinations`) and redacted-report sections (`queue`, `bindings`,
  `capabilities`, `campaigns`, `donors`, `backup_destinations`, `update`).
- **Frontend (RU-first)** — new `CampaignsView.vue` (`/campaigns`), a
  "Бот и реакции" column in `ChannelsView.vue`, backup destinations in
  `BackupView.vue`, and the Setup Wizard + Update cards in `SystemView.vue`.
- **Ops** — `updates/` git-ignored and created by `scripts/build_portable.sh`.
- Tests: `tests/test_bindings_api.py`, `tests/test_campaigns_api.py`,
  `tests/test_product_api.py`, extended `tests/test_diagnostics.py`. Suite
  **491 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

## 2g. v1.1.0 — Account Hub, discovery, encoder, bot-only UX (2026-10-04, on develop)

Maintenance/minor release completing the requested vertical slice. No new phase;
every addition is opt-in and never bypasses Telegram limits. Migrations:
`20261004_2047_76d92fe3e70b` (proxy_profiles, donor_candidates,
user_sessions.proxy_id) and the posts.intent / restriction_count follow-ups.

- **Account Hub — local session import (D-070).** `services/session_import.py`
  defines one `SessionImportProvider` protocol with four providers: Telethon
  `.session` (SQLite header), `.session` + companion JSON (whitelisted keys
  `api_id`/`app_id`/`api_hash`/`app_hash`/`phone`/`dc_id`; secret keys never
  read), StringSession (written to `SESSIONS_DIR`, never echoed/logged) and
  Telegram Desktop TDATA (optional; honest `NOT AVAILABLE` without a reliable
  converter; source folder never modified/uploaded). API:
  `POST /sessions/import/detect`, `POST /sessions/import/artifact`,
  `GET /sessions/{id}/risk`. `SessionsView.vue` shows the "Центр аккаунтов
  (импорт)" panel, format/state, the sensitive-file warning and the "Риск
  ограничений" column.
- **Network routes (proxies, D-065).** `proxy_profiles` + `user_sessions.proxy_id`,
  `/api/v1/proxies*`; password sealed, honest `ok`/`error`/`timeout` check,
  explicit non-bypass notice everywhere.
- **Donor discovery (D-066).** `donor_candidates` +
  `providers/discovery_base.py` / `telegram_discovery.py` +
  `services/donor_discovery_service.py` + `/api/v1/discovery*` (search /
  candidates / compare / add / clear). Candidates are proposals only; a source is
  added solely by an explicit click. `SourcesView.vue` gained the "Автопоиск
  доноров" panel with comparison.
- **Lightweight encoder (D-067) + ruBERT backend (D-068).** `ai/encoder.py`
  (dependency-free hashing encoder + prototype classifier; `MODE_ENCODER`), the
  `EncoderBackend` protocol, and the optional `cointegrated/rubert-tiny2`
  embedding backend (lazy, CPU-only, unload-when-idle). `services/encoder_service.py`
  + `/api/v1/ai/encoder/{status,install,check,remove}` download only the official
  files, verify SHA-256, store in the gitignored `models/` and report an honest
  status; `AiView.vue` shows the "Мини-ИИ" install card.
- **Bot-only UX (D-069).** Analytics without an account (`account_connected` /
  `account_note`, "Режим без личного аккаунта"); adaptive wizard
  (`session_optional_note` / `session_risk_note`); intent → reaction narrowing
  (`services/reaction_intent.py`; the planner intersects profile ∩ intent ∩
  channel ∩ bot-compatible and skips with a reason).
- **Bots UX.** `BotsView.vue` explains the three bot kinds (what/why/can/cannot/
  add-to-channel) and shows an honest binding status (`Готов`/`Нужны права`/
  `Не подключён`/`Ошибка`/`Недоступен`) with "Подключить к каналу" + "Проверить".
- **Security.** `.gitignore` also excludes `tdata/`, `*.session.json`,
  `*.session_meta.json`; docs/SECURITY.md documents the import scope and proxy
  credential sealing; a cp775 mojibake corruption in `docs/API.md` was fixed.
- Tests: `test_session_import.py`, `test_proxy_api.py`, `test_proxy_service.py`,
  `test_discovery_api.py`, `test_donor_discovery.py`, `test_encoder.py`,
  `test_encoder_service.py`, `test_reaction_planner.py`; extended `test_ai_api.py`,
  `test_ai_classifier.py`, `test_session_service.py`, `test_diagnostics.py`.
  Suite **574 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

## 2h. v1.2.0 — Content Studio (2026-10-05, on develop)

Minor release: the **v1.2 content-studio foundation** vertical slice. No new
phase; nothing is published without an explicit owner action and no Telegram
limit is bypassed. Migration: `20261005_1200_c4a1f8b2e6d9` (content tables, all
additive with server defaults).

- **Models + repositories.** `db/models/content.py`: `ContentSource`,
  `ContentItem`, `MediaAsset`, `Publication`, `ButtonSet`, `CommentPlan` (+ enums
  `ContentSourceKind`, `ContentSourceStatus`, `RightsStatus`,
  `ContentItemStatus`, `PublicationStatus`). `db/repositories/content.py`: one
  repository per model with dedup lookups (source hash / source message id /
  content hash / media hash).
- **Content sources (D-071/D-074).** `providers/content_base.py` +
  `providers/content_sources.py`: `ContentSourceProvider` protocol and Telegram /
  RSS / Atom / manual providers. Telegram reads through the existing
  `SessionProvider` (no Telethon import here); a `noforwards` source stores only
  the link and is marked `protected`.
- **Posting (D-071/D-072).** `providers/posting_base.py` (`PostingProvider`:
  publish/delete/send_comment/capabilities) + `providers/posting.py`
  (`BotPostingProvider` over `TelegramBotProvider`; `UserPostingProvider` over
  `SessionProvider`). No direct aiogram/Telethon imports.
- **Services.** `services/content_cleaner.py` (deterministic, explainable,
  cancellable), `services/content_markup.py` (`validate_markup`,
  `validate_buttons`, `render_preview`), `services/content_service.py` (sources,
  grab, items, clean, rights + attribution, rewrite via the generative LLM only,
  moderation: blocked keywords + quiet hours, `release_held`, dashboard),
  `services/posting_service.py` (plan / schedule / calendar / buttons / publish
  with `uncertain` idempotency / retry / auto-delete / first comments / tick).
- **Scheduler (D-075).** `scheduler/handlers.py::_handle_posting` runs one
  bounded pass and re-schedules itself every `POSTING_TICK_SECONDS` (D-008 style);
  `main.py` seeds the first tick with `QueueService.ensure_periodic`.
- **API + UI.** `api/v1/content.py` + `api/schemas/content.py` expose
  `/api/v1/content/*`; `frontend/src/views/ContentStudioView.vue` (`/content`, nav
  «Content Studio») has four RU-first tabs (Обзор / Источники / Материалы /
  Календарь). Help topics `content_studio`, `content_source`, `content_rights`.
- Tests: `test_content_posting.py`, `test_content_posting_api.py`; extended
  `test_scheduler.py` (periodic tick + `ensure_periodic`), `test_migrations.py`
  (v1.2 tables added in place), `test_help.py`. Suite **611 passed**; `ruff`
  clean; `vue-tsc` + `npm run build` clean.

## 2i. v1.3.0 — Bot Factory + LAN Mesh (2026-10-05, released)

Minor release: the **Bot Factory** and the **optional LAN Mesh / offline control
plane** vertical slice (D-077…D-083). No new phase; Standalone (one computer)
stays the default; nothing registers Telegram accounts or bypasses Telegram
limits. Migration: `20261005_1600_d5b2e9c3f7a1` (bot-factory + mesh tables, all
additive).

- **Bot Factory (D-077/D-078).** `db/models/bot_factory.py` (`BotBatch`,
  `BotCandidate`), `db/repositories/bot_factory.py`, `services/bot_factory.py`
  (`BotFactoryService`: templates, deterministic `generate_name` /
  `generate_username` / `sanitize_prefix` / `validate_username`,
  `check_availability` — a real Telegram check per candidate username — native
  creation, adopt, bind, write-only tokens, dashboards). `api/v1/bot_factory.py`
  + `api/schemas/bot_factory.py` expose `/api/v1/bot-factory/*`; creation goes
  through the official owner-confirmed @BotFather flow and adoption/binding reuse
  the existing `BotService` + `BindingService` (one manager bot).
- **LAN Mesh / offline control plane (D-079…D-082).** `db/models/mesh.py`
  (`MeshNode`, `MeshPeer` — credential stored as a salted hash, `PairingCode`,
  `MeshLease` with a monotonic `fencing_token`), `db/repositories/mesh.py`, and
  the `mesh/` package (`identity`, `discovery`, `pairing`, `election`, `lease`,
  `capability`, `transport` — `MeshTransport` protocol + `HttpMeshTransport` +
  in-memory `RecordingTransport` — and `service`). `/api/v1/mesh/*`
  (status, discover, peers, pairing-code, pair, unpair, probe, elect, leases);
  the `mesh.tick` durable maintenance job (probe peers, re-elect, reclaim expired
  leases; a cheap no-op while disabled). `main.py` keeps the manager-bot runtime
  off when the node is not the coordinator (no double-polling, D-081).
- **Hardening (D-083).** Pairing never persists or returns anything derived from
  a secret (the peer `note` is a plain status string; the shared secret is never
  stored); `/api/v1/mesh/ping` authenticates the `X-Mesh-Secret` header
  (timing-safe) and rejects unauthenticated requests when a secret is configured.
- **UI + config.** `frontend/src/views/BotFactoryView.vue` (`/bot-factory`) and
  `MeshView.vue` (`/mesh`), RU-first, with help topics `bot_factory` /
  `lan_mesh`; `core/config.py` mesh settings (`mesh_enabled` off by default,
  `mesh_mode=standalone`).
- Tests: `test_bot_factory.py`, `test_bot_factory_api.py`, `test_mesh.py`,
  `test_mesh_api.py` (offline against the deterministic fakes, D-001). Suite
  **664 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.
- **Released:** reviewed PR #9 (`develop → main`, merge `7788125`), tag `v1.3.0`;
  the Release workflow created the GitHub Release and attached the Windows
  portable ZIP + `.sha256` (24.7 MB, checksum verified, artifact secret scan
  clean — D-060).

## 5. Next action

**v1.3.0 Bot Factory + LAN Mesh is released** (PR #9 `develop → main`, merge
`7788125`, tag `v1.3.0`; GitHub Release with the Windows portable ZIP +
`.sha256`, built by CI — D-060). `main == develop == 7788125`. No required next
phase.

`NEXT_TASK` returns to **MAINTENANCE / OPTIONAL EXTENSIONS**; the roadmap
(PHASE 0–11) is complete. Optional future work (only if the owner asks): a fully
automated @BotFather Mini App flow (D-054); short-lived signed Mini App tokens if
it is ever exposed beyond the owner (D-035); a reliable, permissively-licensed
TDATA converter adapter (D-070); or any feature the owner requests (record a
decision; keep the vertical-slice workflow).

### RC verification (2026-10-03) — done against a live server in offline mode

A full user journey was exercised end-to-end via HTTP (fake providers, real
scheduler, real SQLite): setup-wizard → add bots/health → session auth wizard →
audience source/scan → import users/tags → reaction profiles/rules/simulate →
ingest post + plan + execute → invite preview/create/confirm/run → **kill server →
restart (recovery)** → resume invite to completion → backup → graceful shutdown.
Also verified: SPA deep links and all 15 pages render RU-first with plain-language
help; `vue-tsc` + `npm run build` clean; `ruff` clean; hidden-member/FloodWait
limits surface as statuses (never bypassed); secrets/phone masked; git has no
tracked secrets.

**Bugs found and fixed during the RC pass:** D-044 (reaction policy on
execution), D-045 (invite stuck-task recovery), D-046 (sad-news default rule),
plus a Reactions-page status-text bug and a duplicate `backup_dir` config field.

**Known gaps (documented, not blocking):** Mini App @BotFather registration is a
deployment step (the one-click menu-button helper exists, D-054); the manager-bot
command loop runs only while the app is running (no webhook by default). Both are
intentional, not defects.

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
- Analytics is a read-only aggregate layer; plain-language summaries are owned by
  the backend, and per-day bucketing is portable (D-036).
- Charts are dependency-free inline SVG; the SPA stays the single frontend
  (D-037).
- Mini App auth verifies Telegram `initData` server-side and issues a signed
  `HttpOnly` cookie; it is the same SPA/API as the Web UI, off by default, and
  never requires a public server for local use (D-038).

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
- `main` was at the PHASE 3 commit (`f06ba53`) until PR #1 merged; it now points
  at the release merge commit `82c1059` (same as `develop`).
- **RC sync (2026-10-03):** PHASE 7–11 + polish + RC hardening pushed to
  `develop` (`fd53ad1`…`e65a374`; fast-forward, no force). `origin/develop` is
  now at `e65a374` (RC hardening). PR #1 retitled to **"Full roadmap (PHASE 0–11)
  + release-candidate hardening"** with a full body; still **open**, `merged:
  false` — **not merged** (awaiting owner confirmation).
- **Hardening sync (2026-10-03):** post-1.0 hardening (manager-bot runtime +
  notifications + permission probe) pushed to `develop` as a fast-forward
  (`ba30578`…`727b0f8`; no force). Functional commit `c0174a8`; `origin/develop`
  is now at `727b0f8`. PR #1 retitled to **"Full roadmap (PHASE 0–11) + RC &
  post-1.0 hardening"** with an updated body.
- **Release v1.0.0 (2026-10-03):** release-prep commits `b442e08` (build fix:
  keep `backend/app/static/.gitkeep` across Vite builds), `f53cadf` (memory/docs
  sync to actual state, new `docs/RELEASE_CHECKLIST.md`) and `6a45e0a`
  (AGENTS release section) pushed to `develop`. PR #1 was marked ready and
  **merged into `main`** with merge commit `82c1059` (no force, no history
  rewrite). `develop` fast-forwarded to `82c1059` (both branches 0 ahead / 0
  behind). Local stale `main` (`f06ba53`) fast-forwarded to `origin/main`.
  Annotated tag **`v1.0.0`** created on `82c1059` and pushed; **GitHub Release
  `v1.0.0`** published:
  https://github.com/Surimat/Telegram-Channel-Management-Suite/releases/tag/v1.0.0
- No history rewrite, no force push.
- Secret audit before push: `.env`, `data/*.db`, session files and portable
  runtimes are git-ignored and confirmed absent from the remote; the mutable
  runtime dirs (`sessions/`, `logs/`, `data/`, `backups/`, `exports/`) contain
  only `.gitkeep` on the remote. The PHASE 5–6 diff contained no real tokens,
  api_hash values, session strings, passwords or exported PII (only code
  parameter names such as `api_hash`).
- **Release v1.3.0 (2026-10-05):** the v1.3.0 Bot Factory + LAN Mesh work was
  committed on `develop` (`548f309`), pushed (fast-forward, no force), and merged
  into `main` via reviewed **PR #9** (`develop → main`, merge `7788125`). Annotated
  tag **`v1.3.0`** created on `7788125` and pushed; the **Release** workflow
  verified the code and built the Windows portable ZIP, then created the **GitHub
  Release `v1.3.0`** and attached the ZIP + `.sha256` (24.7 MB; checksum verified,
  artifact secret scan clean — D-060). `develop` fast-forwarded to `7788125`, so
  `main == develop == 7788125`. No history rewrite, no force push; the
  `v1.0.0`–`v1.2.0` tags are untouched (D-050).
