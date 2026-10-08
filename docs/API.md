# API — Telegram Channel Management Suite

REST API served by FastAPI. The **Web UI and the Telegram Mini App use the same
API**. OpenAPI schema is auto-generated at `/docs` (Swagger) and `/redoc`.

Base path: `/api/v1`
Health endpoints live at the root (`/health`, `/health/deep`) for probes.

> This document lists the contract. Endpoints are implemented across phases;
> see `agent/CURRENT_STATE.md` for what exists now.

---

## Conventions

- JSON request/response bodies.
- Errors use a uniform envelope:

```json
{
  "error": {
    "code": "short_machine_code",
    "message": "Human-friendly message (RU-first).",
    "hint": "What to do next.",
    "details": null
  }
}
```

- Never return secrets, tokens, session content, or stack traces.
- All list endpoints support `?page=&page_size=&q=&sort=` where meaningful and
  return `{ "items": [...], "total": N, "page": P, "page_size": S }`.

---

## Health

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness (fast) |
| GET | `/health/deep` | deep checks (db, scheduler, providers, filesystem) |

---

## Setup / System

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/system/status` | overall system status summary |
| GET | `/api/v1/system/setup` | run Setup Wizard checks |
| GET | `/api/v1/system/info` | version, paths, environment |
| GET | `/api/v1/system/database` | database migration state in plain language |
| POST | `/api/v1/system/database/upgrade` | apply pending migrations (pre-migration backup first) |
| POST | `/api/v1/system/shutdown` | graceful shutdown (portable/stop.bat) |

Backups and configuration export/import live under `/api/v1/backup` — see the
**Backup / Restore** section below.

---

## Help / UI preferences

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/help/topics` | contextual help topics (what / why / default) |
| GET | `/api/v1/help/prefs` | UI preferences (e.g. novice mode) |
| PUT | `/api/v1/help/prefs` | update UI preferences |

---

## Settings

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/settings` | all settings (secrets masked) |
| PATCH | `/api/v1/settings` | update settings |

---

## Bots

Implemented in PHASE 2. A bot token is verified with Telegram (`getMe`) before
being stored, and is persisted **sealed** (encrypted at rest with a key derived
from `APP_SECRET_KEY`). Responses expose `has_token` but never the token itself.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/bots` | list bots (`?kind=&enabled=`) |
| POST | `/api/v1/bots` | add a bot (validate token, seal, store) |
| GET | `/api/v1/bots/summary` | counts + manager-bot state (for Dashboard) |
| GET | `/api/v1/bots/{id}` | bot detail |
| POST | `/api/v1/bots/{id}/health` | run health check (getMe) |
| POST | `/api/v1/bots/{id}/enable` | enable |
| POST | `/api/v1/bots/{id}/disable` | disable |
| DELETE | `/api/v1/bots/{id}` | remove from active config |
| GET | `/api/v1/bots/managed/all` | list managed bots recorded locally |
| GET | `/api/v1/bots/managed/preview` | build the official create link (`?username=&name=`) |
| POST | `/api/v1/bots/managed/register` | record a managed bot (from a `managed_bot` update) |
| POST | `/api/v1/bots/{id}/managed/token` | fetch managed-bot token (`getManagedBotToken`) |
| POST | `/api/v1/bots/{id}/managed/replace-token` | revoke + regenerate (`replaceManagedBotToken`) |

Managed bots use the official Telegram API only. The manager bot must have
"Bot Management Mode" enabled in @BotFather; Telegram creates the child bot
through the link and notifies the manager via a `managed_bot` update.

---

## Sessions (user accounts) — PHASE 4

All Telegram access goes through the `SessionProvider` abstraction. Responses
expose only `phone_masked` (e.g. `+7999***4567`) and `has_session` /
`has_api_hash` / `session_file_exists` booleans — never the api_hash, the full
phone number or the session file contents.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/sessions` | list accounts (`status`, `enabled` filters) |
| GET | `/api/v1/sessions/summary` | counts by status (total/active/online/...) |
| GET | `/api/v1/sessions/{id}` | one account |
| POST | `/api/v1/sessions/auth/start` | start wizard (api_id, api_hash, phone) → code sent |
| POST | `/api/v1/sessions/{id}/code` | submit login code (may advance to 2FA) |
| POST | `/api/v1/sessions/{id}/password` | submit 2FA password |
| POST | `/api/v1/sessions/import` | import an existing `.session` file by path |
| POST | `/api/v1/sessions/import/detect` | detect a local artifact's format + state (`path` or `string_session`) |
| POST | `/api/v1/sessions/import/artifact` | import `.session` / `.session`+JSON / StringSession / TDATA |
| GET | `/api/v1/sessions/{id}/risk` | account restriction-risk band (`level`/`title`/`message`) |
| POST | `/api/v1/sessions/{id}/health` | health check (updates status) |
| POST | `/api/v1/sessions/{id}/enable` | enable the account |
| POST | `/api/v1/sessions/{id}/disable` | disable the account |
| POST | `/api/v1/sessions/{id}/logout` | reset local session → re-authorize |
| DELETE | `/api/v1/sessions/{id}` | delete the account + its session file |

Wizard steps: `idle` → `code` → `password` (optional 2FA) → `done`. An interrupted
flow is reset to `auth_required` on startup (`SessionService.recover()`).

### Account Hub — local session import (v1.1)

The Account Hub accepts the common formats a user already owns, behind one
`SessionImportProvider` protocol (`backend/app/services/session_import.py`). It
only ever reads **local files the user owns**; it never searches for, downloads,
or bulk-registers third-party accounts and never bypasses Telegram verification,
FloodWait, privacy or identity checks (D-006).

| Format | Detection |
|--------|-----------|
| Telethon `.session` | a SQLite file (`SQLite format 3` header) |
| `.session` + companion JSON | `.session` plus `<stem>.json` / `<stem>_meta.json` |
| StringSession | a Telethon `StringSession` string |
| TDATA | a Telegram Desktop `tdata` directory (optional converter) |

`POST /sessions/import/detect` returns `format`, `format_title`, `state`
(`valid`/`damaged`/`unauthorized`/`unknown`), `available`, `message` and
`how_to_fix` before anything is imported. The companion JSON is read with a
whitelist (`api_id`/`app_id`/`api_hash`/`app_hash`/`phone`/`dc_id`); secret keys
(`session_string`, `auth_key`, `password`, …) are never read. A StringSession
string is accepted, written to the protected sessions directory and **never
returned, logged or displayed** again. TDATA conversion is optional: with no
reliable converter installed the importer reports an honest `NOT AVAILABLE`
state instead of pretending (the source `tdata` folder is never modified or
uploaded).

### Account restriction risk (v1.1)

`GET /sessions/{id}/risk` returns `level` (`healthy`/`warning`/`flood_wait`/
`restricted`/`auth_required`/`disabled`), a human `title` and an explanatory
`message`. Repeated limits raise the band. The UI shows this in the account card
and **never promises a safe invite count** — Telegram provides no universal safe
limit.

---

## Audience & Sources — PHASE 5 (implemented)

All paths are under `/api/v1/audience`. Sources:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/dashboard` | aggregate audience statistics |
| GET | `/filters/presets` | ready-made filter presets |
| GET | `/sources` | list sources (`enabled`,`status`,`search`,`limit`,`offset`) |
| POST | `/sources` | add source (`reference`: @user, t.me link or id) |
| GET | `/sources/{id}` | source detail |
| PATCH | `/sources/{id}` | edit title/enabled/account/type |
| DELETE | `/sources/{id}` | delete source (+ its links) |
| POST | `/sources/{id}/check` | resolve source, report reachability |
| POST | `/sources/{id}/scan/preview` | dry-run summary before scanning |
| POST | `/sources/{id}/scan` | start a durable scan job |
| GET | `/sources/{id}/scan/progress` | live scan progress + completeness |
| POST | `/sources/{id}/scan/pause` | pause |
| POST | `/sources/{id}/scan/resume` | resume from stored offset |
| POST | `/sources/{id}/scan/cancel` | cancel |

Audience users:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/users` | list users (`search`, `source_id`, `tag`, `status`, `is_bot`, `is_deleted`, `has_username`, `is_premium`, `telegram_user_id`, `sort`, `order`, `limit`, `offset`) |
| GET | `/users/{id}` | user detail (+ sources, score components) |
| POST | `/users/bulk-status` | bulk status update |
| GET | `/tags` | list tags with counts |
| POST | `/tags/assign` \| `/tags/remove` | bulk tag edit |
| POST | `/tags/rename` | rename a tag |
| DELETE | `/tags/{tag}` | delete a tag |

Export / import:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/export/preview` | preview row count + fields (+ PII flag) |
| POST | `/export` | write CSV/JSON to the local `exports/` dir |
| POST | `/import` | import CSV/JSON text with dedup |

Notes: responses never contain raw phone numbers or secrets; PII export is off by
default and gated by the `AUDIENCE_STORE_PII` setting. Scan completeness values:
`complete`, `partial`, `no_access`, `failed`, `unknown`.

---

## Reactions & Rules

Implemented in PHASE 3. Reaction execution goes through `TelegramBotProvider`
(D-001) and the durable queue (D-008); emoji choice is deterministic weighted
logic, never an LLM (D-005). Preview/simulation never contacts Telegram.

### Reaction profiles

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/reactions/categories` | list classification categories (key + RU title) |
| GET | `/api/v1/reactions/profiles` | list profiles |
| POST | `/api/v1/reactions/profiles` | create a profile |
| PATCH | `/api/v1/reactions/profiles/{id}` | update a profile |
| DELETE | `/api/v1/reactions/profiles/{id}` | delete a profile |
| POST | `/api/v1/reactions/simulate` | preview a plan for a text (no Telegram call) |
| GET | `/api/v1/reactions/status` | status + counters (for Dashboard) |
| POST | `/api/v1/reactions/enable` | enable the Reaction Manager (global switch) |
| POST | `/api/v1/reactions/disable` | disable the Reaction Manager |

A profile carries: `allowed_emoji`, `emoji_weights`, `participation_probability`,
`skip_probability`, `delay_min`/`delay_max`, `delay_preset`
(`early`/`normal`/`spread`), `max_bots_per_post`, `enabled`, `is_default`.
Exactly one profile can be the default.

### Rules

Editable classification rules (seeded once, then fully user-editable):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/reactions/rules` | list rules |
| POST | `/api/v1/reactions/rules` | create a rule |
| PATCH | `/api/v1/reactions/rules/{id}` | update a rule |
| DELETE | `/api/v1/reactions/rules/{id}` | delete a rule |

A rule carries: `category`, `keywords`, `phrases`, `regexes`, `exclusions`,
`allowed_reactions`, `preferred_reactions`, `forbidden_reactions`,
`min_confidence`, `priority`, `language`, `manual_override`, `enabled`.

### Posts & reaction jobs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/reactions/posts` | list ingested posts |
| POST | `/api/v1/reactions/posts` | ingest a post: classify + (optionally) plan |
| POST | `/api/v1/reactions/posts/{id}/plan` | (re)plan reactions for a post |
| GET | `/api/v1/reactions/jobs` | list reaction jobs (`?status=`) |

Each reaction job stores `post_id`, `bot_id`, `reaction`, `scheduled_at`,
`status`, `attempts`, `error`, `completed_at` — and a matching durable queue row.

---

## AI classifier (optional) — PHASE 7 (implemented)

The Rules Engine is always the deterministic default. The tiny AI is consulted
only when rules are unsure, and every AI failure degrades to the rules result.
The LLM never picks emoji; emoji selection stays deterministic (D-021/D-033).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/ai/status` | status: enabled, backend, model present/loaded, effective + plain-language reason/fix |
| GET | `/api/v1/ai/overview` | status + lifetime metrics + today's metrics |
| GET | `/api/v1/ai/settings` | all AI settings with plain-language help (what/why/large/safe) |
| PUT | `/api/v1/ai/settings` | update AI settings (validated; DB override) |
| POST | `/api/v1/ai/classify` | classify a text: `{text, mode}` → category/tone/confidence/source + routing flags |
| POST | `/api/v1/ai/test` | alias of `/classify` for the UI's testing panel |
| GET | `/api/v1/ai/models` | list `.gguf` files found in the models directory |
| POST | `/api/v1/ai/model/check` | verify runtime + model file (load test, load time) |
| POST | `/api/v1/ai/model/load` | load the model into memory |
| POST | `/api/v1/ai/model/unload` | unload the model from memory |
| GET | `/api/v1/ai/metrics` | aggregate classification counters/latency |
| GET | `/api/v1/ai/history` | recent AI diagnostics records (`?limit=&offset=`) |

`mode` is `auto` (rules-first, default), `rules` (rules only), `encoder` (the
lightweight local encoder only — no model download, weak-PC friendly) or `ai`
(AI only, falls back to rules). `source` is `rules` / `llm` / `encoder` /
`manual` / `fallback`.
Model files are user-provided runtime assets: never committed, never downloaded
automatically. The lightweight encoder needs no model file at all.

#### Optional lightweight encoder model (v1.1)

The built-in encoder needs no download. The optional **ruBERT-tiny2** encoder
backend (embeddings only, never a generative JSON model — D-068) is installed
from the UI or API; only official files are fetched and each is verified by
SHA-256 before it is kept in the gitignored `models/` directory.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/ai/encoder/status` | `runtime_available`, `installed`, `ready`, `model_dir`, `size_bytes`/`size_human` |
| POST | `/api/v1/ai/encoder/install` | download + verify the official model files |
| POST | `/api/v1/ai/encoder/check` | run a real load test (honest pass/fail) |
| POST | `/api/v1/ai/encoder/remove` | delete the downloaded model (built-in encoder still works) |

The status is honest: a missing runtime (`torch`/`transformers`) is reported as
such, and a failed checksum is rejected without keeping the file.

---

## Analytics — PHASE 8 (implemented)

Read-only aggregates over data the suite already stores (posts, reaction jobs,
audience sources/users/links, invite tasks). Every response carries a
plain-language RU `summary`; the backend owns the copy so the Web UI and the Mini
App share it (D-036). Responses contain only aggregate counts — no secrets or
per-person PII (D-010/D-029). `days` is clamped to `1..365` (default `30`).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/analytics/overview?days=&channel_id=` | headline + content + reactions + audience + a list of takeaways |
| GET | `/api/v1/analytics/content?days=&channel_id=` | posts total/window, per-day series, category/source/status mix, summary |
| GET | `/api/v1/analytics/reactions?days=&channel_id=` | status mix, success rate, planned/completed per day, emoji/bot/category mix |
| GET | `/api/v1/analytics/audience?days=&channel_id=` | audience total, new 7d, per-day growth, status mix, top sources, source effectiveness, invite outcomes |

`channel_id` optionally scopes every analytics view to one registry channel
(`/api/v1/channels`). Omit it for global aggregates; the Analytics page defaults
to the channel marked as default in the registry.

`by_category`/`by_source`/`by_status` entries are titled for the UI. Charts in the
frontend are dependency-free inline SVG (`Sparkline.vue`, `BarList.vue`, D-037).

---

## Logs / Error Center

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/events` | list events (level, module, filter) |
| GET | `/api/v1/events/{id}` | event detail + "what happened / how to fix" |
| POST | `/api/v1/events/{id}/resolve` | mark resolved |

---

## Queue / Scheduler

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/queue` | queue jobs (status filter) |
| POST | `/api/v1/queue/{id}/retry` | retry a job where appropriate |
| POST | `/api/v1/queue/{id}/cancel` | cancel |

---

## Invites (PHASE 6)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/invites/preview` | dry-run summary (counts, accounts, sources, filters) |
| GET | `/api/v1/invites/summary` | job counts by status |
| GET | `/api/v1/invites` | list invite jobs (status/search, pagination) |
| POST | `/api/v1/invites` | create a draft job (plans tasks; runs nothing) |
| GET | `/api/v1/invites/{id}` | job detail + plain-language explanation |
| POST | `/api/v1/invites/{id}/confirm` | confirm the summary **and** start the run |
| POST | `/api/v1/invites/{id}/pause` | pause the run |
| POST | `/api/v1/invites/{id}/resume` | resume a paused run |
| POST | `/api/v1/invites/{id}/stop` | stop the run |
| POST | `/api/v1/invites/{id}/retry` | re-queue technically retryable tasks |
| GET | `/api/v1/invites/{id}/tasks` | per-user tasks (status filter, counts) |

A run never starts without confirmation (`confirm` records `confirmed_at`). On
restart, running jobs are paused rather than silently resumed. Responses never
contain tokens, session contents, `api_hash` or raw phone numbers.

---

## Mini App authentication (PHASE 9 — implemented)

The Mini App reuses the same SPA and the same API (D-003). These endpoints only
establish *who* the Telegram caller is; all business endpoints are shared with the
local Web UI.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/miniapp/config` | feature flag, manager bot username, plain-language availability + how-to-fix |
| POST | `/api/v1/miniapp/setup` | register a public HTTPS URL as the manager bot's Web App menu button (owner action; persists `miniapp_public_url` + `miniapp_enabled`) |
| POST | `/api/v1/miniapp/auth` | verify Telegram WebApp `initData` (HMAC-SHA256), set a signed session cookie |
| GET | `/api/v1/miniapp/me` | report whether the current session cookie is valid |
| POST | `/api/v1/miniapp/logout` | clear the session cookie |

Auth details:

- `initData` is verified with `HMAC_SHA256(bot_token, "WebAppData")` over the
  sorted `key=value` pairs, per Telegram's Mini App spec.
- Stale payloads (older than `MINIAPP_INITDATA_MAX_AGE`) are rejected.
- The manager bot token is used only as the HMAC key; it is never logged or
  returned. The raw `initData` is never logged or returned.
- When `MANAGER_BOT_ADMIN_IDS` is set, only those Telegram ids may sign in.
- The session cookie (`tcms_miniapp`) is `HttpOnly`, `SameSite=Lax`, and
  `Secure` in production; its token is HMAC-signed with a key derived from
  `APP_SECRET_KEY`.
- The Mini App is off by default (`MINIAPP_ENABLED=false`); the local Web UI is
  unaffected and still needs no public server.

---

## Backup / restore (PHASE 10 — implemented)

Backups are single `.tcmsbak` zip files (SQLite database + `manifest.json`).
Restoring always writes a safety backup of the current state first. Configuration
export/import moves only user-owned rows and never includes secrets.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/backup/info` | plain-language explanation + excluded tables |
| GET | `/api/v1/backup` | list backups (filename, date, size, sessions flag, retention) |
| POST | `/api/v1/backup` | create a backup (`include_sessions` optional, off by default) |
| GET | `/api/v1/backup/download?filename=` | download a backup file |
| POST | `/api/v1/backup/restore?filename=` | restore a backup (creates a safety backup) |
| DELETE | `/api/v1/backup/{filename}` | delete a backup |
| GET | `/api/v1/backup/config/export` | export configuration as JSON |
| POST | `/api/v1/backup/config/import?replace=` | import configuration (multipart `file`) |

Safety notes:

- Session files are **never** included unless `include_sessions=true`; even then
  the manifest is marked so the owner can see it.
- `export_config` / `import_config` only touch `settings`, `reaction_profiles`
  and `reaction_rules`. The `bots` and `user_sessions` tables (sealed tokens and
  session references) are **excluded** and reported as such in `/backup/info`.
- Filenames are validated against path traversal; responses never contain
  tokens, hashes, phone numbers or session contents.

---

## Permission probe (post-1.0 hardening)

Checks whether a user account really has access to a target channel before an
invite run: is the channel resolvable, are members readable, can we invite?
The result is stored and shown in plain language; the status is one of
`ok | partial | no_access | auth_required | admin_required | privacy_restricted |
flood_wait | error`. Responses never expose an api_hash, phone or session content.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/permissions/check` | probe one account against a channel (`account_id`, `target` or `channel_id`) |
| GET | `/api/v1/permissions/latest` | most recent check (or `null`) |
| GET | `/api/v1/permissions/history?limit=` | recent checks, newest first |

---

## Manager bot runtime (post-1.0 hardening)

The manager bot can be driven from Telegram (an admin whitelist) and can forward
significant events to the owner. Only the username and health are exposed; tokens
are never returned.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/manager/status` | connected/runtime state, admin count, pending notifications |
| GET | `/api/v1/manager/notifications` | master switch + per-category toggles |
| PUT | `/api/v1/manager/notifications` | update toggles (`enabled`, `categories`) |

Admin IDs come from `MANAGER_BOT_ADMIN_IDS` (comma-separated). The runtime polls
the manager bot only while the app runs and never blocks the durable scheduler.

---

## Channel Registry (hardening)

One shared channel identity for every module. A channel stores its reference
(normalized `@username` / numeric ID), resolved title/kind, verification state and
per-module toggles. `reference` accepts `@name`, `name`, `t.me/name` or a numeric
ID and is normalized on input. Verification reuses the permission probe and never
bypasses Telegram limits.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/channels?search=&status=&limit=&offset=` | list channels |
| GET | `/api/v1/channels/summary` | counts + default channel |
| GET | `/api/v1/channels/{id}` | one channel |
| POST | `/api/v1/channels` | add (`reference`, optional `title`/`kind`/`make_default`/`note`) |
| PATCH | `/api/v1/channels/{id}` | update editable fields |
| POST | `/api/v1/channels/{id}/verify` | verify with an account (`account_id`) |
| POST | `/api/v1/channels/{id}/modules` | set module toggles (`modules`) |
| POST | `/api/v1/channels/{id}/default` | make this the default channel |
| DELETE | `/api/v1/channels/{id}` | remove (a default is promoted if needed) |

The first channel added becomes the default. Invite create/preview accept an
optional `channel_id`; when set, the target and title come from the registry.

Registry links are used by other modules too:

- `POST /api/v1/reactions/posts` accepts an optional `registry_channel_id`; when
  set, the post's `channel_username` (and numeric `channel_id` when the registry
  channel has a known Telegram id) are filled from the registry. `PostOut` echoes
  `registry_channel_id`.
- `POST /api/v1/audience/sources` accepts an optional `channel_id`; when set, the
  source `reference`/`username`/`telegram_id` come from the registry (or the
  source is created with the registry reference). `SourceOut` echoes `channel_id`.
- `POST /api/v1/permissions/check` accepts an optional `channel_id` in place of
  `target`; the probe resolves the reference from the registry and stores the link
  (`registry_channel_id`) with the result.

An unknown registry id returns a friendly `404`.

---

## Diagnostics (product polish)

Owner-facing system state in plain language plus a **redacted** support report.
The report never contains bot tokens, api_hash/api_id, session data, phone
numbers, passwords, database contents or audience records; every payload is
redacted and re-scanned server-side before it is returned. If the safety scan is
unsure, no file is produced (HTTP 500 with a friendly message).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/diagnostics` | one status row per subsystem (`ok \| warning \| error \| not_configured`), each with "what it means" and "what to do" |
| GET | `/api/v1/diagnostics/actions` | safe maintenance actions and their state |
| POST | `/api/v1/diagnostics/actions/{key}` | run a safe action (`restart_scheduler`, `recheck_telegram`, `recheck_channels`, `cleanup_jobs`) |
| GET | `/api/v1/diagnostics/report?format=json\|txt\|zip` | download the redacted report (`X-Diagnostics-Redacted: true`) |
| GET | `/api/v1/diagnostics/report/formats` | available export formats |

Subsystems covered: application, database (migration status + revision), Telegram
Bot API, manager bot, managed bots, user sessions (status only, no contents),
channels, audience, reactions, invites, AI, scheduler/queue, storage and the
portable runtime.

Maintenance actions are non-destructive: they never delete user data. Only
`cleanup_jobs` requires confirmation (it resets jobs stuck in "running" and
cancels long-overdue pending jobs); it is hidden while the scheduler is running.

---

## Bot ↔ channel bindings & reaction capabilities

A binding connects a bot to a registry channel for a function (`reactions`,
`posting`, `editing`) and records the **verified** admin rights. Capabilities
record which reactions Telegram reports as available for a channel. Everything is
**bot-only** — no user session is required — and tokens are never returned.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/bindings?channel_id=&bot_id=` | list bindings |
| POST | `/api/v1/bindings` | connect a bot to a channel (`bot_id`, `channel_id`, `function`) |
| POST | `/api/v1/bindings/{id}/check` | verify the binding against Telegram (rights, presence) |
| POST | `/api/v1/bindings/channel/{channel_id}/check` | verify every binding of one channel |
| DELETE | `/api/v1/bindings/{id}` | remove a binding |
| GET | `/api/v1/capabilities/{channel_id}` | last known reaction capabilities |
| POST | `/api/v1/capabilities/{channel_id}/probe` | probe Telegram for the channel's reactions |

The binding response includes a `status` (`not_connected`, `connected`,
`needs_permission`, `ready`, `error`), a plain-language `status_label`, the
verified `can_*` rights and the official `invite_link` to add the bot.

---

## Invite campaigns (no session required)

Campaigns promote a channel through invite links. They work with the manager bot
only (no MTProto account) and never bypass Telegram limits: the chosen
`risk_mode` sets conservative spacing, and every link action is a normal Bot API
call.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/campaigns` | list campaigns + available risk modes |
| POST | `/api/v1/campaigns` | create a campaign (`name`, optional `channel_id`, `risk_mode`) |
| GET | `/api/v1/campaigns/{id}` | campaign detail (links, pending/approved requests) |
| POST | `/api/v1/campaigns/{id}/status` | change state (`draft`/`active`/`paused`/`completed`/`disabled`) |
| DELETE | `/api/v1/campaigns/{id}` | delete a campaign |
| POST | `/api/v1/campaigns/{id}/links` | create an invite link (`label`, `join_request`, `member_limit`) |
| POST | `/api/v1/campaigns/{id}/links/{link_id}/revoke` | revoke an invite link |

---

## Donor quality indicators

Explainable source-quality indicators for scanned audience sources. The service
reports a probability **band** and a confidence level; when an account is not
connected and member data is unavailable, no bot share is invented — the estimate
stays `null` and only confidence is shown.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/donors` | list donor metrics + an honesty note |
| POST | `/api/v1/donors/analyze/{source_id}` | (re)analyze one source |
| POST | `/api/v1/donors/analyze` | analyze all sources |

---

## Backup destinations

Each new backup is delivered to every **enabled** destination. A local
destination is created automatically and cannot be deleted; remote destinations
(Telegram, Google Drive, Яндекс.Диск) are optional and only contacted when the
owner enables them. Credentials are sealed at rest and never returned.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/backup/destinations` | list destinations + available kinds |
| POST | `/api/v1/backup/destinations` | add a destination (`kind`, optional `config`, `token`) |
| PATCH | `/api/v1/backup/destinations/{id}` | update (`enabled`, `label`, `config`, `token`) |
| POST | `/api/v1/backup/destinations/{id}/check` | verify reachability |
| DELETE | `/api/v1/backup/destinations/{id}` | remove a remote destination |
| POST | `/api/v1/backup/destinations/deliver` | re-send the newest backup to every enabled destination |

---

## First-run promotion wizard

A guided, resumable onboarding flow. It reflects **real** system state (channel,
manager bot, session, AI, backup, update) and never claims a step is done unless
it is. Without a user session, session-gated steps are `optional`, not required.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/promotion/presets` | available presets (minimal → professional) |
| GET | `/api/v1/promotion` | current wizard state + per-step status |
| POST | `/api/v1/promotion/preset` | switch preset (`preset`) |
| POST | `/api/v1/promotion/step` | mark a step (`step`) |
| POST | `/api/v1/promotion/finish` | mark the setup complete |
| POST | `/api/v1/promotion/dismiss` | hide the wizard |

---

## Auto-update (conservative)

Checks GitHub Releases for a newer version and can stage a **verified** file
(SHA-256 checked). It never installs anything by itself and is disabled by
default; when enabled it only checks and downloads. `state` is one of `idle`,
`checking`, `up_to_date`, `available`, `downloaded`, `error`, `failed`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/update` | current update state |
| POST | `/api/v1/update/enabled` | enable/disable checking (`enabled`) |
| POST | `/api/v1/update/check` | check for a newer release |
| POST | `/api/v1/update/download` | download + verify the release archive |

---

## Proxy profiles / network routes (v1.1)

Owner-facing CRUD for connection routes. A proxy is a normal connection route
for a user account — it **never** lifts Telegram limits (FloodWait, privacy,
admin rights) and must not be used to bypass them. The password is accepted on
input, sealed at rest and never returned (`has_password` only). The list response
always carries the explicit non-bypass notice.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/proxies` | list profiles + non-bypass notice |
| POST | `/api/v1/proxies` | add a profile (`name`, `kind`, `host`, `port`, optional `username`/`password`) |
| PUT | `/api/v1/proxies/{id}` | update a profile (empty `password` clears it) |
| DELETE | `/api/v1/proxies/{id}` | delete a profile; bound accounts return to a direct connection |
| POST | `/api/v1/proxies/{id}/check` | honest reachability check (`ok`/`error`/`timeout` + how-to-fix) |
| POST | `/api/v1/proxies/bind` | bind an account (`account_id`, `profile_id`; empty = direct) |

---

## Donor discovery (v1.1)

Search for donor channels by topic. Results are **candidates** — proposals only.
A candidate becomes an audience source solely through an explicit
`POST /candidates/{id}/add`. Metrics that Telegram hid stay at zero and the
`partial`/`confidence` fields say so; nothing bypasses Telegram limits.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/discovery/providers` | provider availability (telegram / web / manual) |
| POST | `/api/v1/discovery/search` | run a search (`topic`, optional filters) |
| GET | `/api/v1/discovery/candidates` | stored candidates + provider status |
| POST | `/api/v1/discovery/compare` | compare 2–10 candidates, name the best |
| POST | `/api/v1/discovery/candidates/{id}/add` | explicitly add a candidate to sources |
| POST | `/api/v1/discovery/candidates/clear` | clear stored candidates (sources are kept) |

---

## Content Studio (v1.2)

Collect material from sources, prepare it, and publish it to the owner's own
channels. Nothing is published without an explicit action; unknown rights warn
and add attribution; protected content keeps only its link.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/content/providers` | provider availability (telegram / rss / atom / manual) |
| GET | `/api/v1/content/sources` | sources + provider status |
| POST | `/api/v1/content/sources` | add a source (`kind`, `reference`, optional `title`/`channel_id`/`account_id`) |
| DELETE | `/api/v1/content/sources/{id}` | remove a source |
| POST | `/api/v1/content/sources/{id}/grab` | fetch new material (`limit`); returns new/duplicate/blocked/held counts |
| GET | `/api/v1/content/sources/{id}/moderation` | blocked keywords + quiet hours |
| PUT | `/api/v1/content/sources/{id}/moderation` | update moderation |
| GET | `/api/v1/content/items` | list items (`status`, `source_id`, `limit`, `offset`) |
| GET | `/api/v1/content/items/{id}` | one item |
| PATCH | `/api/v1/content/items/{id}` | edit item (title/text/note/status/rights/mode/scheduled_at) |
| DELETE | `/api/v1/content/items/{id}` | delete an item |
| GET | `/api/v1/content/items/{id}/clean` | cleaner preview (explainable, cancellable) |
| POST | `/api/v1/content/items/{id}/clean` | apply cleaning (optional `cleaned` override) |
| POST | `/api/v1/content/items/{id}/clean/revert` | revert cleaning |
| POST | `/api/v1/content/items/{id}/rewrite` | rewrite preview (generative LLM backend only) |
| POST | `/api/v1/content/items/{id}/rewrite/apply` | apply a rewrite |
| GET | `/api/v1/content/items/{id}/rights` | rights status + attribution block + warning |
| POST | `/api/v1/content/items/{id}/release` | release a moderation-held item |
| GET | `/api/v1/content/items/{id}/validate` | Telegram markup + button validation |
| GET | `/api/v1/content/items/{id}/preview` | Telegram-like preview |
| GET/PUT | `/api/v1/content/items/{id}/buttons` | inline button set |
| POST | `/api/v1/content/items/{id}/plan` | plan one publication per target channel |
| GET | `/api/v1/content/items/{id}/publications` | publications for an item |
| POST | `/api/v1/content/publications/{id}/schedule` | set/clear the scheduled time |
| POST | `/api/v1/content/publications/{id}/cancel` | cancel a publication |
| POST | `/api/v1/content/publications/{id}/publish` | publish now (idempotent; `uncertain` on a lost connection) |
| POST | `/api/v1/content/publications/{id}/retry` | retry a failed publication |
| GET | `/api/v1/content/calendar` | multi-channel calendar (`start`, `end`) |
| GET | `/api/v1/content/dashboard` | status counts |
| POST | `/api/v1/content/tick` | run one bounded posting pass (manual/diagnostic) |

---

## Content Operations 2.0 (v1.9)

Extends Content Studio into a **single pipeline** —
`source → gather → clean → mini-AI → moderation → publish → comment/delete` —
without a second studio and without breaking the v1.2 routes. Everything is
additive; every new column has a server default.

**AI profiles** hold the prompt as *data* (instructions, language, tone, max
length, provider policy, actions) so a prompt is never hardcoded. **Automation
rules** are declarative `SOURCE + CONDITION → ACTION` — deliberately not a
script engine: the condition vocabulary is a fixed field allow-list and actions
are a fixed allow-list of pipeline steps. **Pipeline records** are append-only
metadata (no text, no keys).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/content/ai-profiles` | list profiles (built-ins first) |
| POST | `/api/v1/content/ai-profiles` | create a profile (unknown actions dropped) |
| PATCH | `/api/v1/content/ai-profiles/{id}` | update a profile |
| DELETE | `/api/v1/content/ai-profiles/{id}` | delete a profile (built-ins are protected → 400) |
| POST | `/api/v1/content/items/{id}/ai/classify` | local encoder classification (advisory category + intent) |
| POST | `/api/v1/content/items/{id}/ai/process` | apply a profile through the AI Gateway (failover; never loses the item) |
| POST | `/api/v1/content/items/{id}/moderate` | human decision `approve`/`reject`/`review` |
| GET | `/api/v1/content/automation-rules` | list rules |
| POST | `/api/v1/content/automation-rules` | create a rule (non-empty actions required) |
| PATCH | `/api/v1/content/automation-rules/{id}` | update a rule |
| DELETE | `/api/v1/content/automation-rules/{id}` | delete a rule |
| POST | `/api/v1/content/items/{id}/apply-rules` | apply the first matching rule to an item |
| GET | `/api/v1/content/pipeline/analytics` | per-stage counts + recent metadata records |

**Item AI fields:** `original_text`, `ai_status` (`none`/`ok`/`ai_unavailable`/
`error`), `ai_category`, `ai_intent`, `ai_profile`, `ai_note`. `plan` accepts a
per-target `profile_key`. **Publication** now carries `profile_key`,
`comment_status` and `delete_status` independently, so a lost comment or delete
never marks the post `failed`.

**Honesty:** processing without a provider moves the item to `needs_review` with
`ai_status = ai_unavailable` and a clear note — the material is never destroyed.
The mini-AI never selects an emoji; it only returns a category/intent that the
reaction engine then intersects with the channel's available reactions (D-033 /
D-116).

---

## Bot Factory (v1.3)

Create a set of worker bots for the owner and bind them to the owner's own
channels. The factory never registers Telegram accounts and never bypasses
Telegram limits; a username is reported free only after a real Telegram check.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/bot-factory/templates` | name/username templates |
| GET | `/api/v1/bot-factory/dashboard` | batch + candidate counts |
| GET | `/api/v1/bot-factory/batches` | list batches |
| POST | `/api/v1/bot-factory/batches` | create a batch (`prefix`, `count`, optional `topic`/`style`/`channel_id`/`manager_bot_id`) |
| GET | `/api/v1/bot-factory/batches/{id}` | one batch with candidates |
| DELETE | `/api/v1/bot-factory/batches/{id}` | delete a batch |
| GET | `/api/v1/bot-factory/batches/{id}/dashboard` | per-batch dashboard |
| POST | `/api/v1/bot-factory/batches/{id}/check` | check candidate username availability (`account_id`) |
| POST | `/api/v1/bot-factory/batches/{id}/create` | create the batch's bots |
| POST | `/api/v1/bot-factory/batches/{id}/candidates/{cid}/regenerate` | regenerate one candidate's name/username |
| POST | `/api/v1/bot-factory/batches/{id}/candidates/{cid}/adopt` | adopt a bot the owner created in @BotFather |
| POST | `/api/v1/bot-factory/batches/{id}/candidates/{cid}/bind` | bind a candidate's bot to a channel |
| POST | `/api/v1/bot-factory/candidates/{cid}/tokens` | set the managed bot token (write-only; never returned) |
| POST | `/api/v1/bot-factory/batches/{id}/enqueue` | queue free candidate(s) for one-at-a-time creation (durable, restart-resumable) |
| POST | `/api/v1/bot-factory/candidates/{cid}/retry` | re-queue a failed/cancelled candidate operation |
| POST | `/api/v1/bot-factory/candidates/{cid}/skip` | skip a queued candidate operation without touching the rest |
| POST | `/api/v1/bot-factory/batches/{id}/cancel` | stop the batch's queue (already-created bots are kept) |
| POST | `/api/v1/bot-factory/batches/{id}/resume` | restart a stopped batch queue |

The **creation queue** (v1.7) runs through the durable scheduler job
`bot_factory.create`: one creation operation per tick, so a batch survives a
restart. Deep-link batches are not queued for background ticking — the owner
finishes them by hand in Telegram. `token_mask` on a candidate is a
non-reversible head/tail shape (`1234…xyz`) shown in the UI; the raw token is
never returned by the API, never logged and never exported.

---

## LAN Mesh / offline control plane (v1.3)

Optional: several of the owner's computers on one local network cooperate with no
cloud control plane. Standalone (one computer) is the default. Pairing codes and
shared secrets are write-only and never returned; a peer is never trusted
automatically.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/mesh/status` | this computer's identity, mode, role, capabilities |
| GET | `/api/v1/mesh/peers` | peers (`trusted` filter) |
| POST | `/api/v1/mesh/discover` | look for peers on the LAN (broadcast + static) |
| POST | `/api/v1/mesh/peers/manual` | add a peer by address |
| POST | `/api/v1/mesh/pairing-code` | issue a short one-time pairing code |
| POST | `/api/v1/mesh/pair` | trust a peer after verifying the code |
| DELETE | `/api/v1/mesh/peers/{id}` | unpair |
| POST | `/api/v1/mesh/peers/{id}/probe` | check a peer's liveness |
| POST | `/api/v1/mesh/elect` | recompute the coordinator |
| GET | `/api/v1/mesh/leases` | job leases |
| POST | `/api/v1/mesh/leases/acquire` | lease a job to this node (capability-gated) |
| POST | `/api/v1/mesh/leases/complete` | commit a result (stale fencing token rejected) |
| POST | `/api/v1/mesh/leases/reclaim` | reclaim expired leases |

---

## Notification Center (v1.4)

A durable, queryable history of important events with per-category routing,
quiet hours and anti-spam aggregation. Secrets are never stored or returned.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/notifications/settings` | categories, routing, quiet hours |
| PUT | `/api/v1/notifications/settings` | update toggles / routing / quiet hours |
| GET | `/api/v1/notifications` | history (`category`, `priority`, `status`, `page`, `page_size`) |
| GET | `/api/v1/notifications/dashboard` | enabled/pending/failed + counts + in-quiet-hours |
| POST | `/api/v1/notifications/test` | send a test notification (`category`, `priority`) |
| POST | `/api/v1/notifications/{id}/read` | mark a notification read |

---

## Editorial Workspace (v1.4)

A linked Telegram forum supergroup where the owner, editors and moderators work
the same publication queue the Web UI shows. The suite owns the queue order; the
bot's rights are verified, never assumed.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/editorial/rooms` | list rooms |
| POST | `/api/v1/editorial/rooms` | create/link a room (`channel_id`, `group_chat_id`, optional `bot_id`) |
| DELETE | `/api/v1/editorial/rooms/{id}` | delete a room |
| POST | `/api/v1/editorial/rooms/{id}/check` | verify bot rights and create topics (`create_topics`) |
| GET | `/api/v1/editorial/rooms/{id}/members` | list members |
| PUT | `/api/v1/editorial/rooms/{id}/members` | set a member role (by numeric Telegram id) |
| DELETE | `/api/v1/editorial/rooms/{id}/members/{telegram_user_id}` | remove a member |
| GET | `/api/v1/editorial/rooms/{id}/board` | the queue board (columns + counts) |
| POST | `/api/v1/editorial/rooms/{id}/items` | enqueue a content item |
| POST | `/api/v1/editorial/rooms/{id}/items/{item_id}/move` | move an item (`status`, optional `expected_version`) |
| POST | `/api/v1/editorial/rooms/{id}/reorder` | reorder one status column |
| GET | `/api/v1/editorial/rooms/{id}/audit` | the audit trail (`item_id` optional) |

---

## Tray Agent (v1.4)

The tray agent is a separate process; it is not an HTTP surface. It writes a
secret-free snapshot to `data/tray.json` that Diagnostics reads. Start it with
`python -m backend.app.tray.agent --tray --no-browser` (the portable `run.bat`
does this automatically).

---

## Capability graph + Consistency (v1.5)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/capability-graph` | evaluated capability graph (`?language=ru|en`) — what is available now, what is `partial`, what `needs_setup` and how to fix it. Without an explicit `language` it uses the saved preference from `/api/v1/help/prefs` |
| GET | `/api/v1/consistency` | consistency report (overall, counts, areas, findings). Never contains secrets, sessions, phones or database rows |

A capability whose feature does not exist yet is reported as **`not_implemented`**
(never `available`), and each item carries an `implemented` boolean. As of v1.5.1
`config_sync` and `media_conversion` are `not_implemented`.

The Promotion Wizard (`GET /api/v1/promotion`) embeds the same evaluated graph in
`capabilities`, so the wizard, the Dashboard and the Diagnostics panel always
agree.

UI preferences (`/api/v1/help/prefs`) now also carry `language` (default `ru`)
and `available_languages`. The language is selectable in Settings and is used by
the capability graph; the beginner help catalog stays RU-first.

---

## Owner Auth + Config Sync (v1.6)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/owner/status` | owner profile state (exists/enabled/locked, method, last login) — no secret |
| POST | `/api/v1/owner/setup` | create the owner profile (password/PIN); returns a signed token + status |
| POST | `/api/v1/owner/login` | log in; returns a signed token + status |
| POST | `/api/v1/owner/logout` | log out |
| POST | `/api/v1/owner/lock` / `/unlock` | lock / unlock the app |
| POST | `/api/v1/owner/protection` | turn app protection on/off |
| POST | `/api/v1/owner/password` | change the owner password |
| DELETE | `/api/v1/owner/profile` | delete the owner profile (204) |
| GET | `/api/v1/owner/sync/status` | config-sync state (provider, revisions, conflict) — no token |
| POST | `/api/v1/owner/sync/configure` | choose the sync provider (`local` / `google_drive`) |
| POST | `/api/v1/owner/sync/upload` | encrypt the local config into a bundle and hand it to the provider |
| POST | `/api/v1/owner/sync/download/preview` | decrypt a cloud bundle and show what differs (preview-first) |
| POST | `/api/v1/owner/sync/download/apply` | apply a cloud bundle |
| GET | `/api/v1/owner/sync/conflict` | local-vs-cloud revision conflict |
| POST | `/api/v1/owner/sync/disconnect` | disconnect the provider |
| GET | `/api/v1/owner/sync/google/auth` | Google consent URL for the installed-app loopback flow |
| POST | `/api/v1/owner/sync/google/connect` | hand the OAuth tokens to the app (stored sealed) |

While no owner profile exists — or protection is off — every endpoint stays open
exactly as before (local-first). Once protection is on, all `/api/` calls outside a
small allowlist (health, docs, owner status/setup/login, system status) require the
signed `X-Owner-Token` header. No endpoint ever returns a password, verifier, token
value or bundle plaintext.

The config bundle is **canonical JSON → AES-256-GCM**, with the schema version
authenticated as associated data. It carries settings, UI preferences and
provider/scheduler/backup/notification configuration; a denylist plus
`scan_for_secrets` excludes anything that looks secret. Telegram sessions, TDATA
and the SQLite database are **never** synced.

As of v1.6 the `config_sync` capability is **implemented** (requires owner auth +
Google Drive; minimal: owner auth).

---

## AI Gateway + Web Wrapper Hub (v1.8)

One access layer over many AI providers plus a browser-based "web wrapper"
subsystem. The gateway never registers accounts, never defeats CAPTCHA/MFA or
regional blocks, and never touches someone else's cookies or sessions.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/ai-gateway/status` | gateway health: provider counts, strategy, browser availability |
| GET | `/api/v1/ai-gateway/providers` | configured providers (boolean `has_key` only) + kinds + strategies |
| POST | `/api/v1/ai-gateway/providers` | create/update a provider; the API key is sealed and never echoed |
| POST | `/api/v1/ai-gateway/providers/{provider}/toggle` | enable/disable a provider |
| DELETE | `/api/v1/ai-gateway/providers/{provider}` | remove a provider (204) |
| GET | `/api/v1/ai-gateway/settings` | routing settings (strategy, allow-paid, timeout, retries, history) |
| PUT | `/api/v1/ai-gateway/settings` | update one routing setting |
| POST | `/api/v1/ai-gateway/chat` | run a request through the router with failover |
| GET | `/api/v1/ai-gateway/wrappers` | the web-wrapper library (definitions) |
| GET | `/api/v1/ai-gateway/browser` | browser-runtime availability (honest; never claims unprobed) |
| GET | `/api/v1/ai-gateway/use-cases` | capability/use-case matrix per modality |
| GET | `/api/v1/ai-gateway/requests` | bounded observability ring (metadata only — no prompt text) |

**Provider kinds:** `openai_compatible`, `openrouter`, `google`, `anthropic`,
`deepseek`, `ollama` (local), `web` (browser wrapper). **Strategies:** `auto`,
`free_first`, `cheapest`, `fastest`, `best_quality`, `manual`.

The router orders eligible providers (capability match, then strategy, then
priority), retries transient failures with bounded backoff, trips a per-provider
circuit breaker, honours a rate-limit cooldown, and fails over to the next
provider. Every attempt is recorded; the response reports `fallback_used` and the
per-attempt statuses. API keys are sealed with `seal_secret` and registered with
the logging redaction filter — never returned, logged or exported.

Web wrappers drive the owner's **own** logged-in browser session via a
`WrapperDefinition` (URL, selectors, extraction, login markers). The engine runs
the open steps, fills the prompt, submits, reads the newest answer, and returns
`AUTH_REQUIRED` (stopping) when the site asks for a login. The browser runtime is
optional: when unavailable, the wrapper reports honest unavailability rather than
pretending to work. A consistency anchor (`services/ai_gateway_service.py`) and
capability requirement (`ai_provider`) guard against advertising the gateway with
nothing behind it.

A definition with `extraction="structured"` and `extract_attrs` (default
`("href",)`) reads records through `BrowserRuntime.extract(selector, attrs=...)`
and returns them on `ChatResponse.structured` (`{"kind": "extraction", "items":
[…]}`), each item carrying `tag`, `text`, `href` and the requested `attributes`.
Structured extraction is strict: no matching node → `wrapper_selector`, never
fabricated data. A *text* extraction with no match honestly returns the page text.

### Practical verification (v1.8.2, D-115)

The wrapper pipeline is exercised on practical scenarios with no external site,
account or credential, using a local fixture HTTP server:

```bash
PYTHONPATH=. python tests/web_wrapper_bench.py                  # 7/7 scenarios
python -m pytest tests/test_web_wrapper_verification.py \
                 tests/test_ai_gateway_verification.py -q      # CI-safe
# optional real Chromium layer (skips when Playwright/Chromium is absent):
pip install playwright && playwright install chromium
python -m pytest tests/test_web_wrapper_playwright_integration.py -q
```

---

## Versioning

The API is versioned (`/api/v1`). Breaking changes go to a new version path.
Additive changes stay within the current version.
