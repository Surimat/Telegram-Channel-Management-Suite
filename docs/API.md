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
| POST | `/api/v1/system/shutdown` | graceful shutdown (portable/stop.bat) |
| GET | `/api/v1/system/backups` | list backups |
| POST | `/api/v1/system/backups` | create backup |
| POST | `/api/v1/system/backups/restore` | restore backup |
| GET | `/api/v1/system/config/export` | export configuration |
| POST | `/api/v1/system/config/import` | import configuration |

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
| POST | `/api/v1/sessions/{id}/health` | health check (updates status) |
| POST | `/api/v1/sessions/{id}/enable` | enable the account |
| POST | `/api/v1/sessions/{id}/disable` | disable the account |
| POST | `/api/v1/sessions/{id}/logout` | reset local session → re-authorize |
| DELETE | `/api/v1/sessions/{id}` | delete the account + its session file |

Wizard steps: `idle` → `code` → `password` (optional 2FA) → `done`. An interrupted
flow is reset to `auth_required` on startup (`SessionService.recover()`).

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

## Invites

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/invites` | list invite jobs |
| POST | `/api/v1/invites/preview` | build dry-run summary + counts |
| POST | `/api/v1/invites` | create job (requires confirmation) |
| POST | `/api/v1/invites/{id}/start` | start |
| POST | `/api/v1/invites/{id}/pause` | pause |
| POST | `/api/v1/invites/{id}/stop` | stop |
| GET | `/api/v1/invites/{id}/tasks` | per-user task status |

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

## AI classifier (optional)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/ai/status` | classifier status |
| POST | `/api/v1/ai/classify` | classify a text (debug) |

_Planned for PHASE 7._

---

## Analytics

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/analytics/content` | posts, time, reactions, type, category |
| GET | `/api/v1/analytics/audience` | sources, growth, engagement |
| GET | `/api/v1/analytics/dashboard` | dashboard summary + explanations |

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

## Mini App authentication

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/auth/telegram` | validate Telegram WebApp `initData`, start session |
| POST | `/api/v1/auth/logout` | end session |

---

## Versioning

The API is versioned (`/api/v1`). Breaking changes go to a new version path.
Additive changes stay within the current version.
