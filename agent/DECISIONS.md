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

**Update (2026-10-03):** runtime staging is now automated — see D-043.

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

## D-043 — 2026-10-03 — Portable runtime staging is automated, with an offline fallback — LOCKED

**Decision:** `scripts/fetch_embedded_python.sh` stages the official Windows
**embeddable** Python into `runtime/` during the portable build: it downloads the
`python-<ver>-embed-<arch>.zip` from python.org, extracts it, writes the matching
`pythonXY._pth` (adding `../app`, `site-packages`, `import site`), bootstraps pip
and installs `backend/requirements.txt` into `runtime/site-packages`.
`scripts/build_portable.sh` calls it by default.

**Why:** The portable promise is "unpack → run.bat → works" with nothing
installed (D-040). Requiring the owner to hand-download and unzip a runtime broke
that promise. Automating it is a small, self-contained script with no new
dependency. It is deliberately best-effort: `--dry-run` plans offline,
`SKIP_RUNTIME=1`/`--no-runtime` opts out, and on download failure the script
prints exact manual steps and the caller falls back — so restricted networks and
non-Windows hosts still produce a usable tree.

**Consequence:** Downloaded runtimes are build artifacts and are never committed
(the `dist/` output is gitignored). If the embedded `python.exe` cannot run on the
build host (e.g. Linux), dependencies are not installed there but the manual
command is printed for Windows. Covered by network-free tests in
`tests/test_portable_smoke.py`.

---

## D-044 — 2026-10-03 — RC hardening: execution uses the same reaction policy as simulation — LOCKED

**Decision:** `ReactionService.plan_post` builds the planner's `RuleMatch` from
the post's category **through the category reaction policy** (`_result_to_match`
/ `_policy_for_category`), exactly like `simulate`. A post executed for real can
no longer receive an emoji that the category forbids.

**Why:** `plan_post` previously constructed a `RuleMatch` without
`allowed/preferred/forbidden` reactions, so it fell back to the whole profile
emoji pool — a donation post could get 😍/🔥 even though the donation rule
forbids them (only simulation enforced the policy). That is a correctness bug in
the core feature. Emoji selection stays deterministic and rule-driven; AI still
never picks emoji (D-021/D-033).

**Consequence:** Execution and simulation now share one policy path. Covered by
`tests/test_reaction_service.py::test_planned_jobs_respect_category_forbidden_emoji`.

---

## D-045 — 2026-10-03 — Restart recovery un-sticks claimed invite tasks — LOCKED

**Decision:** On startup, `InviteService.recover()` first calls
`InviteTaskRepository.recover_stuck_running()`, which resets any `RUNNING` tasks
(claimed mid-batch by a crashed process) back to `PENDING`, then pauses the
interrupted jobs as before.

**Why:** `claim_batch` marks a batch `RUNNING`; if the process died mid-batch
those rows were never returned to the pending pool, so an explicit resume could
never finish the run — the tasks were stranded forever. Resetting them is the
only way a resumed bulk action can complete, while the job still stays paused
until the operator confirms (D-008 / D-030).

**Consequence:** After any crash, resume finishes the run instead of hanging.
Covered by
`tests/test_invite_service.py::test_recover_returns_stuck_running_tasks_to_pending`.

---

## D-046 — 2026-10-03 — Sad posts are never classified as celebratory news — LOCKED

**Decision:** The default `news` rule carries `exclusions` for sad vocabulary
(`грустн`, `печальн`, `траур`, `потеряли`, `умер`, `погиб`, `скорб`, …) so a
"грустная новость" classifies as `sad` rather than `news` (which would pick
🎉/🔥). The seed ships a working, safe policy for a beginner; all rules stay
UI-editable data.

**Why:** Live RC testing with the default rules gave a sad post 🎉🔥 — an
inappropriate reaction on a sensitive post, unacceptable for a channel owner out
of the box.

**Consequence:** Default rules are safer; covered by
`tests/test_rules_engine.py::test_default_rules_sad_news_is_not_celebratory`.

---

## D-047 — 2026-10-03 — Manager-bot runtime is a separate, optional, non-blocking loop — LOCKED

**Decision:** The manager bot is driven by a dedicated `ManagerBotRuntime` asyncio
task (short polling) rather than by the durable job scheduler. It is enabled by
`MANAGER_RUNTIME_ENABLED` (default on for normal installs, off in tests), backs
off exponentially when Telegram is unreachable, and is stopped cleanly on
shutdown. All Telegram access still goes through the provider abstraction (D-001).

**Why:** The manager bot is an interactive control/notification channel, not
durable work: it must never contend with the queue that runs audience scans,
reactions and invites (D-008). Keeping it a separate, best-effort loop means a
Telegram outage degrades notifications only — the local app, scheduler and UI keep
working, which is required for a weak/offline Windows machine.

**Consequence:** Startup/shutdown stay fast and never fail because of Telegram.
There is exactly one manager-bot loop per process; there is no second scheduler.

---

## D-048 — 2026-10-03 — Notifications ride a bounded, never-raising in-process bus; toggles live in `settings` — LOCKED

**Decision:** Notification routing uses a module-level `NotificationBus` (bounded
`asyncio.Queue`, default 500). `publish()` is non-blocking and swallows
`QueueFull`/unexpected errors (counting drops instead). Categories
(`system`, `telegram`, `reactions`, `audience`, `invites`, `ai`) are owner-
toggleable; toggles are stored as rows in the existing `settings` table, not a new
table.

**Why:** A notification is best-effort by definition; it must never be able to
break the operation that emitted it, and it must not add infrastructure. Reusing
`settings` keeps backup/export/import already complete for these values and keeps
the schema minimal (no-heavy-infra principle).

**Consequence:** Losing a notification is acceptable and observable (`dropped`);
losing an operation result never happens. No new dependency or table was added.

---

## D-049 — 2026-10-03 — Permission probe reports honest status, never bypasses limits — LOCKED

**Decision:** `PermissionService.check(account_id, target)` resolves the channel,
probes member visibility and invite rights through the `SessionProvider`, and
stores a `PermissionCheck`. It maps provider errors to explicit statuses
(`ok`, `partial`, `no_access`, `auth_required`, `admin_required`,
`privacy_restricted`, `flood_wait`, `error`). Errors already translated by the
provider are surfaced, not swallowed, and no limit is ever circumvented (D-006).

**Why:** The owner must know *before* an invite run whether it can work, and a
`FloodWait` must show a wait time, not be retried in a loop. A single honest
pre-flight check prevents launching a mass operation that would fail midway.

**Consequence:** The Sessions page and `/api/v1/permissions/*` show the true state
and a "how to fix" hint. Results never contain api_hash, phone or session content.

---


---

## D-050 — 2026-10-03 — v1.0.0 released from `develop`; version bumped afterward, tag immutable — LOCKED

**Decision:** Release `v1.0.0` is the `develop → main` **merge commit**
`82c1059`, tagged `v1.0.0` (annotated) with a GitHub Release. PR #1 was marked
ready (it had been a draft) and merged via the GitHub API; no force push, no
history rewrite. `develop` was fast-forwarded to `82c1059` and the stale local
`main` fast-forwarded to `origin/main`. After the release, `develop` may advance
(e.g. the application version string `0.1.0 -> 1.0.0`); the published tag is
**immutable** and `main` stays exactly at the release commit until the next PR.

**Why:** The tag must point at exactly the reviewed, merged code. Bumping the
version string before the merge would have made the image report `1.0.0` without
a reviewed release; doing it after keeps the release honest and the tag stable,
while still aligning the reported version with the release going forward.

**Consequence:** `origin/main` = `82c1059` (the released artifact reports
`0.1.0`, a cosmetic pre-merge value). `develop` head is `72a432d` and reports
`1.0.0`. The next `develop -> main` PR will make `main` report `1.0.0`. Fixed
build hygiene: Vite `emptyOutDir` no longer deletes the tracked
`backend/app/static/.gitkeep` (a `frontend/public/.gitkeep` is re-emitted).

---

## D-051 — 2026-10-03 — Versioned migrations at startup; one shared Channel Registry — LOCKED

**Decision:** (a) Startup applies **Alembic** versioned migrations instead of
`create_all`; the runner (`backend/app/db/migrate.py`) is guarded so a fresh
install, an existing `create_all` database (adopt + stamp) and a normal upgrade
all converge, with a pre-migration backup and transaction-per-migration. (b) The
suite keeps **one shared channel identity**: a `channels` table
(`Channel`, `ChannelKind`, `ChannelStatus`) is the single source for a channel's
reference/title/kind/verification/module toggles, exposed at `/api/v1/channels`.
Modules (reactions/audience/invites/analytics) reference a channel by `channel_id`
instead of each storing its own target string; the first channel becomes the
default and a default is always promoted when the current one is removed.

**Why:** `create_all` cannot evolve an installed schema and silently drifts from
the models; a real migration path is required before the schema grows. A single
channel registry removes duplicated, inconsistent target strings across modules
and lets the UI offer one channel picker everywhere, which is the RU-first,
low-friction experience the owner needs.

**Consequence:** Schema changes ship as migrations under `migrations/versions/`;
the baseline revision is regenerated (not shipped) until the next release, so
`channels` and `invite_jobs.channel_id` are part of the baseline. The invite
manager resolves its target from `channel_id` when a registry channel is chosen,
falling back to a manually typed target. Docker and the portable build copy
`alembic.ini` + `migrations/`.

---

## D-052 — 2026-10-03 — Migration adoption is baseline-aware; modules link to the registry — LOCKED

**Decision:** (a) The Alembic adoption path is **baseline-aware**: an existing
`create_all` database is stamped at the *baseline* revision (whose schema equals
the shipped `create_all` schema) and then upgraded through the delta migrations —
it is never stamped straight at head. `_schema_matches_baseline()` inspects the
live schema to decide, and `database_status` reports a pending upgrade instead of
"up to date" when a stamped database still lacks delta tables. (b) Modules link
to the shared Channel Registry by a **nullable, backfilled** `channel_id`/
`registry_channel_id` string column (empty string = "no registry link"), not by a
hard foreign key, so existing rows and manual (non-registry) targets keep working
while the UI offers the picker.

**Why:** A v1.0.0 install (built with `create_all`, no `channels` table) was
being stamped at *head* without running the registry migration, so the app
crashed on the missing `channels` table. Stamping at the baseline and upgrading
fixes that. The soft link keeps the migration SQLite-safe (a NOT NULL column
cannot be added to a populated table without a server default, and a server
default would show up as model/migration drift) and preserves backward
compatibility for rows created before the registry existed.

**Consequence:** Migration history is baseline (`0191baf5265f`) → registry delta
(`561f0631d045`) → registry links for posts/sources (`e3b5890e407e`) → permission
link (`6816b29afc76`). Tests cover the v1.0.0 → develop upgrade with existing rows
and the registry-link API paths (posts, sources, invites, permission probe). A
numeric Telegram chat id on a post remains the transport identity; the registry
link is the stable owner-selected identity.

---

## D-053 — 2026-10-03 — CI runs the real quality gates on `main` and `develop` — LOCKED

**Decision:** A GitHub Actions workflow (`.github/workflows/ci.yml`) runs two
independent jobs on every push and pull request targeting `main` or `develop`:
a **backend** job (`ruff check backend tests` then `pytest`, Python 3.12, pip
cache) and a **frontend** job (`npm ci` then `npm run build`, Node 20, npm
cache). The workflow is required to be green on the PR head before release
(added to `docs/RELEASE_CHECKLIST.md`).

**Why:** The suite has 413 tests, a strict lint config and a TypeScript SPA
build, but nothing enforced them on the remote — `main`/`develop` could silently
break for a contributor without the local toolchain. CI makes the local gates
authoritative on every change and is the minimum viable safety net for a
long-lived repo that must survive agent/session handoffs.

**Consequence:** No test/lint/build changes may be merged to `main` with a red
CI. CI is intentionally minimal (no Docker/portable jobs) to keep the free
runner fast and avoid requiring credentials; Docker and portable builds remain
documented manual gates. The workflow uses only official actions and the
already-committed lockfile.

---

## D-054 — 2026-10-03 — Mini App registration is a one-click, provider-backed owner action — LOCKED

**Decision:** Mini App deployment no longer requires the owner to talk to
@BotFather by hand. `POST /api/v1/miniapp/setup` validates a **public HTTPS**
URL, points the manager bot's chat menu button at it via a new
`TelegramBotProvider.set_menu_button(title, url)` method, and persists
`miniapp_public_url` + `miniapp_enabled` as UI-editable settings. The Settings
page exposes this as a "Мини-приложение Telegram" card. Validation and provider
failures return plain-RU `{ok, message, how_to_fix}` and are logged to the
event center.

**Why:** BotFather registration was the last manual, error-prone step in PHASE 9
and is easy to get wrong (HTTP vs HTTPS, missing public URL). Routing it through
the existing provider abstraction keeps Telegram details out of the service layer
(D-001) and lets the fake provider cover the whole flow in tests. It never
bypasses Telegram limits (D-049) — a rejected registration is surfaced honestly.

**Consequence:** `set_menu_button` is added to the provider protocol; providers
without a menu-button API may return `False`. HTTPS-only validation is enforced
in the service (Telegram will not open non-HTTPS Web Apps), so a plain local
`http://127.0.0.1` install still works but cannot be a Mini App target. The URL
is normalised (trailing slash trimmed) and stored as a non-secret setting; the
bot token is never read into the response or logs.

---

## D-055 — 2026-10-03 — Analytics can be scoped per registry channel — LOCKED

**Decision:** Every analytics view (`/api/v1/analytics/overview|content|reactions|audience`)
accepts an optional `channel_id` (a Channel Registry row id, D-051). Posts are
scoped by `posts.registry_channel_id`; reaction jobs are scoped by joining their
post; audience users by joining the sources linked to that channel; invite
outcomes by joining the invite job's `channel_id`. Omitting the parameter keeps
the original global aggregates exactly as before. The Analytics page exposes a
channel selector and defaults to the registry's default channel.

**Why:** The registry was wired into ingestion, sources, invites and the
permission probe, but analytics still summed every channel together — the last
gap in the "one shared channel identity" work. Scoping is read-only and purely
additive, so no existing behaviour or API contract changes for callers that omit
`channel_id`.

**Consequence:** `AnalyticsRepository` query methods take an optional
`channel_id`; `AnalyticsService.content/reactions/audience/overview` thread it
through; `AnalyticsOverviewOut` gained a `channel_id` field (defaults to `""`).
Audience scoping relies on sources having a `channel_id`, so unlinked sources are
only counted globally — acceptable for a single-owner install and honest about
what the data supports.

---

## D-056 — 2026-10-04 — Base `uvicorn` + a pinned Windows runtime lock — LOCKED

**Decision:** The runtime dependency list uses base `uvicorn` (not
`uvicorn[standard]`), and the portable build installs a **pinned** Windows wheel
set from `scripts/win-requirements.lock` (win_amd64 / CPython 3.12) rather than
resolving the loose ranges on the build host. `scripts/build_win_runtime.py`
downloads the official Windows *embeddable* CPython plus those wheels and extracts
them flat into `runtime/site-packages`; `pyaes` (Telethon's only sdist-only
dependency, pure Python) is extracted from its sdist so no compiler is needed.
The build is cross-platform — a Linux/macOS/Windows host produces the same
Windows runtime.

**Why:** `uvicorn[standard]` pulls uvloop/httptools/websockets, which the app
never uses (no WebSockets; the default asyncio loop is fine) and which made
cross-platform wheel resolution fail (`uvloop` is excluded on win32 by its
environment marker, so a `--platform win_amd64` download could not resolve the
extra). A pinned lock makes the shipped runtime reproducible and lets the
portable ZIP be built in CI on Linux. Keeping the base package also trims the
portable runtime and matches the "no dependencies without necessity" rule.

**Consequence:** `--reload` now requires `watchfiles` (documented in
`backend/app/main.py` and `docs/SETUP.md`); production never reloads, so this is
dev-only. `scripts/fetch_embedded_python.sh` remains for a host-driven build and
gained `--no-deps`. The portable ZIP name is
`Telegram-Channel-Management-Suite-Windows-Portable-<version>.zip`.

---

## D-057 — 2026-10-04 — Release target is `v1.0.1` (patch) — LOCKED

**Decision:** The post-1.0 work on `develop` is published as **v1.0.1** (the
release the owner asked for). The application version string stays at `1.0.1`
across `backend/app/__init__.py`, `pyproject.toml`, `frontend/package.json` and
`frontend/package-lock.json` (it was already `1.0.1` on `develop`, so no bump was
needed; the earlier drift concern was cosmetic). `v1.0.0` and its tag stay
immutable; the release is the `develop → main` merge commit, tagged `v1.0.1`,
with a GitHub Release whose portable ZIP is attached by
`.github/workflows/release.yml`.

**Why:** The owner explicitly targets `v1.0.1` for this release. `develop` already
carried the `1.0.1` version string, so the only inconsistency was documentation
(the changelog still said `1.0.0`); that is fixed here. D-050 (immutable published
tags, version set on `develop`) still holds. (An earlier draft of this decision
proposed `v1.1.0` on SemVer grounds; overridden by the explicit owner target.)

**Consequence:** `/health`, `/health/deep` and `/api/v1/system/*` report `1.0.1`
after the merge. The version is the single source of truth in
`backend/app/__init__.py`; `scripts/build_portable.sh` reads it for the ZIP name
(`…-Windows-Portable-1.0.1.zip`).

---

## D-058 — 2026-10-04 — Async fixtures: dispose the engine before resetting it

**Decision:** In `tests/conftest.py`, `_dispose_engine_between_tests` declares a
dependency on `_isolated_env` so pytest finalizes it *first* (dispose) and
`_isolated_env` *second* (reset). Tests that need a session use the
`session_scope()` context manager, never `async for session in get_session():
... break`.

**Why:** The autouse finalizers ran in the wrong order — `_isolated_env` reset
`_engine = None` before `_dispose_engine_between_tests` called
`dispose_engine()`, so the engine was never actually disposed. Open aiosqlite
connections then survived into a later test and were garbage-collected on a
closed event loop, intermittently failing with `GeneratorExit` /
`TypeError: object NoneType can not be used in an await expression`. Iterating
the FastAPI `get_session()` dependency with `break` leaks its async generator
the same way (never finalized in its own loop).

**Consequence:** The suite is deterministic: 427 passed across repeated runs,
no "Event loop is closed" noise. Any new test must use `session_scope()` (or
explicitly `aclose()` a `get_session()` generator) rather than `break`.

---

## D-059 — 2026-10-04 — v1.0.1 released; tag immutable, Release build fixed forward

**Decision:** `v1.0.1` is the `develop -> main` merge commit `d267cf6`, tagged
`v1.0.1` (annotated) with a GitHub Release. Per D-050 the tag is **immutable**,
so the Release-workflow path bug (`build_portable.sh` wrote the ZIP to a
non-existent `dist/TCMS/dist/...` for a relative output dir) is fixed **forward**
on `develop` and the portable ZIP is built locally and attached to the existing
`v1.0.1` release. `v1.0.1` is **not** moved or re-tagged. A future `v1.0.2`
would carry the fix in its own tag.

**Why:** Rewriting a published tag breaks reproducibility and the rule the
project already locked for `v1.0.0`; a broken *automation* path is not a reason
to invalidate the release commit. The released code is correct — only the CI
packaging step failed.

**Consequence:** `main` = `develop` = `d267cf6` (tag `v1.0.1`). The GitHub
Release `v1.0.1` carries the Windows portable ZIP + `.sha256` built from that
exact commit. The next release runs the now-fixed workflow cleanly.

---

## D-060 — 2026-10-04 — Release workflow creates the GitHub Release (no manual fallback)

**Decision:** `.github/workflows/release.yml` publishes the release itself. On a
`v*` tag the `portable` job now runs `gh release create <tag> --verify-tag
--notes-file …` when the release is missing, or `gh release upload --clobber`
when it already exists, then attaches `dist/*.zip` + `dist/*.sha256`. The
`v1.0.1` release was attached **manually** (see D-059) because the old workflow
only did `gh release upload`, which fails when no release exists yet.

**Why:** A tag push must produce a complete, reproducible release with no human
step ("push tag → GitHub Actions → ZIP + checksum → GitHub Release"). `gh release
upload` alone cannot satisfy that on a fresh tag. Using the workflow's own
`GITHUB_TOKEN` (`permissions: contents: write`) keeps it within repository
policy; `--verify-tag` guards against a missing tag.

**Consequence:** `v1.0.2` (and every later `v*` tag) is produced end-to-end by
CI. The release notes generated by the workflow state "AUTOMATED PORTABLE BUILD:
PASS". `v1.0.0`/`v1.0.1` remain immutable (D-050).

---

## D-061 — 2026-10-04 — Diagnostics is read-only + redacted; maintenance is non-destructive

**Decision:** The **Diagnostics** feature (`backend/app/services/diagnostics_service.py`,
`backend/app/api/v1/diagnostics.py`, `frontend/src/views/DiagnosticsView.vue`) is
the owner's single place to see system state. It has three parts:

1. **Status aggregation** — one row per subsystem (application, database incl.
   migration state/revision, Telegram API, manager bot, managed bots, user
   sessions, channels, audience, reactions, invites, AI, scheduler/queue, storage,
   portable runtime), each with `ok | warning | error | not_configured` plus a
   plain-language "what it means" and "what to do". Reuses `SystemService` checks
   where they exist and adds the missing aggregations.
2. **Redacted report** — `GET /api/v1/diagnostics/report?format=json|txt|zip`
   builds a payload from the aggregation plus versions, OS/runtime, enabled
   modules, bot/session/channel statuses (status only — never contents), queue
   state, AI state, dependency versions, last errors and safe path *names*. Every
   payload passes through `core/redaction.py` (`redact_and_verify`) and is
   re-scanned; **if the scan is not clean, no file is produced**. It never
   contains bot tokens, api_hash/api_id, session data, phone numbers, passwords,
   database contents, audience records or private logs. The response carries
   `X-Diagnostics-Redacted: true` and the UI states the report is cleared of
   secrets.
3. **Safe maintenance actions** — `POST /api/v1/diagnostics/actions/{key}` for
   `restart_scheduler`, `recheck_telegram`, `recheck_channels` and `cleanup_jobs`.
   None deletes user data. `cleanup_jobs` (reset jobs stuck in RUNNING, cancel
   long-overdue pending jobs) requires confirmation and is hidden while the
   scheduler is running.

**Why:** The primary product goal is that a non-technical owner can download the
portable build, open the Web UI and understand the system state without reading
Python logs or the Telegram API. A redacted report lets them hand a developer
everything needed without leaking secrets. Restricting maintenance to
non-destructive operations (and reusing the same job handlers via
`scheduler/handlers.py` for a clean scheduler restart) keeps the "never delete
user data automatically" rule.

**Consequence:** The durable-queue handler registration moved from `main.py` into
`backend/app/scheduler/handlers.py::register_handlers` so the scheduler can be
restarted from the UI with identical wiring. Diagnostics is a read-only view plus
explicit safe actions; it never mutates Telegram state except through the
existing, limit-respecting services. New tests live in `tests/test_diagnostics.py`.

---

## D-062 — 2026-10-04 — Diagnostics and startup degrade gracefully; never crash on a bad DB — LOCKED

**Decision:** The application must start and the Diagnostics page must render even
when the database is damaged, unreadable or mid-migration. A failing check is
reported as a friendly `error` row with a "what to do" step; a failing report
section falls back to a safe empty value. Startup must not be aborted by a
database problem.

**Implementation:**
1. `DiagnosticsService.collect` runs every DB-backed check through `_guarded`, so
   one failure yields an `error` row (friendly title/meaning/how-to-fix) instead
   of an HTTP 500. `DiagnosticsService.build_report_payload` uses `_safe` so a
   failing section becomes `[]`/`{}` rather than aborting the report.
2. `SystemService.database_check` distinguishes a damaged/unreadable DB file
   (schema probe `_schema_readable` fails) from a benign "version unknown" case,
   and returns an `error` row with a concrete recovery step.
3. `Scheduler.start()` wraps `_recover()` in a guard; the loop already tolerates
   per-tick errors, so a DB problem cannot crash application startup.

**Why:** The whole point of the Diagnostics page is to be the place a
non-technical owner is sent when something is wrong. A page that 500s precisely
when the database is corrupt defeats its purpose, and a startup crash leaves the
user with a traceback instead of an explanation.

**Consequence:** Diagnostics is a best-effort, read-only view; a row may read
"error" while the rest still renders. This does not weaken the redaction rule
(D-061) — the degraded rows and report contain no secrets. New regression tests:
`tests/test_diagnostics.py::test_collect_degrades_when_a_check_fails`,
`::test_collect_degrades_when_database_check_raises`,
`::test_report_payload_survives_db_failure`, and
`tests/test_scheduler.py::test_scheduler_start_survives_recovery_failure`.

---

## D-063 — 2026-10-04 — Docs/memory are verified against code each maintenance pass

**Decision:** Documentation and persistent memory (`README.md`, `docs/*.md`,
`agent/*.md`) are treated as claims to verify against the actual code, not as
free-form prose. During a maintenance pass the API surface, routes, setup checks,
page inventory and version strings are diffed against the source; every mismatch
is fixed in the same commit.

**Why:** A factual audit of v1.0.4 found real drift that would mislead a user or a
new agent — `docs/API.md` documented `/api/v1/system/backups*` and
`/api/v1/system/config/*` paths that do not exist, omitted `/api/v1/help/*`, and
carried a duplicate Invites table with a non-existent `/start` endpoint;
`docs/UI.md` was missing the `/diagnostics` and `/backup` routes; `docs/SETUP.md`
listed Setup Wizard checks that do not exist; `agent/CURRENT_STATE.md` cited a
stale `DECISIONS.md` range. The repository is the source of truth, so a doc that
contradicts the code is a bug.

**Consequence:** Each release/maintenance pass re-checks docs against code (the
route table vs `backend/app/api/v1/*`, the router vs `docs/UI.md`, the setup
checks vs `GET /api/v1/system/setup`, the version string across
`backend/app/__init__.py`, `pyproject.toml` and `frontend/package.json`). No
product behaviour changes.


---

## D-064 — 2026-10-04 — Product slice: bot-only bindings, campaigns, destinations, wizard, update — LOCKED

**Decision:** Ship a vertical product slice that makes the suite useful **without
a user (MTProto) account**, plus a first-run guide and a conservative updater.
Everything reuses the existing provider abstraction, sealed-secret storage and
limit-respecting services; nothing bypasses Telegram.

**Scope (all additive, no new phase):**
1. **Bot↔channel bindings + capabilities** — a bot is bound to a registry channel
   (`reactions`/`posting`/`editing`); `POST /bindings/{id}/check` verifies the real
   admin rights and `POST /capabilities/{id}/probe` records the channel's available
   reactions. The **reaction planner now intersects the profile emoji with the
   channel's confirmed set** (`reaction_planner.PlanParams.channel_available` /
   `bot_compatible`, fed by `reaction_policy.intersect_reactions`), so it never
   schedules an emoji Telegram does not support in that channel.
2. **Invite campaigns** (`/api/v1/campaigns`) — invite-link promotion that works
   with the manager bot only. Conservative `risk_mode` sets spacing; join requests
   and link revocation use normal Bot API calls.
3. **Donor quality** (`/api/v1/donors`) — explainable source-quality bands. When
   member data is unavailable, the bot-share estimate stays `null`; the service
   never invents a number.
4. **Backup destinations** (`/api/v1/backup/destinations`) — each new backup is
   delivered to every enabled destination (local / Telegram / Google Drive /
   Яндекс.Диск). A local destination is auto-created and cannot be deleted;
   remote credentials are sealed (`seal_secret`) and never returned.
5. **Setup Wizard** (`/api/v1/promotion`) — resumable, preset-driven onboarding
   that reflects **real** system state; without a session, session-gated steps are
   `optional`, not required.
6. **Auto-update** (`/api/v1/update`) — off by default; `check` compares the
   GitHub `releases/latest` tag with the running version (`core/versioning`), and
   `download` fetches the portable ZIP + `.sha256`, **verifies the checksum** and
   stages it under `updates/`. It never installs anything by itself.

**Why:** The primary product goal is that a non-technical owner can run the suite
on a weak Windows PC and get value immediately. Bots alone (no MTProto account)
should cover promotion and reactions; a wizard and a safe updater remove the
"read the docs first" barrier.

**Consequence:** New DB tables (`bot_channel_bindings`, `channel_capabilities`,
`invite_campaigns`, `invite_links`, `join_requests`, `donor_metrics`,
`backup_destinations`, `promotion_progress`, `update_state`) land in one Alembic
migration (`7cb72d22d35b`, autogenerate-drift clean). Diagnostics gained the new
subsystem rows and redacted-report sections (`bindings`, `capabilities`,
`campaigns`, `donors`, `backup_destinations`, `update`). `updates/` is git-ignored
and created by the portable build. New tests: `test_bindings_api.py`,
`test_campaigns_api.py`, `test_product_api.py`, plus the extended
`test_diagnostics.py`. Suite: **491 passed**.


---

## D-065 — 2026-10-04 — Network routes (proxies) are a connection route, never a limit bypass — LOCKED

**Decision:** An owner may attach an optional proxy to a user account
(`proxy_profiles` + `user_sessions.proxy_id`, `/api/v1/proxies`). A proxy is a
plain connection route: it does **not** lift Telegram FloodWait, privacy or admin
limits and must never be used to circumvent them. The password is accepted on
input, sealed at rest (`seal_secret`) and never returned (`has_password` only).
Every list response carries an explicit non-bypass notice.

**Why:** Some users genuinely need a route (no direct Telegram access), but the
project forbids bypassing Telegram limits (D-006). Keeping the route strictly
mechanical and the messaging explicit keeps that line clear.

**Consequence:** `ProxyStatus` is one of `UNKNOWN`/`OK`/`ERROR`/`TIMEOUT`; the
reachability check is honest and reports how to fix. Deleting a profile returns
its accounts to a direct connection. Diagnostics gained a `proxies` row and the
report a `proxies` section (host/kind/status only — never the password).

---

## D-066 — 2026-10-04 — Donor discovery returns candidate proposals; sources are added only explicitly — LOCKED

**Decision:** Donor search (`/api/v1/discovery`) stores **candidates**
(`donor_candidates`) and never adds a source automatically. A candidate becomes
an audience source solely through an explicit
`POST /discovery/candidates/{id}/add`. Provider availability is surfaced honestly;
hidden metrics stay zero with a `partial`/`confidence` marker rather than being
invented.

**Why:** Discovery must help the owner find donor channels without silently
committing their account to new sources or bypassing Telegram limits (D-006).

**Consequence:** Providers are pluggable (`telegram` today; `web`/`manual`
placeholders). The list shows fit/confidence; comparison (2–10 candidates) names
the best with a reason. Diagnostics gained `donor_candidates`; the report gained
a matching section.

---

## D-067 — 2026-10-04 — A lightweight local encoder is a first-class classifier mode with no model download — LOCKED

**Decision:** `mode="encoder"` (and the encoder stage of `auto`) uses a small,
dependency-free local encoder that needs **no model file and no download**, so it
works on a weak Windows PC. It is deterministic and advisory: rules remain the
deterministic default and every encoder failure degrades to the rules result.

**Why:** The product must give useful classification on the weakest machines
without requiring the owner to obtain a `.gguf` model.

**Consequence:** `MODE_ENCODER` is added to the classifier modes and `source` can
be `encoder`; the AI test panel exposes it. No new dependency, no new phase.

---

## D-068 — 2026-10-04 — The ruBERT backend is an *encoder* (embeddings only) with an honest install flow — LOCKED

**Decision:** The optional lightweight Russian model (`cointegrated/rubert-tiny2`,
MIT) is used **only as an embedding backend** for the existing prototype/KNN
classifier — never as a JSON-generating model, because ruBERT-tiny2 is an encoder,
not a generative LLM. The install flow (`services/encoder_service.py`,
`/api/v1/ai/encoder/*`) downloads only the official model files, verifies each
SHA-256, stores them under the gitignored `models/` directory and reports an
honest status; it never claims success without a real load.

**Why:** The owner must not have to understand Hugging Face / PyTorch, and a
small encoder cannot reliably emit strict JSON the way the GGUF LLM path does.
Keeping it as embeddings preserves the existing `EncoderClassifier` contract.

**Consequence:** `EncoderBackend` protocol + `backends/rubert.py` are lazily
loaded, CPU-only, single-inference and unload when idle (D-019/D-035); the
dependency-free hashing encoder stays the default so the weakest PC works with no
download. Tests use a fake backend; no network or heavy runtime is required.

---

## D-069 — 2026-10-04 — Bot-only analytics, adaptive wizard and intent-narrowed reactions — LOCKED

**Decision:** Three product behaviours are locked together: (a) analytics is
useful **without a user account** and states plainly that history is unavailable
for that connection type (it never hides the analytics window); (b) the promotion
wizard marks session-gated steps `optional` when no account is connected, with an
optional-account note, and shows an invite-restriction risk note when one is;
(c) the AI's communicative **intent** only *narrows* the reaction set
(`services/reaction_intent.py`) — it never chooses an emoji, and an empty
intersection skips the reaction with a reason.

**Why:** The main scenario ("I want to promote my channel") must work with bots
alone, and the owner must never be told a user account is safe for mass invites.

**Consequence:** `AnalyticsOverviewOut.account_connected/account_note`,
`WizardStateOut.session_optional_note/session_risk_note` and
`intent`/`intent_narrowed` on the simulate result; the UI renders all of them.

---

## D-070 — 2026-10-04 — Account Hub import is local-only, owner-scoped and secret-safe — LOCKED

**Decision:** The Account Hub (`services/session_import.py`) imports only local
artifacts the owner supplies — Telethon `.session`, `.session` + companion JSON,
StringSession and (optionally) Telegram Desktop TDATA — behind one
`SessionImportProvider` protocol. It never searches for, downloads or
bulk-registers third-party accounts and never bypasses verification, FloodWait,
privacy or identity checks. A StringSession string and TDATA auth data are
treated exactly like a `.session` file: written to the gitignored `SESSIONS_DIR`,
never logged, returned or rendered. TDATA stays optional with an honest
`NOT AVAILABLE` status when no reliable converter is installed, and the source
folder is never modified or uploaded.

**Why:** Importing an account the owner already controls is legitimate; acquiring
or automating someone else's account is not, and TDATA conversion is fragile
enough that a fake success would be worse than an honest gap.

**Consequence:** `.gitignore` also excludes `tdata/`, `*.session.json` and
`*.session_meta.json`; docs/SECURITY.md documents the import scope; detection
reports format + state (`valid`/`damaged`/`unauthorized`/`unknown`) before import.

---

## D-071 — 2026-10-05 — Content Studio is a source→item→publish pipeline over the existing provider seams — LOCKED

**Decision:** The Content Studio (`db/models/content.py`,
`providers/content_sources.py`, `services/content_service.py`) collects material
from Telegram / RSS / Atom / manual sources and turns it into publications on the
owner's own channels. It introduces **no new Telegram client**: reading a Telegram
source goes through the existing `SessionProvider`, and publishing goes through a
`PostingProvider` that wraps `TelegramBotProvider` (bot mode, the default) or
`SessionProvider` (expanded mode). Neither the service nor the providers import
aiogram or Telethon directly (D-001).

**Why:** The suite already has one provider abstraction per concern; a parallel
client would duplicate credentials handling, redaction and error translation.

**Consequence:** `providers/posting_base.py` defines `PostingProvider`
(`publish`/`delete`/`send_comment`/capabilities); `providers/posting.py` holds the
concrete bot/user providers.

---

## D-072 — 2026-10-05 — Content is never published without an explicit owner action — LOCKED

**Decision:** Grabbing material only creates `ContentItem`s. A publication exists
only after the owner plans it, and a scheduled publication is sent by the durable
posting tick — never by an implicit "auto-publish everything" default. A held
(moderation) item is not published until the owner releases it. A lost connection
during publish marks the publication `uncertain` rather than silently retrying.

**Why:** Publishing is irreversible and public; an implicit default would let a
grab turn into an unwanted post.

**Consequence:** `services/posting_service.py` exposes plan/schedule/publish/
retry/release as explicit operations; `tick()` only acts on `planned`/`scheduled`
publications that are due.

---

## D-073 — 2026-10-05 — Content rights are owner-declared, not legally checked — LOCKED

**Decision:** Usage rights are recorded from what the owner states (`own` /
`allowed` / `licensed` / `public` / `unknown`). The suite never performs a legal
check. When rights are unknown, publishing warns and keeps an attribution block
(source link) rather than silently proceeding or hard-blocking.

**Why:** The suite cannot determine copyright, but it can avoid pretending a
material is safe and can preserve attribution.

**Consequence:** `RightsStatus` + `RIGHTS_TITLES`; `services/content_service.py`
`rights()` returns the warning and attribution block; the UI renders both.

---

## D-074 — 2026-10-05 — Protected content keeps only its link (D-006) — LOCKED

**Decision:** When a Telegram source forbids forwarding/downloading
(`noforwards`), the Content Studio stores only the post's link (and metadata),
never a copy of the text or media, and marks the source `protected`.

**Why:** Copying protected content would violate the author's setting and
Telegram's rules; a link preserves the reference without duplicating the work.

**Consequence:** `providers/content_sources.py` returns a link-only item and the
`GrabOut.protected` flag; the UI states that only the link was kept.

---

## D-075 — 2026-10-05 — The posting tick is a bounded, restart-safe periodic job — LOCKED

**Decision:** Due publications, auto-deletions and first comments are driven by
one durable job kind (`content.posting`). The handler runs one bounded pass and
re-schedules itself every `POSTING_TICK_SECONDS` (D-008 style); `main.py` seeds
the first tick with `QueueService.ensure_periodic`. There is no separate scheduler
primitive and no in-memory timer.

**Why:** A periodic self-rescheduling durable job survives restarts and fires a
later-scheduled publication without a restart, without adding infrastructure.

**Consequence:** `scheduler/handlers.py::_handle_posting`,
`QueueService.ensure_periodic`, `PostingService.tick()/due_count()`.

---

## D-076 — 2026-10-05 — The AI never picks emoji and the encoder never generates — LOCKED

**Decision:** The Content Studio's rewrite routes through the existing generative
LLM backend only. The lightweight encoder (ruBERT-tiny2) is an embedding/classifier
backend and is never used to generate text (D-068). Reaction selection remains an
intersection of profile ∩ AI intent ∩ channel capabilities ∩ bot compatibility; the
AI narrows, it never picks the emoji (D-033).

**Why:** An encoder cannot generate reliable prose; asking it to would produce
broken output. Keeping the AI in a narrowing role preserves the deterministic
rules engine as the default.

**Consequence:** `services/content_service.py::rewrite_preview` uses the LLM
backend; the encoder is used only for classification/embeddings.


---

## D-077 — 2026-10-05 — Bot Factory creates bots through the official owner-confirmed flow — LOCKED

**Decision:** The Bot Factory plans a *set* of worker bots (names + usernames),
checks username availability through Telegram, and creates each bot through the
official @BotFather flow that the owner confirms; it then **adopts** the created
bot. It never registers Telegram accounts, never automates phone verification and
never bypasses Telegram limits. The managed-bot token is write-only and never
returned.

**Why:** Mass account registration and verification bypass violate Telegram's
rules and are explicitly out of scope; adopting an owner-created bot keeps the
action legitimate and auditable.

**Consequence:** `services/bot_factory.py` (`check_availability`, `create`,
`adopt`), `providers/fake_session.py::FakeBotFactoryScenario` for tests, the
`/api/v1/bot-factory/*` router and the `/bot-factory` UI page.

---

## D-078 — 2026-10-05 — Bot Factory reuses BotService/BindingService and keeps the manager bot unique — LOCKED

**Decision:** A factory-created bot is registered through the existing
`BotService` and bound through the existing `BindingService`; there is exactly one
manager bot (adding a second is a 409). No parallel bot/binding path exists.

**Why:** A single path guarantees the binding + capability rules (D-030) apply
identically to factory bots and manual bots.

**Consequence:** `get_bot_factory_service` composes `BotService` + `BindingService`;
`db/models/bot_factory.py::BotCandidate` stores the resulting `Bot` row id.

---

## D-079 — 2026-10-05 — LAN Mesh never shares a live SQLite file and never trusts a peer automatically — LOCKED

**Decision:** Each computer keeps its own SQLite database; a live database file is
never opened over a network share (no multi-writer SQLite). A discovered peer is a
*candidate* only; it becomes trusted after the owner verifies a short one-time
pairing code. The pairing credential is stored only as a salted hash and the raw
code/secret are never stored or returned.

**Why:** Multi-writer SQLite over a network share corrupts data; implicit trust of
LAN devices is a security hole.

**Consequence:** `db/models/mesh.py`, `mesh/discovery.py`, `mesh/pairing.py`, the
`/api/v1/mesh/*` router.

---

## D-080 — 2026-10-05 — Mesh leases use fencing tokens; a stale owner cannot commit — LOCKED

**Decision:** A job is leased to exactly one worker with a monotonically
increasing `fencing_token`. After a failover the old owner's token no longer
matches, so its commit is rejected and it can never overwrite a newer result.
Expired leases are reclaimed by the `mesh.tick` handler.

**Why:** Without fencing, a slow old worker could clobber the result of the worker
that took over after failover.

**Consequence:** `mesh/lease.py::can_commit`, `MeshService.acquire_lease` /
`complete_lease` / `reclaim_expired`.

---

## D-081 — 2026-10-05 — Only the elected coordinator owns Telegram pollers in a mesh — LOCKED

**Decision:** When the mesh is enabled and this node is not the elected
coordinator, the manager-bot runtime (Telegram polling) does **not** start. The
coordinator election prefers the highest priority node that advertises the
`telegram` capability, ties broken by node id, excluding offline nodes.

**Why:** Two computers polling the same bot token would double-process updates.

**Consequence:** `main.py` lifespan guard via `MeshService.owns_telegram_pollers`;
`mesh/election.py`.

---

## D-082 — 2026-10-05 — The mesh is optional, off by default, and never a limit bypass — LOCKED

**Decision:** Standalone (one computer, everything local) is the default;
`mesh_enabled` is off by default and `mesh_mode` defaults to `standalone`. The mesh
is a coordination layer for the owner's own computers and never enables bypassing
Telegram limits, aggressive proxy rotation, or mass account registration.

**Why:** Most installs are a single weak Windows PC; the mesh must add no cost or
complexity unless the owner opts in.

**Consequence:** `core/config.py` mesh settings; `MeshView.vue` states the
standalone default; `mesh.tick` is a cheap no-op while disabled.

---

## D-083 — 2026-10-05 — Mesh secrets are never persisted and mesh ping is authenticated — LOCKED

**Decision:** The mesh stores only a salted hash of a pairing code; nothing
derived from a secret is written to a user-visible field. The `/api/v1/mesh/ping`
liveness endpoint verifies the `X-Mesh-Secret` header against the configured
shared secret (timing-safe) and rejects a request when a secret is configured but
missing or wrong.

**Why:** A sealed-but-truncated secret in the peer `note` was returned by the API
and provided no authentication value; an unauthenticated ping is an open probe for
any host on the same network.

**Consequence:** `mesh/service.py` (pair), `api/v1/mesh.py` (ping),
`tests/test_mesh_api.py` (note-leak and ping-auth tests).

---

## D-084 — 2026-10-05 — The Notification Center is durable and stores no secrets — LOCKED

**Decision:** Every notification the app raises is recorded in the `notifications`
table with its category, priority, destination, status and display-safe text; each
delivery attempt is recorded in `notification_deliveries`. Only non-secret,
display-safe data is stored — no token, API hash, session string, password or
audience record ever reaches these tables.

**Why:** The pre-v1.4 in-process bus was fire-and-forget: the owner could not see
what happened, what failed, or whether delivery worked. A durable history makes
the subsystem inspectable, while the secret-free rule keeps the existing redaction
guarantee intact.

**Consequence:** `db/models/notification.py`, `db/repositories/notifications.py`,
`services/notification_service.py`, `api/v1/notifications.py`,
`tests/test_notifications.py`.

---

## D-085 — 2026-10-05 — Quiet hours postpone only non-urgent notifications — LOCKED

**Decision:** During quiet hours, `info`/`success` notifications are postponed
until the window ends (`postponed_until`); `warning`, `error` and `critical`
notifications are always delivered immediately. Postponed items are delivered by
the manager-bot runtime when due.

**Why:** Quiet hours must silence routine chatter without hiding a real problem.
A blanket mute would risk missing an error overnight; an unconditional
pass-through would defeat quiet hours entirely.

**Consequence:** `services/notification_service.py` (`in_quiet_hours`,
`_quiet_until`, `deliver_due_postponed`), `manager/runtime.py`,
`tests/test_notifications.py`.

---

## D-086 — 2026-10-05 — Identical notifications are aggregated, never spammed — LOCKED

**Decision:** A notification carries a deterministic `dedup_key`
(`category` + `event_key`). A repeat of the same key inside the aggregation window
does not create a new delivery: the existing record's `aggregate_count` grows and
its status becomes `aggregated` (the first record stays `sent` as the master).
Aggregation can be turned off in settings.

**Why:** A recurring condition (a flapping health check, a repeated channel error)
must be visible once, not hundreds of times. Aggregation keeps the history
readable and protects Telegram from a self-inflicted rate limit.

**Consequence:** `services/notification_service.py` (`submit`,
`_aggregate_message`), `db/models/notification.py` (`dedup_key`,
`aggregate_count`, `NotificationStatus.AGGREGATED`), `tests/test_notifications.py`.

---

## D-087 — 2026-10-05 — The tray agent supervises the backend with a bounded restart backoff — LOCKED

**Decision:** The TCMS Tray Agent starts the backend hidden, waits for `/health`
(never a fixed sleep) and restarts an unexpectedly exited backend at most
`DEFAULT_MAX_RESTARTS_PER_HOUR` (5) times per hour. When the cap is hit the agent
stops auto-restarting and reports the state honestly.

**Why:** A crash loop must not spin the CPU or the network forever, and a fixed
sleep would either open the browser too early or delay it needlessly. Readiness is
polled; restart is bounded.

**Consequence:** `tray/supervisor.py`, `tray/agent.py`, `portable/run.bat`,
`services/diagnostics_service.py::_tray_item`, `tests/test_tray_agent.py`.

---

## D-088 — 2026-10-05 — Tray autostart uses the Startup folder and writes no secret — LOCKED

**Decision:** "Запускать вместе с Windows" writes a plain `.cmd` launcher into the
user's Startup folder (no admin, no registry, no service). The agent's state
snapshot (`data/tray.json`) contains only state, pid, restart count, last error,
autostart flag and version; unknown fields are filtered on read.

**Why:** A normal user must be able to enable/disable autostart without elevation,
and a separate process must not become a new place where secrets could leak.

**Consequence:** `tray/autostart.py`, `tray/state.py`, `tests/test_tray_agent.py`.

---

## D-089 — 2026-10-05 — Editorial rights are verified, never assumed — LOCKED

**Decision:** An editorial room only reaches the `ready` status after Telegram
confirms the bot is a member of the forum group and can send messages. A missing
right leaves the room in `needs_rights` with the specific right named. The suite
never shows a room as ready (or claims a capability) without a real check.

**Why:** A card that silently fails to post is worse than an honest "needs rights"
state; assuming rights would also violate the project-wide honesty rule used by
the permission probe and the bot↔channel bindings.

**Consequence:** `services/editorial_service.py` (`check_room`),
`db/models/editorial.py` (`RoomStatus`), `frontend/src/views/EditorialView.vue`,
`tests/test_editorial.py`.

---

## D-090 — 2026-10-05 — Editorial roles are numeric Telegram ids; the suite owns the queue order — LOCKED

**Decision:** Editorial authorization matches a member by numeric
`telegram_user_id` (the owner is determined by `MANAGER_BOT_ADMIN_IDS`); a username
is never an identity. The queue order (`order_index`) and status live in the
database; a status change posts a fresh card into the target topic rather than
moving messages between topics.

**Why:** A username can be changed or spoofed, so it cannot be an identity; and a
bot cannot reliably move a message between forum topics, so the order must be
owned by the suite and merely mirrored in Telegram.

**Consequence:** `db/models/editorial.py` (`ROLE_ACTIONS`, `EditorialRole`,
`EditorialMember`), `services/editorial_service.py` (`role_for`, `can`, `move`,
`reorder`), `tests/test_editorial.py`.

---

## D-091 — 2026-10-05 — Editorial publishing reuses the Content Studio posting path — LOCKED

**Decision:** Approving/publishing an editorial item resolves (or plans) the
item's Content Studio publication and publishes it through the existing
`PostingService`; the editorial queue does not implement a second publish path.

**Why:** Two publish paths would diverge (different auto-delete/first-comment
behaviour, different provider rules). Reusing one path keeps the editorial queue
and Content Studio consistent and honours the existing content decisions
(D-071…D-076).

**Consequence:** `api/deps.py::get_editorial_service` (`_publish` handler),
`services/editorial_service.py` (`publish_handler`), `tests/test_editorial.py`.

---

## D-092 — 2026-10-05 — One machine-readable capability graph is the source of truth for "what is available" — LOCKED

**Decision:** A single registry (`services/capability_graph.py`) declares every
capability and the requirements it needs. `context_from_db(session)` reads the
real database state, `evaluate_all()` returns a `CapabilityState` per capability
(`available` / `partial` / `needs_setup` / `unavailable`, plus `satisfied`,
`missing`, `missing_fixes`). The Dashboard, the Promotion Wizard and the
Diagnostics panel all read this graph instead of re-deriving "does this need a
session?" locally.

**Why:** The same question ("is reaction ready?") was answered in several places
with slightly different logic; they could disagree and the owner saw inconsistent
advice. One graph removes the drift and gives the Diagnostics auditor something
concrete to check.

**Consequence:** `services/capability_graph.py`, `api/v1/capability_graph.py`,
`api/schemas/capability.py`, `WizardState.capabilities`, `DashboardView.vue`
("Что уже доступно"), `tests/test_consistency.py`,
`tests/test_architecture_consistency.py::test_capability_requirements_are_known`.
A missing optional requirement is always `needs_setup`/`unavailable`, never an
error.

---

## D-093 — 2026-10-05 — Backend user strings come from one bilingual i18n catalog — LOCKED

**Decision:** `core/i18n.py` holds one RU/EN catalog; backend-produced user
strings (capability titles, the invite-risk warning) are read through
`translate(key, language)`. The UI language is a stored, non-secret preference
(`services/ui_prefs.py`, default `ru`) exposed on `/api/v1/help/prefs`.

**Why:** Wording must be single-sourced so one change reaches every surface, and
the risk wording in particular must never drift into something that promises a
safe limit (D-006/D-069).

**Consequence:** `core/i18n.py`, `services/ui_prefs.py`, `api/schemas/help.py`,
`tests/test_i18n.py`,
`tests/test_architecture_consistency.py::test_i18n_keys_are_complete`.
`missing_keys()` is empty and asserted in CI.

---

## D-094 — 2026-10-05 — The Consistency Auditor reports drift; it never changes runtime behaviour — LOCKED

**Decision:** `services/consistency_checks.py` runs **static** checks (models↔
migrations, frontend calls↔routes, job kinds↔handlers, routes↔views, real/fake
providers, capability registry, i18n completeness, help topics, documented
prefixes). Hard drift is an `error`; heuristic noise (unused routers, orphan help
topics) is `info`. `services/consistency.py` adds DB-backed runtime checks. The
report (`GET /api/v1/consistency`) contains no secrets, sessions, phones or
database rows. The static checks also run in `pytest` so drift fails a PR.

**Why:** The project grew past 700 tests and many modules; cross-module drift
(a route the UI calls but the backend removed, a table without a migration) is
exactly the class of bug a human review misses. Making it a CI gate keeps the
codebase honest.

**Consequence:** `services/consistency_types.py`, `services/consistency_checks.py`,
`services/consistency.py`, `api/v1/consistency.py`, `api/schemas/consistency.py`,
`DiagnosticsView.vue` ("Проверка целостности"), `tests/test_consistency.py`,
`tests/test_architecture_consistency.py`. The auditor is additive: it never blocks
startup and never mutates data.

---

## D-095 — 2026-10-06 — A capability without an implementation is never `available` — LOCKED

**Decision:** A `Capability` carries an explicit `implemented` flag. When it is
`False`, `evaluate()` always returns the new state `not_implemented`
("Не реализовано" / "Not implemented") regardless of the requirement context, and
`CapabilityState.implemented` mirrors the flag through the API. The static
Consistency Auditor gained `check_capability_implementation()`, which fails
(`error`) if a capability is marked `implemented=True` while no matching code
signal exists in `backend/app`. `config_sync` and `media_conversion` are
`implemented=False` (no Owner-Auth/cloud-sync and no ffmpeg/media tooling exist).

**Why:** The forensic audit of v1.5.0 found `config_sync` reporting **`available`
on an empty install** while no sync implementation existed — a false claim the
user could not fix by configuring anything. The registry must be able to describe
a future capability without lying about its readiness.

**Consequence:** `services/capability_graph.py` (`implemented`,
`STATE_NOT_IMPLEMENTED`), `api/schemas/capability.py` + `api/v1/capability_graph.py`
(`implemented`), `core/i18n.py` (`cap.state.not_implemented`),
`services/consistency_checks.py` (`check_capability_implementation`),
`DashboardView.vue` (renders the note),
`tests/test_consistency.py::test_unimplemented_capabilities_are_never_available`,
`tests/test_architecture_consistency.py::test_capabilities_have_implementations`.

---

## D-096 — 2026-10-06 — A consistency check that raises is an error, never silently skipped — LOCKED

**Decision:** `run_static_checks()` (static) and
`ConsistencyAuditor._runtime_findings()` (runtime) no longer `except Exception:
continue`. A check that raises produces an `error` finding
(`audit.check_failed.<name>`) carrying the exception type and message, so
"checked and clean" is distinguishable from "could not run".

**Why:** The audit found `_runtime_findings` silently swallowed errors. A check
that never runs looks identical to a passing check — the auditor could report
"pass" precisely when it was blind.

**Consequence:** `services/consistency_checks.py`, `services/consistency.py`,
`tests/test_architecture_consistency.py::test_auditor_never_swallows_a_failed_check`.

---

## D-097 — 2026-10-06 — Capability labels and the language preference are actually consumed — LOCKED

**Decision:** `GET /api/v1/capability-graph` resolves the language from the saved
UI preference (`UiPrefsService.get_language()`) when no explicit `language` query
parameter is given, so the labels match what the user picked. The Settings page
gained a real language selector (`help.setLanguage`) writing the stored
preference; the help store exposes `language` / `availableLanguages`.

**Why:** The audit found the i18n catalog and the stored `language` preference
were wired to the API but **no UI ever read them** — the preference was
write-only and every label stayed RU.

**Consequence:** `api/v1/capability_graph.py`, `frontend/src/stores/help.ts`,
`frontend/src/views/SettingsView.vue`, `frontend/src/api/client.ts` (`UiPrefs`),
`tests/test_consistency.py::test_capability_graph_language_follows_ui_preference`.
Scope is honest: the beginner help catalog (`help_topics.py`) stays RU-first (not
machine-translated); the preference localises backend-produced strings (capability
titles/states), not the entire UI.

---

## D-098 — 2026-10-06 — A source-comparison check with no sources reports "unavailable" (info) — LOCKED

**Decision:** Static checks that compare repository *source* files
(`check_api_route_frontend_client`, `check_frontend_route_view`,
`check_help_catalog_usage`, `check_orphan_help_ids`, `check_documented_endpoints`)
first verify their input directory exists (`frontend/`, `docs/`). When it does not
(the runtime Docker image ships only the backend), the check emits an **`info`**
finding `audit.source_unavailable.<name>` and is skipped, instead of raising into
an `audit.check_failed.<name>` **error**. Backend-only checks always run.

**Why:** The v1.5.1 Docker smoke surfaced a real defect: on the honest
no-silent-failure runner (D-096), the runtime image reported
`overall: fail` because it has no `frontend/` source, even though nothing was
wrong. A deployment condition must not look like drift — but it also must not be
silently skipped (D-096). "Could not check here" is a distinct, honest state.

**Consequence:** `services/consistency_checks.py` (`_SOURCE_CHECKS`,
`run_static_checks`). The Docker `/api/v1/consistency` report now returns
`overall: pass` with five `info` notes; the dev checkout and CI still run every
check fully. Test:
`tests/test_architecture_consistency.py::test_missing_source_tree_is_info_not_error`.


---

## D-099 — 2026-10-06 — The Consistency Auditor is proven against seeded defects ("Проверка проверяющего") — LOCKED

**Decision:** The Consistency Auditor may not be assumed reliable. A **meta-audit**
harness (`tests/test_consistency_mutations.py` + `tests/test_meta_audit.py`) builds
an isolated copy of the repository source tree, injects **one synthetic defect per
test**, and asserts the corresponding finding appears — then discards the copy. A
machine-readable kill-rate summary is written to `agent/META_AUDIT_RESULT.json` and
uploaded by a dedicated `meta-audit` CI job. No synthetic defect is ever written to
the working tree.

The same cycle closed four detection gaps the harness exposed and hardened two
checks that were structurally unable to fail:

1. **False capability / stray-string mask (F1/F2).** `check_capability_implementation()`
   now requires a **strong anchor** — a real service class (e.g.
   `class ReactionService` in `services/reaction_service.py`) registered in
   `CAPABILITY_SERVICE_ANCHORS`. A capability with `implemented=True` and no anchor
   is `capabilities.no_anchor.<key>`; a missing/renamed service is
   `capabilities.unimplemented.<key>`. A stray string/comment named after the
   capability no longer counts.
2. **Registry pointing at a deleted module (E2).** `check_provider_registry()` now
   verifies every `backend.app.providers.<module>` import in `registry.py`
   resolves to a real file (`providers.registry_missing.<module>`).
3. **i18n / hardcoded UI strings (H).** `check_hardcoded_ui_strings()` flags
   user-visible Vue text carrying a placeholder marker (`_RU_UI_MARKERS`) that
   bypasses the catalog (`ux.hardcoded_string.<file>:<line>`), severity
   **warning**, confidence **low**. Broad Cyrillic scanning is deliberately avoided
   (the current SPA keeps Russian UI text in components); the limitation is
   documented in the check docstring.
4. **New static checks.** `check_router_registration()` (an `APIRouter` module not
   included in `router.py` → `api.router_unregistered.<module>`),
   `check_backup_destination_registry()` (enum kind with no provider →
   `backup.destination_no_module.<kind>` / `backup.destination_missing.<kind>`),
   `check_notification_routing()` (category with no `DEFAULT_ROUTING` entry →
   `notifications.no_routing.<category>`).
5. **Capability dependency is enforced at evaluation.** `capability_graph.evaluate()`
   treats a requirement naming an unimplemented capability as missing, so a
   dependent capability can never report `available`/`partial` on that basis.

**Why:** The prior cycle "fixed" the auditor but only proved the checks that were
easy to trigger. Four breakages (false capability, stray-string mask, registry
miss, i18n gap) passed green. Trust in the auditor must be earned with evidence,
not asserted.

**Consequence:** `services/consistency_checks.py`,
`services/capability_graph.py`, `tests/test_consistency_mutations.py`,
`tests/test_meta_audit.py`, `.github/workflows/ci.yml` (job `meta-audit`).
Static suite stays `pass` (0 error, 0 warning, 2 info) on the real tree.

---

## D-100 — 2026-10-06 — Auditor coverage gaps are recorded honestly; `_check_channel_aware` silent failure fixed — LOCKED

**Decision:** The meta-audit reports the auditor's real kill rate (**75%**: 18 of 24
seeded defects detected, 6 missed, **0 critical**, 2 high) in
`agent/META_AUDIT_RESULT.json` with `status: gaps_found`. Remaining gaps are
documented and pinned by `strict=True` `xfail` tests, never hidden:

| Gap | Severity | Reason |
|-----|----------|--------|
| L — orphan setting (static) | medium | runtime-only heuristic; no static consumer graph |
| M — write-only setting | **high** | allow-listed `sync_*`/`owner_*` keys are read nowhere |
| N — unused DB field | medium | no per-column usage analysis |
| O — service without caller | medium | no dead-code/caller analysis |
| P — control without behavior | medium | no UI-control ↔ endpoint wiring check |
| Q — channel-aware module code | **high** | runtime covers rows, not module code |

The meta-audit also surfaced and fixed a **real** silent failure: the runtime
`_check_channel_aware()` queried `ContentItem.channel_id`, which does not exist, so
it always raised and was swallowed by `except Exception: return findings` — the
check had never detected anything. It now queries `ContentSource.channel_id` (the
D-051 registry link) and emits `channel-aware.content_source`.

A cross-file release-hygiene guard (`test_repo_version_is_consistent`,
`test_readme_states_the_current_release`) caught `README.md` still claiming
`v1.5.0` while the code shipped `v1.5.1`; the README is corrected.

**Why:** "No gaps found" would be a false claim. A trustworthy auditor states what
it cannot yet catch, and a high-severity miss (write-only settings) must prevent a
"trust: HIGH" verdict. The `except Exception` swallow is exactly the class of
silent failure the meta-audit exists to find.

**Consequence:** `services/consistency.py`, `agent/META_AUDIT_RESULT.json`,
`tests/test_consistency_mutations.py` (xfail gap tests),
`tests/test_meta_audit.py`, `README.md`. Next work may promote gaps L/M/N/O/P/Q to
real checks, starting with M (write-only settings) since it is high severity.

---

## D-101 — 2026-10-06 — The default language is Russian, resolved from the saved preference — LOCKED

**Decision:** The product is Russian-first. `core/i18n.py` exposes
`normalize_language()`; an unknown/absent language resolves to Russian
(`DEFAULT_LANGUAGE = "ru"`) rather than English, and the stored `language`
preference is consumed (capability graph + Settings RU/EN selector, D-097). Every
catalog key must have both RU and EN text (`missing_keys()` → CI check).

**Why:** The target user is a Russian-speaking channel owner; an English fallback
would surface the wrong language on a fresh install. A single catalog keeps the
Web UI, Mini App and backend messages consistent.

**Consequence:** `core/i18n.py`, `services/ui_prefs.py`, `services/consistency_checks.py`
(`check_i18n_completeness`).

---

## D-102 — 2026-10-06 — The auditor's kill rate is computed from runtime mutation executions, never declared — LOCKED

**Decision:** The Consistency Auditor's kill rate must be **measured**, not
asserted. `tests/meta_audit/engine.py` runs a real mutation suite: for each seeded
defect it builds an isolated copy of the source tree (or a fresh temp DB for
runtime checks), injects the defect, runs the **real** auditor, and classifies the
result by semantically matching the finding it actually produced against the
expected finding id/severity. `agent/META_AUDIT_RESULT.json` is a **generated**
artifact (`result_source: "computed from runtime mutation executions"`) with
per-mutation `{id, detected, expected, actual_findings, severity}`; all totals
(`detected`, `missed`, `kill_rate`, `false_positives`, `critical_misses`,
`high_misses`, `status`) are derived from those records.

Hard rules:
1. No `detected`/`missed` value may come from a pre-declared list (`_DETECTABLE`,
   `_MISSED` or equivalent). The previous declarative lists are **deleted**.
2. An unrelated finding is never a detection (semantic match only).
3. The suite includes **negative controls**: a clean tree must not produce a
   mutation finding (0 false positives), asserted in `pytest` and CI.
4. The working tree is never mutated; synthetic defects live only in throwaway
   copies (asserted by a test and by a CI leak check).
5. CI must **not** compare against a hardcoded percentage. It checks that every
   mutation has a runtime result, that the arithmetic is consistent, that negative
   controls false-fire zero times, and that no previously-detected mutation has
   become a miss (`regression_against`).

**Why:** A kill rate assembled from hand-maintained lists keeps showing the old
number even after a detector is deleted. Measuring by execution makes the number a
property of the code: remove a detector and the mutation becomes a miss and the
rate drops automatically; add a mutation and `total` grows automatically.

**Consequence:** `tests/meta_audit/engine.py`, `tests/meta_audit/mutations.py`,
`tests/test_consistency_mutations.py`, `tests/test_meta_audit.py`,
`.github/workflows/ci.yml` (job `meta-audit`), `agent/META_AUDIT_RESULT.json`
(regenerated). Known gaps are recorded in `KNOWN_GAP_IDS` and still executed —
never hardcoded as misses.

---

## D-103 — 2026-10-06 — Write-only settings and channel-registry drift are detected statically — LOCKED

**Decision.** Two auditor coverage gaps that the runtime mutation engine recorded
as **high** misses are closed with **pure, deterministic static checks** in
`backend/app/services/consistency_checks.py`, registered in `run_static_checks()`
(so `pytest` and CI fail on regression):

- **M — `check_write_only_settings`.** Parses the backend AST and compares the set
  of setting keys **written** (a `.set(<literal>)` call on a SettingsService-like
  receiver: `SettingsService(...)`, a local alias bound to it, `self.settings`,
  `self.repo`) against the set **read** (`.get_typed`/`.get_raw` literals plus keys
  declared in a `*_SETTING_SPECS` map). A literal write with no reader is a finding
  `settings.write_only.<key>`. Environment-backed keys (`OPENHANDS_*`/`TCMS_*`) are
  skipped; the check never matches a bare string occurrence.
- **Q — `check_channel_registry_usage`.** Flags a service module that is
  channel-aware (a class/function named `*channel*`, or a function taking a
  `channel_id`/`registry_channel_id` parameter) but never uses a canonical channel
  identity (no `Channel*` import, no canonical parameter). Finding
  `channel-aware.module.<module>`. This complements the runtime
  `_check_channel_aware` (which covers DB rows) by covering module **code**
  (D-051/D-055).

Both are proven by execution, not declaration: their mutations
`M_write_only_setting` and `Q_channel_aware_module` moved out of `KNOWN_GAP_IDS`
and are now **detected** by the runtime engine. Two negative controls
(`NC4_setting_with_reader`, `NC5_channel_aware_with_registry`) assert precision —
a written-and-read setting and a channel-aware module that uses `ChannelRepository`
are **not** flagged.

**Why:** A setting the owner can save but nothing reads is a silent trap; channel
code that keeps a private target string drifts from the registry (no verified
rights, no shared settings). Both are detectable without a database or network.

**Consequence:** `consistency_checks.py` (+2 checks), `tests/meta_audit/mutations.py`
(M/Q detected, NC4/NC5 controls, `KNOWN_GAP_IDS` = {N, O, P}),
`tests/test_architecture_consistency.py`, `tests/test_meta_audit.py`,
`backend/app/services/consistency.py` (honest `_known_setting_keys`),
`agent/META_AUDIT_RESULT.json` (regenerated: 25 total, 22 detected, 3 missed,
88.0%, 0 false positives, 0 critical/high misses). The remaining gaps (N, O, P) stay
executed and honestly recorded.

---

## D-104 — 2026-10-06 — The last three auditor gaps (N, O, P) are closed statically — LOCKED

**Decision.** The three remaining Consistency Auditor coverage gaps that the
runtime mutation engine recorded as misses are closed with **pure, deterministic
static checks** in `backend/app/services/consistency_checks.py`, registered in
`run_static_checks()` (so `pytest` and CI fail on regression). `KNOWN_GAP_IDS` is
now **empty** and the kill rate reaches **100% (25/25, 0 false positives)**:

- **N — `check_unused_model_columns`.** Derives ORM columns from `mapped_column`
  declarations and flags any column whose name never appears as an attribute,
  keyword argument or string literal anywhere outside the model files (so
  serialisers, `getattr`/`setattr` and JSON keys count as a use). Finding
  `db.unused_column.<module>.<Class>.<name>`, severity `info`, confidence
  `medium`. Intentionally-kept extension points can be listed in
  `INTENTIONAL_UNUSED_COLUMNS`.
- **O — `check_orphan_service_classes`.** Flags a public service class that no
  module references (a plain `import` does not count — the class must be
  instantiated, passed or have a method called). Finding
  `dead.service.<module>.<Class>`, severity `info`. Exempt list:
  `INTENTIONAL_ORPHAN_CLASSES`.
- **P — `check_frontend_unwired_controls`.** Flags a Vue `@click`/`@change`/
  `@submit`/`@input` handler that names a function the component never defines (a
  typo) or a function with an empty body. Inline assignments/expressions are out
  of scope; a handler with any body is trusted. Finding
  `frontend.control_unwired.<name>`, severity `warning` (a user-visible dead
  control).

All three are proven by execution: their mutations `N_unused_db_field`,
`O_service_without_caller` and `P_control_without_behavior` are now **detected**
by the runtime engine. Three new negative controls prove precision:
`NC6_used_db_column` (a column that is added *and* read), `NC7_referenced_service`
(a class that is added *and* instantiated) and `NC8_wired_frontend_control` (a
control *and* its defined handler) are **not** flagged. Detector removal flips each
mutation back to a miss (parametrised test over M/N/O/P/Q).

**Why:** Dead schema, dead services and dead UI controls are exactly the kind of
silent drift the auditor exists to catch. N and O are `info` (orphan signals — a
column/class may be a documented extension point); P is `warning` because a dead
control is directly visible to the user.

**Consequence:** `consistency_checks.py` (+3 checks, +2 allow-list constants),
`tests/meta_audit/mutations.py` (N/O/P detected, NC6/NC7/NC8 controls,
`KNOWN_GAP_IDS` = ∅), `tests/test_architecture_consistency.py`,
`tests/test_meta_audit.py`, `agent/META_AUDIT_RESULT.json` (regenerated: 25 total,
25 detected, 0 missed, 100.0%, 0 false positives, 0 critical/high misses). The
version becomes **1.5.4**.


---

## D-105 — 2026-10-07 — Owner Auth is a local, offline identity that protects the panel — LOCKED

**Decision.** The Suite gains a **single local owner identity** (v1.6): a password
or PIN that protects the Web UI / API on this computer. It is **not** linked to any
Telegram account or session and works fully offline. Two independent values are
derived from what the owner types and kept separate:

* a **verifier** — a slow PBKDF2-HMAC-SHA256 hash (200k iterations) stored in the
  DB, used only to check a password at login; it can never be turned back into the
  password;
* a **config-bundle key** — derived from the password plus a non-secret per-owner
  `sync_salt`, **never stored**, recomputed in memory at unlock and used to
  encrypt/decrypt the config-sync bundle.

A successful login issues an HMAC-signed opaque **session token** (never a
password, never reversible to one), sent by the SPA as the `X-Owner-Token` header.
`OwnerGuardMiddleware` is a **middleware**, not a per-route dependency, so a new
router cannot be added unguarded: protection is default-on for every `/api/` path
outside a small allowlist (health, docs, owner status/setup/login, system status).
It is **local-first**: while no owner profile exists — or protection is explicitly
off — the API stays open exactly as before. Repeated wrong attempts are rate-limited
(5 → 15-minute lock).

**Why.** The owner runs this on a personal Windows PC; a local profile protects the
configuration without inventing accounts, cloud identity or Telegram coupling, and
without adding a dependency (stdlib only).

**Consequence:** `core/owner_security.py`, `db/models/owner.py`,
`db/repositories/owners.py`, `services/owner_auth_service.py`, `api/owner_guard.py`,
`api/schemas/owner.py`, `api/v1/owner.py`, migration
`20261007_1000_f8b2d3e5a7c9`; the `/owner` RU-first UI page and an `owner_auth`
help topic. Nothing here searches for, downloads or registers third-party accounts.

---

## D-106 — 2026-10-07 — Config Sync moves an encrypted, versioned configuration bundle — LOCKED

**Decision.** "Config Sync" carries the Suite's configuration to a new computer as
a small **versioned, encrypted document** — never the live SQLite database, never
session files or TDATA. The document is canonical JSON, encrypted with
AES-256-GCM using the key from D-105; the schema version is authenticated as
associated data so a downgrade/version swap is detected as tampering. A provider
stores only the ciphertext:

* **`local`** — a folder on disk (default, always available);
* **`google_drive`** — the owner's Drive **app-data scope** (least privilege),
  optional and independent of the owner password; the app ships no OAuth secret,
  the owner registers their own client id.

A **denylist + safety scan** (`FORBIDDEN_KEY_MARKERS`, `scan_for_secrets`) excludes
anything that looks secret (password, token, api_hash, session, tdata, auth_key,
verifier, …) before an export is written; the scan runs again before export. Sync
detects a **conflict** (local vs cloud revision) and refuses to overwrite silently;
restore is preview-first. The Consistency Auditor gained a config-sync provider
section (`5b-2`) that fails CI if a provider kind has no module or the bundle's
secret anchors disappear.

**Why.** Moving settings between the owner's own computers is genuinely useful, but
only if secrets, sessions and the database never travel. Encryption with a
password-derived key means even the provider (or Google) sees ciphertext.

**Consequence:** `services/config_bundle.py`, `services/config_sync_service.py`,
`providers/config_sync_base.py` + `config_sync_local.py` + `config_sync_gdrive.py`,
`db/models/config_sync.py`, `db/repositories/owners.py` (ConfigSyncRepository),
migration `20261007_1000_f8b2d3e5a7c9`; `/api/v1/owner/sync/*`; a `config_sync`
help topic, a capability (`config_sync`) and a Promotion Wizard step. No Telegram
session, TDATA or secret is ever included.


## D-107 — 2026-10-07 — Owner guard normalises the request path; config_sync has no `minimal` set (v1.6.1) — LOCKED

**Context.** An independent verification pass over the v1.6.0 Owner Auth + Config
Sync slice (no new features) found two real defects and one unwired control:
(a) `api/owner_guard.is_protected()` decided "is this an API path?" from the *raw*
`request.url.path` with `startswith`, so a request whose path began with a doubled
slash (`//api/v1/...`) was treated as a non-API path and skipped the guard, while
the router still normalised and matched it. (b) The `config_sync` capability
declared `minimal=(REQ_OWNER_AUTH,)`, so "owner ready but no provider connected"
reported `partial` even though nothing could be synced — contradicting D-106's
`needs_setup → available → error` states. (c) `OwnerView.vue` set
`showAdvanced = true` but the flag was never read and no token input existed, so
the existing `syncGoogleConnect` endpoint was unreachable from the UI.

**Decision.**
1. The guard **normalises before it decides**: it replaces backslashes, collapses
   runs of `/`, resolves `.`/`..` (`posixpath.normpath`), and then tests the
   `/api/` prefix. The allowlist is matched by **exact path or segment boundary**
   (`/health` matches `/health` and `/health/x`, never `/healthcheck`). A path the
   router cannot route still falls through to the SPA (never a false 401 on a
   non-API path). This is pure hardening: no API, token or allowlist semantics
   change, and the local-first default is unaffected.
2. `config_sync` drops the `minimal` set: it is `needs_setup` until a provider is
   connected, `available` when it is, `error` when it needs reconnection. A
   capability that cannot actually perform its action must never report `partial`.
3. The `/owner` Google Drive flow gets the missing token input + "save token"
   button wired to the **existing** `POST /api/v1/owner/sync/google/connect`
   endpoint. No new endpoint, no client secret in the bundle (D-106 stands).

**Consequences.** `tests/test_v16_verification.py` locks both behaviours: a
middleware-level test (synthetic ASGI scope) proves a raw `//api/v1/settings`
returns 401, and the capability test proves `config_sync` is never `partial`.
Nothing here searches for, downloads or bulk-registers accounts, and nothing
bypasses Telegram limits (D-006/D-070 stand).


## D-108 — 2026-10-07 — Release docs must name the shipped version; guarded by tests (clean-checkout verification of v1.6.1) — LOCKED

**Context.** A clean-checkout verification of the released tag `v1.6.1` (fresh
clone → `git checkout v1.6.1` → fresh venv, not the author's working tree) passed
every gate: `pytest` 843, `ruff` clean, `vue-tsc` + `npm run build` clean, Docker
build + smoke (`/health` → `1.6.1`, migrations applied), portable build/smoke (ZIP
1.6.1, app copy imports), meta-audit 25/25 (100%, 0 false positives), artifact scan
clean. **No code defect was found.** The only problem was documentation drift:
`agent/CURRENT_STATE.md` still read `Version string is **1.6.0**` / `main HEAD =
39efc37`, and `agent/NEXT_TASK.md` still announced `v1.6.0 is released` with `822
passed`; `docs/RELEASE_CHECKLIST.md` had no v1.6.1 section.

**Decision.** The release-hygiene tests are extended so this specific drift cannot
recur silently:
1. `test_memory_files_state_the_current_release` asserts the **first** `Version
   string…` anchor line in both `agent/CURRENT_STATE.md` and `agent/NEXT_TASK.md`
   contains the shipped `__version__` (historical lines legitimately name older
   versions, so only the current anchor is checked).
2. `test_release_checklist_covers_the_current_release` asserts
   `docs/RELEASE_CHECKLIST.md` has a `### vX.Y.Z ` verification section for the
   shipped version.

**Consequences.** `tests/test_meta_audit.py` already guarded the repo version
consistency, the README release string and the meta-audit report version; these add
the memory files and the release checklist. This is documentation/guard only — no
code, API, schema or dependency change, and no new release (v1.6.1 stays the
latest tag; these edits are `Unreleased` on `develop`).


## D-109 — 2026-10-08 — Bot Factory batch is a durable creation queue (v1.7, additive) — LOCKED

**Context.** v1.3 created a whole batch synchronously: one long request tried to
create every candidate at once. On a weak PC or a slow Telegram link this is
fragile — a tab close or a restart mid-batch left the owner unsure what had
happened, and a single failure had no bounded retry path separate from the rest
of the batch.

**Decision.** The batch becomes a **durable creation queue** (`QueueState`:
`pending → queued → running → success|failed`, plus terminal `skipped`/
`cancelled`), advanced by the scheduler job `bot_factory.create`:
1. `enqueue_candidates` marks candidates Telegram confirmed `available`/`ready`
   (and not-yet-checked `generated` ones) as `queued`; `run_queue_once` performs
   **one** creation operation per tick — the queue state lives in SQLite, so the
   batch is **restart-resumable** through the scheduler's normal recovery.
2. `queue_cancelled` stops the remaining work; **already-created bots are never
   rolled back**. `retry_candidate` re-queues a failed/cancelled operation (with a
   bounded attempt counter) and `skip_candidate` ends it without touching the rest.
3. **Deep-link batches are not background-ticked**: the owner completes them by
   hand in Telegram, so `_handle_bot_factory` only reschedules when the batch is
   not `via_deeplink`. This avoids an infinite tick for work the suite cannot do.
4. The queue only *prepares and drives* the official managed-bot flow. It never
   registers accounts, never bypasses FloodWait and never bypasses limits.

**Consequences.** New columns `bot_batches.queue_cancelled` and
`bot_candidates.queue_state`/`attempts`. New API endpoints
(`/batches/{id}/enqueue|cancel|resume`, `/candidates/{cid}/retry|skip`), the
`bot_factory` capability requirement, a Diagnostics check, a Promotion Wizard
step, a help topic and `BotFactoryView.vue` queue controls. Additive: an existing
v1.6 database upgrades in place.

## D-110 — 2026-10-08 — `token_mask` is display-only and derived without decryption — LOCKED

**Context.** After token registration the UI wanted to show *which* managed-bot
credential is stored, but the raw token is a secret that must never be returned,
logged or exported. Decrypting the sealed token just to build a mask would put the
plaintext in memory and risk a leak.

**Decision.** Store a non-reversible `token_mask` (`1234…xyz`) computed by
`mask_token` from the **numeric bot id** (a non-secret) plus the last four
characters of the id string — never by decrypting the sealed token.
`BotCandidate.token_mask` is the only token-derived field the API exposes, and it
is empty until tokens are fetched. `register_tokens` still returns a count only;
the raw token is written once through `BotService` and stays sealed.

**Consequences.** The Diagnostics report and every per-candidate payload carry
queue state, attempts and the mask — never a token, session or auth key (D-061).



## D-111 — 2026-10-09 — One AI Gateway over many providers, with honest routing — LOCKED

**Context.** The Suite already had an optional tiny classifier (rules + an
optional GGUF LLM) but no shared way to reach real AI providers. Each future
feature would otherwise wire its own vendor call, with its own key handling,
retry and error story, and the UI could not explain what was available.

**Decision.** Introduce a single **AI Gateway** (`backend/app/ai/gateway/`) that
the rest of the Suite calls instead of a vendor:

1. **Registry as the single extension point.** `registry.build_provider(config)`
   maps a `ProviderConfig` to an `AIProvider`; adding a kind is one branch.
   Kinds: `openai_compatible`, `openrouter`, `google`, `anthropic`, `deepseek`,
   `ollama` (local), `web` (browser wrapper).
2. **Router with reliability.** The router builds the eligible set (capability
   match → strategy order → priority), retries transient failures with **bounded
   backoff**, honours a **per-provider circuit breaker** and a **rate-limit
   cooldown**, and **fails over** to the next provider. `describe()` returns the
   planned order without executing. Nothing eligible → an honest `no_provider`
   result, never a silent empty success.
3. **Secrets stay sealed.** Provider keys are `seal_secret`-ed, registered with
   the logging redaction filter, and write-only (`has_key` boolean). The
   observability ring (`ai_gateway_requests`) stores **metadata only** — never
   prompt or response text.
4. **Honest availability.** A provider is `available` only after a real probe;
   the browser runtime reports engine/Docker status rather than claiming success.

**Consequences.** New tables `ai_providers` / `ai_route_settings` /
`ai_gateway_requests` (migration `20261008_1200_b2c3d4e5f6a7`), the
`ai_gateway` capability (requires an enabled `ai_provider`), a consistency anchor,
i18n keys, the `/ai-gateway` UI and two help topics. Additive: an existing v1.7
database upgrades in place and the rules/encoder path is unchanged.

## D-112 — 2026-10-09 — Web wrappers use the owner's own session and never bypass a wall — LOCKED

**Context.** A "web wrapper" turns a website's chat UI into an API-shaped
provider, which is attractive for free access — but it sits next to a line the
project will not cross: no bypassing of login, CAPTCHA, MFA, verification,
regional blocks or Telegram limits, and no use of someone else's session.

**Decision.** A wrapper is a declarative `WrapperDefinition` (URL, open steps,
input/send/response selectors, extraction, login markers, version, cost) executed
by `WebWrapperEngine` against the owner's **own** browser session (optional
Playwright runtime, fake runtime for tests). On a login marker the engine returns
`AUTH_REQUIRED` and **stops** — it never enters credentials, solves CAPTCHA or
attempts MFA. When the browser runtime is unavailable the wrapper reports honest
unavailability; it never claims a capability that was not probed. No selector
lives in business logic, and no wrapper credential is returned or logged.

**Consequences.** The `web` provider kind and the wrapper library/`/browser`
status endpoints are additive and off by default (`ai_gateway_web_enabled`).
Wrapper definitions are honest templates until a real probe verifies them.

## D-113 — 2026-10-09 — Gateway costs and modalities are opt-in, never assumed — LOCKED

**Context.** A gateway that silently picks a paid provider or a browser session
would spend the owner's money or reach the network in a way they did not expect.

**Decision.** Routing excludes **paid** providers unless `ai_gateway_allow_paid`
is on, and excludes **web wrappers** unless `ai_gateway_web_enabled` is on. The
strategy (`auto`, `free_first`, `cheapest`, `fastest`, `best_quality`, `manual`)
is a stored preference; `manual` only uses an explicitly named provider. The
use-case matrix reports availability per modality from the same evaluated state,
so the UI cannot show a use-case as available when no provider satisfies it.

**Consequences.** Safe defaults (paid off, web off) mean a fresh install never
spends money or opens a browser. Settings are per-installation and ride the
existing settings service; no new heavy infrastructure.

## D-114 — 2026-10-10 — Gateway availability and retries are proven by behaviour, not by flags — LOCKED

**Context.** v1.8.0 shipped the AI Gateway and claimed "a provider/wrapper is
`available` only after a real probe" and that transient failures are retried with
bounded backoff. An independent verification found the code did not keep those
promises on two paths: a `web` provider with a missing wrapper definition was
still reported `available`, and `AIRouter._attempt` returned a transient
*response* without retrying (only raised errors were retried).

**Decision.** A gateway guarantee must be enforced in code and locked by a test:

1. **Availability is computed, never read from a stored flag.** A provider or
   wrapper is `available` only when `availability().usable` is true at evaluation
   time. A `web` provider whose `wrapper_id` has no matching `WrapperDefinition`
   is forced `unavailable` with the reason "определение обёртки … не найдено".
   The `web:<id>` label is a fallback only — a configured provider keeps its
   configured name so a pinned provider still routes by name.
2. **Retries cover every transient failure shape.** A provider may fail
   transiently by *raising* a `GatewayError` (transport) or by *returning* a
   non-ok `ChatResponse` with a transient status (a mapped HTTP 5xx/429/timeout).
   `AIRouter._attempt` retries both, bounded by the retry budget
   (`ai_gateway_max_retries` / `retry_delays`), then fails over. No unbounded
   retry, no infinite loop.
3. **A raised browser exception is classified, not allowed to crash the gateway.**
   A mid-pipeline wrapper error becomes a classified failure at the provider
   boundary so the router can move on.
4. **Version strings are consistent across all manifests** (app, `pyproject.toml`,
   `package.json`, `package-lock.json`), asserted by `test_repo_version_is_consistent`.

**Consequences.** These are locked invariants: the gateway meta-audit adds three
cases (capability dependency, orphan provider class, unwired control) and the
behaviour tests above fail if a future change re-introduces a decorative retry or
a flag-based availability. No new features, no schema change, no new dependency.

---

## D-115 — 2026-10-11 — The wrapper pipeline is verified on practical scenarios, not by compiles — LOCKED

**Context.** After v1.8.1 the Web Wrapper Hub was "architecturally implemented"
but had not been exercised on *practical* scenarios end to end. A verification
pass over the real engine→provider→router pipeline found that the **genuine**
Playwright runtime's `extract()` read `href` from the matched node itself, so
extracting a container (`li.link`, `tr.row`) returned empty links — a real defect
visible only when the real browser ran.

**Decision.**

1. **The wrapper pipeline is verified with a deterministic local fixture.** A
   local `127.0.0.1` HTTP server (`tests/support/web_fixtures.py::FixtureSite`)
   serves fixed HTML and `FixtureBrowserRuntime` performs a **real HTTP GET** and
   parses the returned HTML. Tests, the benchmark and CI use it — no external
   site, account, key or AI credential, and no browser binary required.
2. **The genuine browser layer is verified too, but optional.** A real headless
   Chromium test (`tests/test_web_wrapper_playwright_integration.py`) runs the
   same scenarios and **skips** when Playwright/Chromium is absent, so CI without
   a browser stays green. Playwright is never imported at startup; the browser is
   optional and reports honest unavailability when missing.
3. **Structured extraction is configurable and strict.** `WrapperDefinition`
   carries `extraction="structured"` + `extract_attrs` (default `("href",)`); the
   engine calls `BrowserRuntime.extract(selector, attrs=...)`. Extraction prefers
   a nested `<a>` for the link. A structured extraction with **no** matching node
   reports `wrapper_selector` — never fabricated data. A *text* extraction with no
   match honestly returns the page text.
4. **Honesty is itself tested.** Login pages are detected and **not** bypassed; a
   transport failure is surfaced; the capability matrix never offers a text-only
   provider for image or structured cases; `diagnostics()` / `wrapper_library()` /
   `ProviderView` contain no key value, cookie, profile path or session string.

**Consequences.** `PYTHONPATH=. python tests/web_wrapper_bench.py` reports 7/7 and
writes `agent/WEB_WRAPPER_BENCHMARK.json`; the CI-safe pytest modules assert the
same scenarios and the failure paths. Any future change that re-breaks real link
extraction or fabricates structured data fails these tests. No new runtime
dependency and no schema change.

**Release.** Shipped as **v1.8.2** via a reviewed `develop → main` PR #21 (merge
`8542d4c`), tag `v1.8.2`; the Release workflow (run `37747125558`) created the
GitHub Release and attached the Windows portable ZIP (24 906 383 bytes, sha256
`f0c6984d…f619`) + `.sha256`. Gates: full suite green (**943 passed**), `ruff`
clean, `vue-tsc` + `npm run build` clean, meta-audit 30/30 (0 missed, 0 false
positives). `main` HEAD = `8542d4c`; `develop` is ahead of `main` only by
documentation/memory-only commits (`ab2c120`, `acf9de4`, …) with no code change.


---

## D-116 — 2026-10-12 — Content Operations 2.0 extends the one studio; the mini-AI classifies, it never chooses — LOCKED

**Context.** The product brief for the v1.9 cycle asks for a *single* content
pipeline — `source -> gather -> clean -> mini-AI -> moderation -> publish ->
comment/delete` — with reusable AI profiles, human moderation, declarative
automation rules and analytics. The risk is a second, parallel "Content Studio"
that forks behaviour and drifts. A second risk is pretending a small encoder
model (ruBERT-tiny2 class) can *generate* exact structured output, or letting an
AI pick an emoji.

**Decision.**

1. **One studio, additive only.** The v1.9 work extends the existing Content
   Studio (`ContentStudioView.vue`, `/api/v1/content/*`, `content_items`). No
   second studio, no parallel route tree, no duplicated posting path. Every schema
   change is an additive column/table with a server default, so an existing v1.8
   database upgrades in place (`20261012_0900_c3d4e5f6a7b8_v1_9_content_operations.py`).
2. **The prompt is data, not code.** `AiProfile` (key/title/language/tone/
   max-length/instructions/provider-policy/actions) is a row, not a constant.
   Built-in profiles are seeded and **delete-protected**; the action list is
   validated against a fixed allow-list, so an unknown action is dropped, never
   executed.
3. **Rules are declarative, not a script engine.** `AutomationRule` matches on a
   fixed condition vocabulary (`contains`/`not_contains`/`min_length`/`max_length`/
   `language`) and performs a fixed allow-list of pipeline actions. There is no
   `eval`, no arbitrary code and no expression language.
4. **The mini-AI classifies; it never chooses.** `ContentPipelineService.classify`
   returns only a **category** and an **intent** (advisory, `ai_status`). It never
   selects an emoji or a reaction: the reaction engine intersects the profile's
   allowed reactions with the channel's actually-available ones (D-033). The model
   is an **encoder** used with prototype/nearest-prototype labels over a small
   seeded Russian example set — it is not treated as a generative LLM and is never
   asked to emit JSON.
5. **An AI failure never loses material.** If the gateway has no live provider,
   `process` moves the item to `NEEDS_REVIEW` with `ai_status = ai_unavailable`
   and a plain note; the original text is preserved in `original_text`. No silent
   drop, no fabricated output.
6. **Analytics are metadata only.** `content_operations` records stage/status/
   provider/model/latency/attempts/detail — never prompt text, keys, tokens or
   audience data. Comment and auto-delete are tracked independently
   (`comment_status`, `delete_status`) so a lost step never marks a publication
   `failed`.

**Consequences.** The full suite is **954 passed**; `ruff` clean; `vue-tsc` +
`npm run build` clean; meta-audit **30/30 (0 missed, 0 false positives)**. New
tests in `tests/test_content_operations.py` cover profiles, moderation, rule
matching and analytics against a temporary SQLite DB with no real accounts,
credentials, SMS or registration flow. A future change that adds a second studio,
hardcodes prompts, lets the AI pick an emoji, or destroys material on AI failure
fails these decisions.

**Release.** Shipped as **v1.9.0** via a reviewed `develop -> main` PR (D-060),
tag `v1.9.0`; the Release workflow attaches the Windows portable ZIP + `.sha256`.
