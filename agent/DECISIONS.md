# DECISIONS — Telegram Channel Management Suite

Architecture Decision Records (ADR-lite). Each entry: what, why, and whether it
is **locked** (must not be broken without a new decision).

Format: `D-<n>` — date — title — status.

---

## D-001 — 2026-10-03 — Provider/adapter abstraction for Telegram — LOCKED

**Decision:** All Telegram access goes through abstract provider interfaces
(`TelegramBotProvider`, `TelegramUserProvider`, `SessionProvider`,
`AudienceProvider`, `ReactionProvider`) with real and fake implementations.

**Why:** Keeps Telegram library details out of domain logic; enables full
business-logic testing without a real account; allows swapping Telegram libraries
later without a rewrite. Mandated by the project's architectural principles.

**Consequence:** Domain services depend only on interfaces, resolved via a
provider registry.

---

## D-002 — 2026-10-03 — SQLite now, PostgreSQL later — LOCKED

**Decision:** Default storage is SQLite via `aiosqlite` + SQLAlchemy async.
PostgreSQL must be adoptable later **without rewriting business logic**.

**Why:** Portable/weak-Windows requirement forbids external DB services; but the
system must scale later.

**Consequence:** All DB access is behind repositories/services; no SQLite-specific
SQL in domain code; use portable SQLAlchemy constructs and Alembic migrations.

---

## D-003 — 2026-10-03 — One SPA and one API for Web UI + Mini App — LOCKED

**Decision:** A single Vue SPA and a single REST API serve both the local Web UI
and the Telegram Mini App. No second interface.

**Why:** Avoid duplicated UI/logic; the Mini App is just another client of the same
API. Explicit requirement.

**Consequence:** Responsive design from the start; Telegram `initData` auth is an
additive API concern (PHASE 9), not a separate app.

---

## D-004 — 2026-10-03 — One backend for all platforms — LOCKED

**Decision:** Windows portable, local Linux, and VPS/Docker all run the **same**
backend codebase. No "server version".

**Why:** Requirement; avoids divergence and double maintenance.

**Consequence:** Runtime differences are configuration/packaging only.

---

## D-005 — 2026-10-03 — AI is optional and disableable — LOCKED

**Decision:** A tiny GGUF classifier (llama.cpp) is an **optional** enhancement.
The Rules Engine is the primary classifier. AI can be fully disabled. The LLM
returns strict JSON `{category, tone, confidence}` and is **never** used to pick
emoji.

**Why:** Requirement; weak hardware; determinism for reactions.

**Consequence:** Classification flow: Rules first (fast path) → AI only when
confidence is insufficient → deterministic weighted emoji selection.

---

## D-006 — 2026-10-03 — No bypassing Telegram server limits — LOCKED

**Decision:** Never circumvent FloodWait, privacy, or admin restrictions. On
FloodWait, pause the affected account/queue and display the wait time. Privacy
errors are stored as the user's status.

**Why:** Requirement + correctness + account safety.

**Consequence:** No retry-until-success loops; all limits configurable; mass
operations require a confirmation summary.

---

## D-007 — 2026-10-03 — No heavy infrastructure in early phases — LOCKED (revisit later)

**Decision:** Do not introduce Redis, Kafka, Celery, PostgreSQL, Kubernetes in
Phases 0–1 (and only when a real need appears).

**Why:** Simplicity, portable runtime, weak hardware.

**Consequence:** Scheduler = APScheduler + asyncio; queue is DB-backed for
restart resilience.

---

## D-008 — 2026-10-03 — Durable DB-backed queue — LOCKED

**Decision:** Queues (reactions, invites) are stored as DB rows, not only in
memory. On startup, unfinished jobs are re-hydrated.

**Why:** Requirement: queues survive restart; app recovers unfinished work.

**Consequence:** Every job has `status, attempts, error, scheduled_at,
completed_at`; a recovery routine runs at startup.

---

## D-009 — 2026-10-03 — Configuration via `.env` + DB settings table — LOCKED

**Decision:** `.env` provides bootstrap/secrets; the UI edits runtime settings
stored in a `settings` table. UI settings override runtime behavior and persist.

**Why:** Requirement: configuration available through UI; no hardcoded values.

**Consequence:** Secrets live only in `.env`/OS store; non-secret settings live in
DB and are editable in the UI with descriptions and safe defaults.

---

## D-010 — 2026-10-03 — Secrets never committed or displayed — LOCKED

**Decision:** `.env`, tokens, API hash, session files, passwords, keys are never
committed and never printed to console/UI/logs/exceptions/API responses. A
logging redaction filter is mandatory.

**Why:** Security requirement.

**Consequence:** `SecretStr` for secrets; `.gitignore` enforcement; pre-commit
security checklist in `docs/SECURITY.md`.

---

## D-011 — 2026-10-03 — Documentation dirs `docs/` + `agent/` — LOCKED

**Decision:** All durable context lives in `docs/*` and `agent/*`, committed to
the repo. Critical context is never stored only in a conversation.

**Why:** Requirement: recover development after a new OpenHands chat.

**Consequence:** Every phase updates `agent/CURRENT_STATE.md`,
`agent/NEXT_TASK.md`, `agent/DECISIONS.md`, `agent/CHANGELOG.md`.

---

## D-012 — 2026-10-03 — Frontend builds to static; no Node.js in production — LOCKED

**Decision:** The SPA is built at packaging time into `backend/app/static/` and
served by FastAPI. Production/portable requires no Node.js.

**Why:** Portable Windows requirement; simple deployment.

**Consequence:** Node is a build-time (dev) dependency only.

---

## D-013 — 2026-10-03 — Python backend framework: FastAPI + aiogram + Telethon — LOCKED

**Decision:** FastAPI for the API, aiogram for Bot API, Telethon for MTProto.

**Why:** Stable, async, widely supported, aligned with the requirement's
"or equivalent stable library" phrasing.

**Consequence:** Providers wrap these libraries; swapping is possible via D-001.

---

## D-014 — 2026-10-03 — RU-first UI language

**Decision:** The UI is Russian-first, beginner-friendly, with plain-language
explanations, tooltips, and safe defaults.

**Why:** Target user profile; explicit requirement.

**Consequence:** i18n structure prepared for future languages but RU default.

---

## D-015 — 2026-10-03 — Minimal asyncio scheduler (no APScheduler) — LOCKED for now

**Decision:** The scheduler is a small hand-written asyncio worker loop over the
durable DB job queue (no APScheduler, no Celery).

**Why:** Keeps the dependency footprint tiny for the weak-Windows/portable
target, avoids a second scheduling abstraction, and the DB queue already
provides restart recovery. APScheduler was dropped from requirements in PHASE 1.

**Consequence:** Job handlers register by `kind` on the `Scheduler`. If complex
cron needs appear later, APScheduler can be layered *on top* of the same job
queue without changing domain logic. Revisit only when a real need appears.

---

## D-016 — 2026-10-03 — Uniform error envelope; no stack traces to clients — LOCKED

**Decision:** All API errors use `{"error": {"code", "message", "hint",
"details"}}` with a friendly RU message and an actionable hint. Unhandled
exceptions are logged server-side and returned as a generic message.

**Why:** Requirement: never show stack traces as primary UI information; be
beginner-friendly.

**Consequence:** New endpoints must raise `HTTPException` with a friendly
`detail`; the handler maps status → code. Technical detail stays in logs/events.
Endpoints wrap `BotServiceError` in `ApiError(status, message, hint)` so the
`hint` reaches the client envelope.

---

## D-017 — 2026-10-03 — Bot tokens sealed at rest (Fernet) — LOCKED

**Decision:** Bot tokens added through the app (including manager and managed
bots) are stored **encrypted** in the `bots.token_encrypted` column using Fernet
with a key derived from `APP_SECRET_KEY` (`core.security.seal_secret`/
`open_secret`). The manager bot may still be bootstrapped from `.env`
(`MANAGER_BOT_TOKEN`), which is also sealed into the DB on first startup.

**Why:** Requirement D-010 (secrets never committed/displayed) plus the need to
persist multiple bot tokens without keeping them in plaintext in SQLite.

**Consequence:** `cryptography` is a runtime dependency. Sealed values carry an
`enc:` prefix so a plaintext fallback stays readable. Changing `APP_SECRET_KEY`
invalidates stored tokens (clear error, no data corruption). API responses only
ever expose `has_token`, never the value.

---

## D-018 — 2026-10-03 — Managed bots via the official API only — LOCKED

**Decision:** Managed-bot support uses only documented Bot API methods:
`getManagedBotToken`, `replaceManagedBotToken`,
`getManagedBotAccessSettings`, `setManagedBotAccessSettings`, and the official
user link `https://t.me/newbot/<manager>/<username>?name=<name>`. The manager bot
must have "Bot Management Mode" enabled in @BotFather. We never invent methods
or bypass the user-confirmation flow.

**Why:** Correctness; the feature requires a user action (confirming bot
creation), so the app provides a clear workflow instead of hacking around it.
Telegram delivers `managed_bot` updates rather than offering a list endpoint.

**Consequence:** Managed-bot creation is a two-step UX: (1) open the generated
link, confirm in Telegram; (2) the app records the bot (from the update or by
Telegram ID) and fetches its token. `AiogramBotProvider` implements the four
methods; the fake provider returns deterministic values for tests.

---

## D-019 — 2026-10-03 — Provider selection via config; fake for offline/tests

**Decision:** `telegram_provider` (`auto` | `aiogram` | `fake`) and
`offline_mode` select the provider in `providers/registry.py`. `auto` uses the
real aiogram adapter unless `offline_mode` is set. Tests inject a fake provider
factory through `api/deps.get_provider_factory`.

**Why:** Lets the whole app and its tests run with no real credentials/network,
and gives users an offline/demo mode — without any change to domain code (D-001).

**Consequence:** Startup best-effort registers the manager bot from settings;
failures are logged as events (never fatal). `pytest` never needs real tokens.

---

## D-020 — 2026-10-03 — Rules Engine is deterministic; categories are data — LOCKED

**Decision:** The Rules Engine classifies a post to one of the fixed categories
(`donation`, `news`, `funny`, `sad`, `angry`, `cute`, `support`,
`announcement`, `neutral`) using **deterministic** matching on keywords, phrases
and (optional) regexes, plus exclusions, per-rule `min_confidence`, priority and
an optional `manual_override` (which always wins). Rules live in the
`reaction_rules` table and are editable in the Web UI — no code change needed.
`default_rule_specs()` seeds a working RU+EN rule set once; if the table is empty
the engine still falls back to those defaults so classification always works.

**Why:** Predictable, testable, and offline-friendly; beginners get a functioning
classifier out of the box while power users can edit everything (project
principle: configuration via UI).

**Consequence:** Classification confidence is a transparent score (matched terms
vs. total), not a probability from a model. The LLM (PHASE 7) is a *fallback*
classifier only, never the primary path (D-005).

---

## D-021 — 2026-10-03 — Reaction planner is pure with an injectable RNG — LOCKED

**Decision:** `ReactionPlanner` is a pure function of `(bots, PlanParams,
RuleMatch, base_time, rng)` returning immutable steps. Randomness (participation
gate, skip gate, weighted emoji choice, delay within the window) is drawn from a
`random.Random` injected by the caller (`ReactionService._rng_for(seed)`).

**Why:** Makes scheduling reproducible for preview/simulation and tests with a
fixed seed, while remaining unpredictable in production. Enables the "simulation"
feature required by PHASE 3 without contacting Telegram.

**Consequence:** Emoji are chosen by weighted deterministic logic, never by an
LLM (D-005). One bot places at most one reaction per message; `max_bots_per_post`
caps participation. Delay presets (`early`/`normal`/`spread`) rescale the
`delay_min`–`delay_max` window deterministically.

---

## D-022 — 2026-10-03 — Reaction profiles are named, with one default — LOCKED

**Decision:** `ReactionProfile` is a named, persisted configuration
(`allowed_emoji`, `emoji_weights`, `participation_probability`,
`skip_probability`, `delay_min`/`delay_max`, `delay_preset`,
`max_bots_per_post`). Exactly one profile is `is_default`; setting a new default
clears the old one atomically. The Reaction Manager as a whole has a separate
global switch (the default profile's `enabled` flag).

**Why:** Users want named presets (e.g. "Осторожный", "Активный") they can switch
between and preview without editing numbers each time.

**Consequence:** Preview/simulation is forgiving: it resolves a usable profile
(explicit id → active → default → any → create default) even if it is currently
disabled, because a preview never contacts Telegram.

---

## D-023 — 2026-10-03 — User accounts use lazy, per-operation MTProto connections — LOCKED

**Decision:** The Session Manager does not keep long-lived MTProto clients. The
`SessionProvider` abstraction (`providers/session_base.py`) exposes async
operations (`send_code`, `sign_in`, `sign_in_password`, `get_me`, `health`,
`export_session`, `aclose`). The Telethon implementation
(`providers/telethon_session.py` — the only module that imports Telethon) builds a
client, connects, runs one operation and disconnects inside each call.

**Why:** Keeps idle resource use minimal on weak Windows machines and the future
portable runtime, avoids background reconnection loops, and keeps the surface that
must handle Telegram exceptions tiny and testable.

**Consequence:** All business logic is provider-agnostic and covered by
`FakeSessionProvider` (tests/offline mode). Real credentials and network are never
needed by `pytest`. Monitoring, if ever needed, is done by periodic `health()`
calls (scheduler), not by holding connections.

---

## D-024 — 2026-10-03 — The auth wizard is a durable, resumable state machine — LOCKED

**Decision:** Adding an account persists an intermediate `UserSession` row with an
`auth_step` (`idle` → `code` → `password` → `done`) and the Telegram
`phone_code_hash`. Each HTTP request advances the wizard by one step. On startup,
`SessionService.recover()` resets any account left in `code`/`password` back to
`auth_required`/`idle` so an interrupted or crashed flow can be retried from the UI
instead of getting stuck.

**Why:** The multi-step flow spans several requests and the app may be restarted
between them. Matches the project rule that state survives restarts and that a new
agent/owner can recover from repo + DB alone.

**Consequence:** The wizard is idempotent to restart and needs no in-memory session
store. A stale `phone_code_hash` surfaces as a friendly "code expired" error,
prompting a fresh `start`.

---

## D-025 — 2026-10-03 — Account secrets are sealed; the API exposes only presence — LOCKED

**Decision:** The `api_hash` and the full phone number are stored **sealed**
(Fernet, via `core.security`, same mechanism as the bot token) in
`api_hash_encrypted` / `phone_encrypted`. Only `phone_masked` (e.g.
`+7999***4567`) and the non-secret `api_id` are stored in plaintext. The session
file is referenced by a UUID basename (`session_ref`) resolved against the
configured `sessions/` directory; its contents are never read, returned or logged.
API responses expose `has_session`, `has_api_hash` and `session_file_exists`
booleans instead of any value.

**Why:** Satisfies the hard project security rule (never leak secrets in UI, logs,
errors or API responses) while still letting the UI show meaningful state.

**Consequence:** The api_hash never leaves the service layer except as a sealed
string passed straight into the provider. Losing/changing `APP_SECRET_KEY` makes
sealed values unreadable — surfaced as a friendly "add the account again" error,
never a stack trace.

---

## D-026 — 2026-10-03 — Audience parsing goes through `AudienceProvider` over the session provider — LOCKED

**Decision:** PHASE 5 introduces `AudienceProvider` (`providers/audience_base.py`)
with `resolve_entity` and `iter_participant_pages`. The real implementation
(`SessionAudienceProvider`) is a thin adapter that delegates to the PHASE 4
`SessionProvider`, so there is still exactly one place that talks MTProto
(Telethon) and the audience code never imports Telethon.
`registry.build_audience_provider` selects the real adapter or the pure
`FakeAudienceProvider` from config (`offline_mode` / `provider=fake`).

**Why:** Keeps the D-001 rule (Telegram details stay behind interfaces), keeps
tests/offline mode account-free, and matches the requirement that a partial
library swap is a config/DI concern.

**Consequence:** Scans are consumed one bounded `ParticipantPage` at a time and
the member list is never fully buffered in memory. Deterministic failure
injection (FloodWait/privacy/admin) is possible in tests via `FakeAudienceScenario`.

---

## D-027 — 2026-10-03 — Audiences are scanned in restart-safe chunks with honest completeness — LOCKED

**Decision:** A scan is a durable `job_queue` job (`audience.scan`) driven one
chunk at a time, committing `scanned_offset` and counters after each chunk so
progress survives a crash. Pause/resume/cancel are explicit source states, and
`AudienceService.recover()` resets scans interrupted mid-flight to `paused` on
startup. Completeness is reported honestly as `complete`, `partial` (Telegram
returned only part of the list), `no_access` (list hidden from this account),
`failed` or `unknown`, each with a plain-language explanation. FloodWait pauses
the scan and shows the wait time; it is never bypassed (D-006).

**Why:** The target machine is weak and the app must survive restarts; the owner
must never be told a partial list is complete, and server limits must be
respected.

**Consequence:** Results are produced incrementally during a long scan and the UI
has a truthful `scan_status`/`completeness` to display.

---

## D-028 — 2026-10-03 — Dedup by `telegram_user_id`; membership is many-to-many — LOCKED

**Decision:** `audience_users` is unique on `telegram_user_id` so a person found
in several sources is stored once. Membership in a source is modelled by the
`source_user_links` join table (unique per `(source_id, user_id)`), which also
records `discovery_method` and timestamps.

**Why:** Prevents duplicate rows and lets one person belong to many sources
without corrupting filters/statistics; mirrors normal relational modelling
(D-002).

**Consequence:** Source statistics use the link table; deleting a source removes
its links (cascade) but not the global user unless explicitly purged. Adding a
new DB port (PostgreSQL) requires no business-logic change.

---

## D-029 — 2026-10-03 — Audience PII is masked; exports are local and PII-off by default — LOCKED

**Decision:** The audience subsystem stores only `phone_masked` (never a full
phone number). CSV/JSON export writes to the local, gitignored `exports/`
directory (never automatically uploaded/sent), excludes PII columns by default,
and requires the `AUDIENCE_STORE_PII` setting to include them. API responses and
event logs never contain secrets, session strings or raw phones.

**Why:** Satisfies the hard security rule while still allowing legitimate
owner-controlled exports.

**Consequence:** `tests/test_audience_security.py` asserts no secret/PII leaks in
responses, exports and events, and that error messages stay human-readable.

---

## D-030 — 2026-10-03 — Invites require confirmation and run as bounded durable batches — LOCKED

**Decision:** An invite run is created as a `draft` `InviteJob`; it can only start
via `POST /confirm`, which records `confirmed_at` server-side (the mandatory
confirmation cannot be skipped by calling the API directly). Execution is a durable
queue job that processes one configurable batch per scheduler tick and re-schedules
itself at the next due time, committing after every batch. The planner spaces tasks
per account (`INVITE_DELAY_MIN/MAX`, randomized); FloodWait pauses the whole run and
records `wait_until`; privacy/admin restrictions become per-user non-retryable
statuses. On restart a running job is paused, never resumed silently.

**Why:** Mass invites must never happen in one burst, must never be resumable
without the owner's knowledge, and must respect Telegram server limits
unconditionally (D-006). Bounded batches keep memory/CPU low on a weak Windows PC
and make the run restart-safe (D-008).

**Consequence:** Per-account and per-user statuses are queryable through the API/UI;
`retry_failed` only re-queues technically retryable failures (generic provider
errors / FloodWait), never privacy or admin restrictions.


---

## D-031 — 2026-10-03 — Tiny AI is an optional adapter behind a `Classifier` Protocol — LOCKED

**Decision:** The AI layer lives in `backend/app/ai/` and exposes one tiny
interface: `Classifier.classify(text, context) -> ClassificationResult`
(`category`, `tone`, `confidence`, `source`). Implementations are
`RulesClassifier` (wraps the PHASE 3 Rules Engine), `LlmClassifier` (a GGUF model
via the optional `llama_cpp` runtime) and `FakeClassifier` (deterministic, for
tests/offline). `RoutingClassifier` composes rules + AI by policy. Telegram and
FastAPI are never imported here; the Reaction Manager depends only on the
`Classifier` concept, never on a runtime or model.

**Why:** Keeps Telegram/LLM implementation details out of the business logic
(D-001/D-005) and lets the classifier be swapped or removed without touching the
reaction pipeline.

**Consequence:** Adding another backend (a different GGUF runtime, a remote API
classifier, an embeddings classifier) is a registry change in
`backend/app/ai/backends/__init__.py`, nothing else.

---

## D-032 — 2026-10-03 — Rules-first routing; AI is consulted only when rules are unsure — LOCKED

**Decision:** The default mode is `auto`: the deterministic Rules Engine runs
first; if its confidence is `>= ai_rules_threshold` (default 0.55) the AI is not
consulted at all. Only when rules are unsure does the tiny LLM run; its result is
accepted only if confidence is `>= ai_confidence_threshold` (default 0.6). Any AI
failure (disabled, missing runtime/model, timeout, invalid JSON) degrades to the
rules/neutral result and records an event — the reaction pipeline is never
blocked. `rules` and `ai` modes exist for explicit control/testing.

**Why:** The Rules Engine stays the deterministic, predictable default; AI is
additive-only, which matters on weak Windows PCs where a model may be slow or
absent.

**Consequence:** `RoutingOutcome` records `ai_attempted`/`ai_used`/`fallback_used`
and the `source` (`rules`/`llm`/`manual`/`fallback`) so the UI and simulation can
explain exactly which classifier won.

---

## D-033 — 2026-10-03 — AI output is strictly validated JSON; emoji are never chosen by the LLM — LOCKED

**Decision:** The model is asked for exactly `{"category", "tone", "confidence"}`.
`parse_classification` tolerates framing (markdown fences, stray prose) but is
strict about values: an unknown category/tone, a non-numeric/boolean/out-of-range
confidence, or invalid JSON raises `InvalidModelOutputError` and triggers the
fallback. Emoji selection remains fully deterministic (weights/RNG) in the
Reaction Planner (D-021) and is never delegated to the model.

**Why:** Models are unreliable narrators; a strict contract keeps classification
safe and keeps reaction selection reproducible.

**Consequence:** The AI can only ever pick from the fixed category vocabulary;
it can never emit an emoji, a free-text action or an out-of-vocabulary category.

---

## D-034 — 2026-10-03 — AI configuration is UI-editable and DB-overridable, with plain-language help — LOCKED

**Decision:** AI settings (`ai_enabled`, backend, model path, threads, context,
temperature, max tokens, timeout, keep-loaded, both thresholds, history limit)
have env defaults in `Settings` but are read through `AiService.effective()`,
which lets DB-stored settings override env. Every setting ships plain-language
help (`what_it_does`, `why`, `large_value_effect`, `safe_default`) from
`ai_help.py`, so the Web UI never hardcodes explanations. The model path must end
in `.gguf`; models are user-provided runtime assets, never committed and never
auto-downloaded. `offline_mode` selects the deterministic `fake` backend.

**Why:** Satisfies "configuration available via the UI" (brief principle 6) and
the beginner-friendly requirement without duplicating copy in the frontend.

**Consequence:** Tests and offline runs exercise the real pipeline through the
`fake` backend; switching to a real model is a path/backend setting, not a code
change.

---

## D-036 — 2026-10-03 — Analytics is a read-only aggregate layer with plain-language summaries — LOCKED

**Decision:** PHASE 8 analytics is implemented as a read-only repository
(`repositories/analytics.py`) plus a service (`services/analytics_service.py`)
that only aggregates data the suite already stores (posts, reaction jobs,
audience sources/users/links, invite tasks). It has no Telegram imports and no
write path. Per-day series are bucketed in Python from a bounded time window
instead of using database-specific date functions, keeping the queries portable
for a future PostgreSQL move (D-002).

**Why:** The brief demands that the Dashboard "explain numbers, not just show
them". Putting the plain-language `summary` in the backend keeps one source of
truth for both the Web UI and the Mini App (D-003) and avoids duplicating copy in
the frontend.

**Consequence:** Adding a new metric means adding a repository query + a service
key; the UI stays a thin renderer. The response carries only aggregate counts —
never secrets or per-person PII (D-010/D-029).

---

## D-037 — 2026-10-03 — Charts are dependency-free inline SVG — LOCKED

**Decision:** The Analytics/Dashboard charts use two small Vue components
(`Sparkline.vue`, `BarList.vue`) that render inline SVG/CSS with no charting
library. The SPA remains the single frontend (D-003) and still builds to static
files served by FastAPI.

**Why:** Keeps the portable Windows runtime and low-end machines light (no extra
JS bundle weight) and avoids a heavyweight dependency for simple line/bar charts.

**Consequence:** Only simple line and horizontal-bar charts are supported by
design; richer charting would be a deliberate later decision.

---

## D-038 — 2026-10-03 — Mini App auth verifies `initData` server-side; no second app — LOCKED

**Decision:** The Telegram Mini App reuses the same SPA and the same API (D-003).
Identity comes only from Telegram `initData`, verified **server-side** with
`HMAC_SHA256(bot_token, "WebAppData")` over the sorted key/value pairs, a
constant-time compare, and an `auth_date` freshness check
(`MINIAPP_INITDATA_MAX_AGE`). On success the server sets a signed `HttpOnly`
session cookie (`tcms_miniapp`) whose HMAC key is derived from `APP_SECRET_KEY`
(no JWT dependency). When `MANAGER_BOT_ADMIN_IDS` is set, only those Telegram ids
may sign in. The feature is off by default and never requires a public server for
the local Web UI.

**Why:** Telegram's signed `initData` is the only trustworthy identity signal;
client-supplied ids must never be trusted. Reusing the SPA avoids a second
codebase (D-003). A cookie + derived-key HMAC keeps the portable runtime
dependency-free and consistent with the existing crypto (`derive_key`).

**Consequence:** All Mini App business calls use the same endpoints as the Web UI;
only `/api/v1/miniapp/*` is new. The manager bot token and raw `initData` are
never logged, stored, or returned (D-010). The Telegram WebApp SDK is loaded from
`telegram.org` in `index.html` and is inert outside Telegram.

---

## D-039 — 2026-10-03 — Backups exclude sessions by default; config transfer never moves secrets — LOCKED

**Decision:** A backup is a single `.tcmsbak` zip holding the SQLite database plus
a `manifest.json`. MTProto session files are **not** included unless the operator
explicitly opts in (`backup_include_sessions` / `include_sessions=true`), and the
manifest records whether they were. Restoring always writes a safety backup of
the current state first. Configuration export/import (`/api/v1/backup/config/*`)
touches only `settings`, `reaction_profiles` and `reaction_rules`; the `bots` and
`user_sessions` tables (sealed tokens, session references) are deliberately
excluded and reported as such in `/backup/info`.

**Why:** Session files grant full account access (D-010 / security policy) and a
casual "make a backup" must never silently duplicate them. Config transfer should
let an owner move rules between installations without shipping credentials. A
safety backup makes a mistaken restore recoverable.

**Consequence:** Backups remain portable and reviewable. Restoring a backup that
included sessions only overwrites session files if the archive contains them.
Paths are validated against traversal; no token/hash/phone/session content ever
appears in an API response or log line.

---

## D-040 — 2026-10-03 — Portable layout decouples code location from data location — LOCKED

**Decision:** The portable distribution keeps application code under `app/` and
mutable state (`data/`, `sessions/`, `backups/`, `logs/`, `exports/`, `models/`)
at the distribution root, selected by `TCMS_ROOT`. `run.bat` sets
`TCMS_ROOT` (root) and `PYTHONPATH` (root\app) and launches
`python -m backend.app.main`; the SPA is served from the package-relative
`backend/app/static` (`paths.static_dir()` now resolves from `__file__`, not the
project root).

**Why:** Mutable data must be predictable and copyable with the folder, while the
code tree may be nested. Resolving `static_dir()` package-relative is correct in
every layout (dev, Docker, portable) and removes an accidental coupling to
`project_root()`. No second backend is created for portable mode (D-004).

**Consequence:** `scripts/build_portable.sh` stages the tree; a Windows user only
adds the Python embeddable package to `runtime/`. The smoke test proves startup +
graceful shutdown with `TCMS_ROOT` in a temp dir.

---

## D-041 — 2026-10-03 — One image for VPS; TLS terminated by an optional proxy overlay — LOCKED

**Decision:** The VPS deployment uses the *same* backend and codebase as
local/portable (D-004), packaged as a single multi-stage image
(`docker/Dockerfile`: Node builds the SPA → `python:3.12-slim` runtime, non-root
uid 10001, no Node at runtime). `docker/docker-compose.yml` runs one `app`
service with an optional `.env`, bind-mounted mutable state, a `/health`
healthcheck, `restart: unless-stopped`, and publishes only `127.0.0.1:8000`.
HTTPS is an opt-in overlay (`docker/docker-compose.proxy.yml` + `docker/Caddyfile`)
where Caddy obtains/renews Let's Encrypt certificates and proxies to `app:8000`.

**Why:** The brief requires VPS deployment of the same architecture with no
separate "server version", and forbids heavy infrastructure. Keeping TLS at the
edge (Caddy/nginx/Traefik) keeps the app dependency-free and the local Web UI
still needs no public server. Binding the app to localhost by default means an
unconfigured server is not accidentally exposed.

**Consequence:** Production config is environment-driven only (`APP_ENV`,
`APP_HOST`, `APP_SECRET_KEY`, `DATABASE_URL`, `MINIAPP_PUBLIC_URL`). `.env`,
sessions, data and logs stay out of the image via `.dockerignore`. Verified by
building the image and running the container (health, SPA, backup API).

---

## D-042 — 2026-10-03 — Audience/Sources UI is frontend-only over the PHASE 5 API — LOCKED

**Decision:** The dedicated Audience and Sources views are implemented purely in
the SPA (`SourcesView.vue`, `AudienceView.vue`) against the existing
`/api/v1/audience` endpoints. No backend endpoint, schema, or service is added or
changed. All scan/limit semantics stay in the service layer: the UI only presents
the `/scan/preview` summary and starts a scan after the owner confirms.

**Why:** The PHASE 5 API already exposes sources CRUD, scan lifecycle
(preview/start/progress/pause/resume/cancel), user list with search/filter/tags/
sort/pagination, tags, bulk status, and export/import. Adding a second backend
path would duplicate logic and risk drift. Keeping the UI thin preserves D-001
(Telegram details behind providers) and the "one API" rule (D-003).

**Consequence:** The two views reuse the shared typed client and the uniform API
error envelope; Telegram limits (FloodWait, hidden member lists) surface as
statuses with a suggested fix, never as bypass attempts. If a real gap is found
later, it is fixed in the service and covered by `tests/test_audience_api.py`.

---

