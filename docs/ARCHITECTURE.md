# Architecture — Telegram Channel Management Suite

Status: **Phase 0 (documentation & foundation)** — see `agent/CURRENT_STATE.md`.
This document is the single source of truth for the system architecture.
If it disagrees with the code, the code wins — then fix this document.

---

## 1. Purpose

A modular, locally runnable **Telegram Channel Management Suite** for a single
channel owner, designed so it can later scale to many bots/accounts without a
rewrite. It manages:

- a control **manager bot**;
- **managed bots** (Telegram Bot API "managed bots" feature);
- **user accounts** (MTProto / Telethon sessions);
- **audience** parsing and storage;
- **invites** into a target channel;
- **automatic reactions** to channel posts using multiple bot identities;
- a **rules engine** + optional **tiny AI classifier** for post categorization;
- **analytics** for content and audience;
- **queues / scheduler** resilient to restarts;
- **logs / error center**, **backup / restore**, **setup wizard**.

It runs on a weak Windows PC (portable), on Linux, and on a VPS via Docker —
all from **one codebase**.

---

## 2. High-level architecture

```
                       ┌──────────────────────────────────────────┐
                       │              Clients                      │
                       │  Local Web UI (browser, 127.0.0.1)        │
                       │  Telegram Mini App (same SPA, HTTPS)      │
                       │  Manager Bot (Telegram chat)              │
                       └───────────────┬──────────────────────────┘
                                       │ HTTP/JSON  +  Bot API
                                       ▼
                       ┌──────────────────────────────────────────┐
                       │        FastAPI application (backend)      │
                       │  REST API  ·  static SPA hosting          │
                       │  auth  ·  validation  ·  OpenAPI          │
                       └───────┬───────────────┬──────────────────┘
                               │               │
             ┌─────────────────▼──┐   ┌────────▼─────────────────┐
             │  Domain services   │   │  Telegram Adapter layer  │
             │  (business logic)  │   │  (interfaces + impls)    │
             │  reactions, rules, │   │  BotProvider             │
             │  audience, invites,│   │  UserProvider            │
             │  analytics, ai     │   │  SessionProvider         │
             └─────────┬──────────┘   │  AudienceProvider        │
                       │              │  ReactionProvider        │
                       │              └────────┬─────────────────┘
                       │                       │
             ┌─────────▼──────────┐   ┌────────▼─────────────────┐
             │  Persistence        │   │  Fake/Test providers      │
             │  SQLAlchemy +       │   │  (used by the test suite, │
             │  SQLite (aiosqlite) │   │   no real Telegram needed)│
             └─────────┬──────────┘   └──────────────────────────┘
                       │
             ┌─────────▼──────────┐
             │  Scheduler / Queue  │
             │  asyncio + APSched. │
             │  DB-backed jobs     │
             └────────────────────┘
```

### Key rule
**Telegram implementation details never leak into domain logic.** Every external
Telegram capability is reached through an abstract *provider* interface
(section 5). This is what makes the fake provider, the portability, and future
PostgreSQL swap possible.

---

## 3. Technology stack

| Layer            | Choice                                  | Rationale |
|------------------|-----------------------------------------|-----------|
| Backend          | Python 3.11+ / FastAPI                  | async, typed, single-file OpenAPI |
| Bot API          | aiogram 3.x                             | stable, async, managed-bot friendly |
| MTProto          | Telethon                                | mature user-account client |
| ORM              | SQLAlchemy 2.x (async)                  | swappable engine, async |
| DB (default)     | SQLite via `aiosqlite`                  | zero-install, portable |
| Migrations       | Alembic                                 | schema evolution without data loss |
| Scheduler        | APScheduler + asyncio                   | no Redis/Celery needed |
| Frontend         | Vue 3 + Vite + TypeScript               | lightweight SPA, builds to static files |
| Frontend serving | FastAPI StaticFiles                     | production needs no Node.js |
| AI (optional)    | llama.cpp + tiny GGUF (~0.5–1B)         | optional, fully disableable |
| Packaging        | PyInstaller (portable) + Docker         | one codebase, two runtimes |

### Explicitly NOT used (Phase 0–1)
Redis, Kafka, Celery, PostgreSQL, Kubernetes. Added only if a real need appears.
**SQLite must be replaceable with PostgreSQL without touching business logic** —
this is enforced by keeping all DB access behind the repository/service layer
and never writing SQLite-specific SQL in domain code.

---

## 4. Repository layout

```
Telegram-Channel-Management-Suite/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app factory + startup/shutdown
│       ├── core/                # config, logging, security, paths
│       ├── db/                  # engine, session, base, models, repositories
│       ├── api/                 # routers (v1) + schemas (pydantic)
│       ├── services/            # domain/business logic
│       ├── providers/           # Telegram adapter interfaces + impls + fakes
│       ├── scheduler/           # queue + jobs
│       └── static/              # built frontend output (generated, ignored)
├── frontend/                    # Vue 3 + Vite + TS source
├── tests/                       # unit / db / api / scheduler / portable tests
├── docs/                        # ARCHITECTURE, ROADMAP, SETUP, SECURITY, UI, API, TROUBLESHOOTING
├── agent/                       # persistent agent memory (state, tasks, decisions, changelog)
├── scripts/                     # dev/ops helper scripts
├── docker/                      # Dockerfile, docker-compose.yml
├── portable/                    # Windows portable build assets + run.bat
├── data/                        # mutable runtime data (gitignored)
├── sessions/                    # MTProto .session files (gitignored, never in image)
├── backups/                     # generated backups (gitignored)
├── logs/                        # log files (gitignored)
├── exports/                     # user exports (gitignored)
├── .env.example                 # documented config template
└── .gitignore                   # protects secrets/sessions/data
```

Runtime mutable state is always under predictable directories (`data/`,
`sessions/`, `backups/`, `logs/`, `exports/`). Portable mode keeps everything
relative to the extracted folder.

---

## 5. Provider / adapter abstraction

Interfaces (abstract base classes / Protocols) live in `backend/app/providers/`:

| Interface             | Responsibility | Real impl | Test impl |
|-----------------------|----------------|-----------|-----------|
| `TelegramBotProvider` | Bot API: getMe, send, health, managed bots | `AiogramBotProvider` (aiogram) | `FakeTelegramBotProvider` |
| `TelegramUserProvider`| MTProto: auth, resolve, parse, invite | Telethon (PHASE 4) | `FakeUserProvider` |
| `SessionProvider`     | create/list/revoke/health of sessions | Telethon files (PHASE 4) | `FakeSessionProvider` |
| `AudienceProvider`    | enumerate members of a source | Telethon (PHASE 5) | `FakeAudienceProvider` |
| `ReactionProvider`    | apply a reaction to a message | aiogram (PHASE 3) | `FakeReactionProvider` |

`providers/registry.py` resolves the correct implementation from config
(`telegram_provider`: `auto` | `aiogram` | `fake`; `offline_mode` forces the
fake). Providers translate library exceptions into `providers/errors.py`
(`InvalidTokenError`, `FloodWaitError`, `UnauthorizedError`, …) carrying a
friendly message and a how-to-fix hint, so no library type or raw error leaks
into services. Domain services **only** depend on interfaces, so swapping
Telegram libraries or running everything against fakes is a config/DI concern.

Implemented (PHASE 2): `TelegramBotProvider` only. `AiogramBotProvider` wraps
aiogram and covers the official managed-bot methods (`getManagedBotToken`,
`replaceManagedBotToken`, `get/setManagedBotAccessSettings`).

Implemented (PHASE 4): `SessionProvider` (`providers/session_base.py`) with
`TelethonSessionProvider` (the **only** Telethon importer; builds a client,
connects, runs one operation, disconnects — lazy per-operation, D-023) and
`FakeSessionProvider` (deterministic, no I/O). It already exposes the operations
PHASE 5/6 need (`resolve_entity`, `get_participants`, `invite_to_channel`), so
audience parsing and invites build on the same interface rather than adding new
Telegram touch-points.

### Account Hub — local session import (v1.1)

`services/session_import.py` adds one `SessionImportProvider` protocol with four
providers so the owner can bring an account they already control: Telethon
`.session` (SQLite header), `.session` + companion JSON (whitelisted keys only),
StringSession and Telegram Desktop TDATA. Detection (`detect_format`) reports the
format and a state (`valid`/`damaged`/`unauthorized`/`unknown`) before import.
Import is local-only and owner-scoped; a StringSession string and TDATA auth data
are written to `SESSIONS_DIR` (gitignored) and never logged, returned or shown
(D-070). TDATA is optional: with no reliable converter it reports an honest
`NOT AVAILABLE` and the source folder is never modified or uploaded.

The optional **network route (proxy)** is a plain connection route stored in
`proxy_profiles` and bound via `user_sessions.proxy_id`; it never bypasses
Telegram limits (D-065). `services/encoder_service.py` provides the optional
lightweight-encoder install flow described in §7.1.

Implemented (PHASE 5): `AudienceProvider` (`providers/audience_base.py`) with
`SessionAudienceProvider` (`providers/session_audience.py`) — a thin adapter that
delegates to the PHASE 4 `SessionProvider` (so it never imports Telethon itself)
— and `FakeAudienceProvider` (pure, offline). `registry.build_audience_provider`
selects the real adapter or the fake from config. The scanner consumes the
interface one bounded page at a time, so the member list is never fully
buffered.

---

## 6. Data model (initial)

Core tables (SQLAlchemy models in `backend/app/db/models/`):

- `bots` — manager + managed + ordinary bots. Fields: `kind`, `enabled`,
  `telegram_id`, `username`, `title`, `token_encrypted` (sealed, never plain),
  `provider_name`, `owner_id`/`owner_username`, `can_manage_bots`,
  `health` (`unknown|ok|warning|error`), `health_message`, `health_hint`,
  `last_error`, `last_health_at`. **Implemented (PHASE 2).**
- `accounts` — user accounts. Fields: `phone_encrypted` + `phone_masked`,
  `api_id`, `api_hash_encrypted` (sealed), `session_ref` (UUID basename in
  `SESSIONS_DIR`), `telegram_user_id`, `username`, `display_name`,
  `status` (`online|auth_required|disconnected|flood_wait|error|disabled`),
  `auth_step` (`idle|code|password|done`), `enabled`, `last_error`,
  `last_checked_at`. **Implemented (PHASE 4).**
- `sources` — audience sources. Fields: `reference`, `username`, `telegram_id`
  (unique), `source_type` (`channel|group|entity|unknown`), `enabled`,
  `account_id`, `scan_status` (`idle|scanning|paused|completed|failed|cancelled`),
  `completeness` (`unknown|complete|partial|no_access|failed`), `scanned_offset`
  (resume point), `discovered_count`/`new_count`/`duplicate_count`/`error_count`,
  `reported_total`, `scan_job_id`, `last_error`, scan timestamps.
  **Implemented (PHASE 5).**
- `audience_users` — parsed users (dedup key = unique `telegram_user_id`).
  Fields: `username`, names, `phone_masked` (masked only; full phones never
  stored), `is_bot`/`is_deleted`/`is_premium`, `status`
  (`active|blocked|deleted|unknown`), `score` + `score_reason`, `tags` (JSON
  list), plus neutral `invite_*` extension fields for PHASE 6.
  **Implemented (PHASE 5).**
- `source_user_links` — many-to-many membership (`source_id`, `user_id`,
  `discovery_method`, timestamps; unique per pair) so a person found in several
  sources stays a single row. **Implemented (PHASE 5).**
- `invite_jobs` / `invite_tasks` — invite queue with per-user status.
- `posts` — channel posts (content, category, tone, confidence).
- `reaction_jobs` — per post/bot/reaction scheduled reaction (section 8).
- `reaction_profiles` — named reaction configurations.
- `rules` / `rule_categories` — editable categorization rules.
- `settings` — UI-editable configuration (key/value, typed).
- `events` — log/error center entries.
- `job_queue` — durable queue rows for restart recovery.

All models use a shared declarative `Base`, UUID/str primary keys where
appropriate, and `created_at`/`updated_at` timestamps.

---

## 7. Rules Engine + Tiny AI

Classification workflow:

```
Post text
  → Rules Engine (keywords / phrases / optional regex, per-category priority)
      → if confidence >= category.minimum_confidence → category (fast path)
  → else if AI enabled → encoder (ruBERT-tiny2) or Tiny GGUF classifier
      → {category, tone, intent, confidence}
  → else → "neutral" fallback
  → Reaction Profile (deterministic weighted emoji choice)
      ∩ intent allowed (when the AI reported a non-neutral intent)
      ∩ channel available reactions (when verified)
      ∩ bot-compatible reactions   (when verified)
      − forbidden reactions
```

Rules are **data, not code**: editable from the Web UI, stored in DB.
Categories (minimum set): `donation, news, funny, sad, angry, cute, support,
announcement, neutral`.

The AI returns **strict structured JSON** and is used **only** to pick a
category/tone/intent/confidence. Emoji selection is **always deterministic
weighted logic**, never the LLM (D-032/D-033). AI can be disabled entirely
(`AI_ENABLED=false`).

Implemented (PHASE 7) in `backend/app/ai/` — free of Telegram/FastAPI imports:

- `types.py` — `Classifier` Protocol and `ClassificationResult`
  (`category`, `tone`, `intent`, `confidence`, `source`; `source` ∈
  `rules`/`llm`/`encoder`/`manual`/`fallback`/`default`).
- `classifiers.py` — `RulesClassifier` (wraps the Rules Engine),
  `LlmClassifier` (prompt → `run_bounded` → strict parse), `FakeClassifier`.
- `schema.py` — tolerant about framing, strict about values; invalid JSON/unknown
  category/tone/out-of-range confidence ⇒ `InvalidModelOutputError`.
- `router.py` — `RoutingClassifier`: rules fast path (`ai_rules_threshold`),
  then AI only when unsure (`ai_confidence_threshold`), else graceful fallback.
  `RoutingOutcome` records `ai_attempted`/`ai_used`/`fallback_used`.
- `inference.py` — one shared single-worker executor (`run_bounded`); a timeout
  raises `InferenceTimeoutError` and shut down on app exit.
- `backends/` — registry (`build_backend`): `fake` (deterministic, offline/tests),
  `llama_cpp` (the only `llama_cpp` importer; lazy, lock-serialized, optional) and
  `rubert` (the optional ruBERT-tiny2 encoder backend, below).

### 7.1 Lightweight encoder classifier (v1.1)

`backend/app/ai/encoder.py` adds a **dependency-free** encoder classifier: text →
hashing embedding → nearest prototype (cosine) → category/tone/intent. It needs
**no model file and no download**, so it works on the weakest Windows PC, and it
is the default `encoder` mode (`auto` uses rules first, then this). Every failure
degrades to the rules result.

`EncoderClassifier` is swappable via an `EncoderBackend` protocol
(`backend/app/ai/backends/encoder_base.py`). The optional `rubert` backend
(`cointegrated/rubert-tiny2`, MIT, ~115 MB) is loaded **lazily, CPU-only, one
inference at a time, and unloaded when idle** (D-019/D-035); it is never a hard
dependency. Because ruBERT-tiny2 is an *encoder*, not a generative model, it is
used for embeddings only — the prototype/KNN classification stays in
`EncoderClassifier` (D-068). `backend/app/services/encoder_service.py` provides
the install experience (download official files → verify SHA-256 → try a real
load → honest status), reachable at `/api/v1/ai/encoder/*` and the «Мини-ИИ» UI.

### 7.2 Intent → reaction policy (v1.1)

`backend/app/services/reaction_intent.py` maps a communicative intent
(`support`/`sympathy`/`joy`/`humor`/`anger`/`surprise`/`love`/`neutral`) to the
emoji it permits. Intent only *narrows* the set (never chooses one); a neutral
intent does not restrict. The planner intersects profile-allowed ∩ intent-allowed
∩ channel-available ∩ bot-compatible − forbidden, and skips (with a reason) when
nothing remains (D-032).

Configuration is read through `AiService.effective()` so DB settings override env
defaults (D-034). Models are user-provided `.gguf` assets in the gitignored
`/models/` directory — never committed, never auto-downloaded. Modes: `auto`
(default), `rules`, `ai`.

---

## 8. Analytics

Analytics is a **read-only** layer over data the suite already stores; it has no
Telegram imports and no write path (D-036):

- `db/repositories/analytics.py` — `AnalyticsRepository`: aggregates over
  `posts`, `reaction_jobs`, `audience_sources`/`audience_users`/
  `audience_source_users`, and `invite_tasks`. Per-day series are bucketed in
  Python from a bounded window (`_buckets`/`_day_key`) so the same queries work on
  SQLite today and PostgreSQL later (D-002).
- `services/analytics_service.py` — `AnalyticsService`: `content()`,
  `reactions()`, `audience()`, `overview()`; RU plain-language summaries,
  percent-change vs. the previous window, titled counts.
- `api/v1/analytics.py` — `GET /api/v1/analytics/{overview,content,reactions,audience}`.

The backend owns the explanatory copy, so the Web UI and the Mini App render the
same wording from one API (D-003). Charts are dependency-free inline SVG
(`Sparkline.vue`, `BarList.vue`, D-037). Responses contain only aggregate counts —
no secrets and no per-person PII.

---

## 8a. Telegram Mini App (PHASE 9)

The Mini App is **not a second application**: the same Vue SPA and the same API
serve both the local Web UI and Telegram (D-003). Only authentication is added:

- `backend/app/miniapp/auth.py` — `verify_init_data()`: verifies the Telegram
  `initData` HMAC-SHA256 signature (`HMAC_SHA256(bot_token, "WebAppData")`),
  rejects stale/future `auth_date`, parses the user. Pure, no FastAPI/Telegram
  imports, so it is unit-testable in isolation.
- `backend/app/miniapp/sessions.py` — signed session tokens (HMAC key derived
  from `APP_SECRET_KEY` via `derive_key`); no JWT dependency.
- `backend/app/miniapp/service.py` — `MiniAppService`: reads the manager bot
  token from the sealed DB row, applies the owner allow-list, issues sessions,
  and reports plain-language availability.
- `api/v1/miniapp.py` — `GET /config`, `POST /auth`, `GET /me`, `POST /logout`.
  Business endpoints stay shared with the Web UI.

Frontend: `src/telegram.ts` wraps the Telegram WebApp SDK; `stores/miniapp.ts`
bootstraps auth only when `initData` is present; `App.vue` shows a friendly gate
while loading/failing and switches to a mobile bottom-nav layout inside Telegram.
The Setup Wizard gains a `miniapp` check. Secrets and raw `initData` are never
logged or returned (D-038).

---

## 8b. Backup / restore & portable layout (PHASE 10)

Backup is a self-contained, portable artefact rather than a service dependency:

- `services/backup_service.py` — `BackupService`:
  - `create_backup()` writes one `.tcmsbak` zip: `manifest.json` (version,
    timestamp, `includes_sessions`) + `data/app.db`. Filenames are unique and
    `backup_retention` prunes older files.
  - `restore_backup()` first writes a **safety backup** of the current state, then
    replaces the database (and session files only if the archive contains them).
  - `export_config()` / `import_config()` move user-owned rows
    (`settings`, `reaction_profiles`, `reaction_rules`) as reviewable JSON. The
    `bots` and `user_sessions` tables (sealed tokens / session refs) are excluded
    (D-039).
  - `_safe_member_path()` rejects path traversal.
- `api/v1/backup.py` — `/api/v1/backup` (info/list/create/download/restore/delete)
  and `/api/v1/backup/config/{export,import}`.

Portable layout (D-040): code under `app/`, mutable state at the distribution
root selected by `TCMS_ROOT` (`data/`, `sessions/`, `backups/`, `logs/`,
`exports/`, `models/`). `paths.static_dir()` resolves package-relative so the SPA
is served regardless of layout. `portable/run.bat` sets `TCMS_ROOT` + `PYTHONPATH`
and opens the browser; `portable/stop.bat` calls the local shutdown endpoint.
`scripts/build_portable.sh` assembles the tree and, by default, stages the
Windows embeddable Python + dependencies via `scripts/fetch_embedded_python.sh`
so the result is zero-setup (`--no-runtime`/`SKIP_RUNTIME=1` opts out for
restricted networks).

---

## 9. Reaction Manager & scheduler

One bot can place **one** reaction per message. A `reaction_job` row stores:
`post_id, bot_id, reaction, scheduled_at, status, attempts, error, completed_at`.

Planner properties (all configurable): allowed emojis, weights, reaction
probability, min/max delay, delay ranges, randomization, skip probability,
per-bot enable/disable, reaction profiles, preview/simulation.

The scheduler **never fires all reactions at once** — it spreads them using the
configured randomized delays. Jobs are persisted so an app restart can resume
pending work (`pending`/`scheduled` rows are re-hydrated on startup).

---

## 10. Reliability principles

1. Telegram specifics stay behind providers.
2. AI is optional and replaceable.
3. SQLite → PostgreSQL without rewriting business logic.
4. Web UI and Mini App share **one** API and **one** SPA.
5. Windows and Linux share **one** backend.
6. Configuration editable via UI (backed by `settings` table).
7. No hardcoded credentials — `.env` / OS secret store.
8. No global mutable application state — DI via app state / services.
9. Queues survive restart (DB-backed `job_queue`).
10. After a crash the app recovers unfinished jobs.

### Telegram server limits (non-negotiable)
We **never** attempt to bypass FloodWait, privacy restrictions, or admin
restrictions. On FloodWait the affected account/queue is **paused** and the wait
time is shown to the user. Privacy errors are stored as the user's status.

---

## 11. Deployment targets

| Target            | Entry point            | Notes |
|-------------------|------------------------|-------|
| Local (dev)       | `uvicorn` / `python -m app` | http://127.0.0.1:8000 |
| Windows portable  | `portable/run.bat`     | embedded Python, no Node/Docker |
| Linux             | systemd / script       | same backend |
| VPS / Docker      | `docker/docker-compose.yml` | HTTPS via reverse proxy |

Portable layout target:

```
TelegramChannelManagementSuite/
  app/  runtime/  data/  sessions/  backups/  logs/  exports/
  run.bat  stop.bat  README.txt
```

### Docker / VPS (PHASE 11)

One image, one process — the same codebase as local/portable (D-004):

- `docker/Dockerfile` — multi-stage: Node builds the SPA, then a `python:3.12-slim`
  runtime copies `backend/` + the built static files and runs as non-root (uid
  10001). No Node at runtime.
- `docker/docker-compose.yml` — one `app` service; optional `.env`; bind-mounted
  mutable state (`data/`, `sessions/`, `backups/`, `logs/`, `exports/`); healthcheck
  on `/health`; `restart: unless-stopped`; publishes `127.0.0.1:8000` only.
- `docker/docker-compose.proxy.yml` + `docker/Caddyfile` — optional TLS overlay;
  Caddy obtains/renews Let's Encrypt certificates and proxies to `app:8000`. An
  nginx example is documented in `docs/SETUP.md`.
- Production config is entirely environment-driven (`APP_ENV=production`,
  `APP_HOST=0.0.0.0`, `APP_SECRET_KEY`, `DATABASE_URL`); set
  `MINIAPP_PUBLIC_URL`/`MINIAPP_ENABLED` to enable the Mini App over HTTPS.
- Verified: image builds, container serves `/health`, the SPA, and the backup API.

---

## 12. Security model

- Secrets never committed (`.gitignore` + `.env.example`).
- Tokens/sessions never printed to console, UI, logs, exceptions, or API responses.
- Session files: separate directory, gitignored, excluded from Docker images,
  owner-labelled, revocable, health-checkable.
- Windows: OS-protected secret storage where available.
- VPS: environment variables / secret files.
- See `docs/SECURITY.md` for the full policy and review checklist.

---

## 13. Extension points

- New Telegram provider implementations (e.g. a second Bot API library).
- New classification backends behind the same classifier interface.
- New reaction strategies behind the planner interface.
- New deployment targets without changing the backend.

---

## 14. Hardening subsystems (post-1.0)

Committed after the PHASE 0–11 roadmap and RC pass, keeping every Telegram call
behind the existing providers (D-001).

**Permission probe.** `PermissionService` asks a user account (through
`SessionProvider`) to resolve a channel, read its participants and confirm invite
rights, then stores a `PermissionCheck` row. Every outcome — including
`flood_wait`, `admin_required`, `privacy_restricted` — is surfaced as an honest,
plain-language status (never bypassed, D-006). Exposed at `/api/v1/permissions/*`
and in the Sessions page.

**Manager-bot runtime + notifications.** `backend/app/manager/` adds:

- `bus.py` — an in-process, bounded, non-blocking notification bus. Publishing
  never raises, so a notification problem can never break a task. Categories
  (`system`, `telegram`, `reactions`, `audience`, `invites`, `ai`) map from event
  modules.
- `service.py` — `ManagerBotService`: an admin whitelist (from
  `MANAGER_BOT_ADMIN_IDS`), plain-language RU commands, provider construction from
  the stored manager bot, and delivery of pending notifications.
- `runtime.py` — `ManagerBotRuntime`: one asyncio task that short-polls the
  manager bot, dispatches authorized commands, and flushes notifications. It is
  off by default in tests, backs off when Telegram is unreachable, and never
  blocks the durable scheduler.

`EventsService` publishes ERROR/CRITICAL events to the bus automatically, and
lifecycle events (app start/stop, backup created, AI warnings) publish explicitly.
Notification toggles reuse the existing `settings` table — no new storage.

---

## 15. Diagnostics (v1.0.3, D-061)

The owner-facing counterpart to the Setup Wizard: a read-only view of system
state plus a safe, redacted support artifact.

- `core/redaction.py` — the single redaction policy: masks live configured secrets
  and pattern-matched values (bot tokens, `api_hash`/`api_id`, Telethon session
  strings, E.164 phones, long hex/base64), drops forbidden keys entirely, and
  exposes `scan` (findings) + `redact_and_verify` (redact then re-scan as a safety
  gate).
- `services/diagnostics_service.py` — `DiagnosticsService.collect()` aggregates
  one explained status per subsystem (application, database + migration state,
  Telegram API, manager bot, managed bots, sessions, channels, audience, reactions,
  invites, AI, scheduler/queue, storage, portable runtime), reusing
  `SystemService` checks where they exist. `build_report()` produces a redacted
  JSON/TXT/ZIP; `run_action()` runs the non-destructive maintenance actions.
- `scheduler/handlers.py` — `register_handlers(scheduler)` hoists the durable-queue
  wiring out of `main.py` so a UI scheduler restart (an action) reuses it exactly.
- `api/v1/diagnostics.py` — the router; `api/deps.py::get_diagnostics_service`.

The report is a *shareable* artifact: it never contains tokens, keys, session
data, phone numbers, passwords, database contents or audience records, and the
API refuses to return a file that fails the safety scan.

---

## 16. Content Studio (v1.2.0, D-071…D-076)

A content pipeline that turns material from sources into scheduled posts on the
owner's own channels. It reuses the existing provider seams (no new Telegram
client): Telegram reads go through `SessionProvider`, publishing goes through a
`PostingProvider` that wraps either `TelegramBotProvider` (bot mode, the default)
or `SessionProvider` (expanded mode).

- `db/models/content.py` — `ContentSource`, `ContentItem`, `MediaAsset`,
  `Publication`, `ButtonSet`, `CommentPlan` (+ enums: source kind/status, rights
  status, item status, publication status). Additive migration
  `20261005_1200_c4a1f8b2e6d9`; an existing v1.1 database upgrades in place.
- `db/repositories/content.py` — one repository per model; dedup lookups by source
  hash, source message id, content hash and media hash.
- `providers/content_base.py` + `providers/content_sources.py` — the
  `ContentSourceProvider` protocol and Telegram / RSS / Atom / manual providers.
  Telegram respects content protection (`noforwards` → keep only the link, D-006).
- `providers/posting_base.py` + `providers/posting.py` — the `PostingProvider`
  protocol (`publish` / `delete` / `send_comment` / capabilities) and the bot /
  user implementations; neither imports aiogram or Telethon directly (D-001).
- `services/content_service.py` — sources CRUD, `grab` (dedup + moderation),
  items, cleaner preview/apply/revert, rights, rewrite (through the existing
  generative LLM backend only — the ruBERT encoder is never used for generation,
  D-068), moderation (blocked keywords + quiet hours), `release_held`,
  `publish_text`, dashboard.
- `services/content_cleaner.py` — the deterministic, explainable, cancellable
  cleaner.
- `services/content_markup.py` — `validate_markup`, `validate_buttons`,
  `render_preview` (a Telegram-like preview; never claims a channel capability it
  cannot verify).
- `services/posting_service.py` — planning (draft → one publication per channel),
  scheduling, calendar, inline buttons, publish (with `uncertain` idempotency on a
  lost connection), retry, auto-delete and first comments; `tick()` runs one
  bounded pass and `due_count()` reports remaining work.
- `scheduler/handlers.py` — the `content.posting` handler runs a bounded pass and
  re-schedules itself every `POSTING_TICK_SECONDS`, so it is a durable periodic
  tick that survives restarts (D-008 style) and fires a later-scheduled post
  without a restart. `main.py` seeds the first tick with `QueueService.ensure_periodic`.
- `api/v1/content.py` + `api/schemas/content.py` — the `/api/v1/content/*` router;
  `api/deps.py::get_posting_service` / `get_content_service`.

Nothing is published without an explicit owner action; unknown rights warn and
add attribution rather than blocking silently; protected content keeps only its
link.

---
