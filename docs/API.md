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

## Sessions (user accounts)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/sessions` | list accounts (owner labels) |
| POST | `/api/v1/sessions/start` | start auth wizard (api id/hash, phone) |
| POST | `/api/v1/sessions/verify` | submit code |
| POST | `/api/v1/sessions/password` | submit 2FA password |
| POST | `/api/v1/sessions/import` | import existing `.session` |
| POST | `/api/v1/sessions/{id}/health` | health check |
| DELETE | `/api/v1/sessions/{id}` | revoke + delete |

---

## Audience & Sources

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/sources` | list sources |
| POST | `/api/v1/sources` | add source |
| POST | `/api/v1/sources/{id}/scan` | scan source |
| GET | `/api/v1/sources/{id}/stats` | source statistics |
| GET | `/api/v1/audience` | list users (search/filter/sort/tags) |
| PATCH | `/api/v1/audience/{id}` | edit tags/status |
| POST | `/api/v1/audience/export` | export |
| POST | `/api/v1/audience/import` | import |

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

## Reactions, Rules, AI

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/reactions/profiles` | list reaction profiles |
| POST | `/api/v1/reactions/profiles` | create/update profile |
| POST | `/api/v1/reactions/preview` | preview/simulate plan |
| GET | `/api/v1/reactions/jobs` | scheduled reaction jobs |
| GET | `/api/v1/rules` | list category rules |
| PUT | `/api/v1/rules/{category}` | update a category rule |
| GET | `/api/v1/ai/status` | classifier status |
| POST | `/api/v1/ai/classify` | classify a text (debug) |

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
