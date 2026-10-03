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
  → else if AI enabled → Tiny GGUF classifier → strict JSON {category, tone, confidence}
  → else → "neutral" fallback
  → Reaction Profile (deterministic weighted emoji choice)
```

Rules are **data, not code**: editable from the Web UI, stored in DB.
Categories (minimum set): `donation, news, funny, sad, angry, cute, support,
announcement, neutral`.

The AI returns **strict structured JSON** and is used **only** to pick a
category/tone/confidence. Emoji selection is **always deterministic weighted
logic**, never the LLM. AI can be disabled entirely (`AI_ENABLED=false`).

Implemented (PHASE 7) in `backend/app/ai/` — free of Telegram/FastAPI imports:

- `types.py` — `Classifier` Protocol and `ClassificationResult`
  (`category`, `tone`, `confidence`, `source`; `source` ∈
  `rules`/`llm`/`manual`/`fallback`/`default`).
- `classifiers.py` — `RulesClassifier` (wraps the Rules Engine),
  `LlmClassifier` (prompt → `run_bounded` → strict parse), `FakeClassifier`.
- `schema.py` — tolerant about framing, strict about values; invalid JSON/unknown
  category/tone/out-of-range confidence ⇒ `InvalidModelOutputError`.
- `router.py` — `RoutingClassifier`: rules fast path (`ai_rules_threshold`),
  then AI only when unsure (`ai_confidence_threshold`), else graceful fallback.
  `RoutingOutcome` records `ai_attempted`/`ai_used`/`fallback_used`.
- `inference.py` — one shared single-worker executor (`run_bounded`); a timeout
  raises `InferenceTimeoutError` and shut down on app exit.
- `backends/` — registry (`build_backend`): `fake` (deterministic, offline/tests)
  and `llama_cpp` (the only `llama_cpp` importer; lazy, lock-serialized, optional).

Configuration is read through `AiService.effective()` so DB settings override env
defaults (D-034). Models are user-provided `.gguf` assets in the gitignored
`/models/` directory — never committed, never auto-downloaded. Modes: `auto`
(default), `rules`, `ai`.

---

## 8. Reaction Manager & scheduler

One bot can place **one** reaction per message. A `reaction_job` row stores:
`post_id, bot_id, reaction, scheduled_at, status, attempts, error, completed_at`.

Planner properties (all configurable): allowed emojis, weights, reaction
probability, min/max delay, delay ranges, randomization, skip probability,
per-bot enable/disable, reaction profiles, preview/simulation.

The scheduler **never fires all reactions at once** — it spreads them using the
configured randomized delays. Jobs are persisted so an app restart can resume
pending work (`pending`/`scheduled` rows are re-hydrated on startup).

---

## 9. Reliability principles

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

## 10. Deployment targets

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

---

## 11. Security model

- Secrets never committed (`.gitignore` + `.env.example`).
- Tokens/sessions never printed to console, UI, logs, exceptions, or API responses.
- Session files: separate directory, gitignored, excluded from Docker images,
  owner-labelled, revocable, health-checkable.
- Windows: OS-protected secret storage where available.
- VPS: environment variables / secret files.
- See `docs/SECURITY.md` for the full policy and review checklist.

---

## 12. Extension points

- New Telegram provider implementations (e.g. a second Bot API library).
- New classification backends behind the same classifier interface.
- New reaction strategies behind the planner interface.
- New deployment targets without changing the backend.
