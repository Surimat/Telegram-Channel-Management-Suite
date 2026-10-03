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
