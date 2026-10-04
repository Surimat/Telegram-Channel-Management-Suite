# Telegram Channel Management Suite

A modular, locally runnable suite for managing a Telegram channel: a manager bot,
managed bots, user (MTProto) accounts, audience parsing, invites, automatic
reactions, a rules engine with an optional tiny AI classifier, analytics, a
channel registry, a scheduler, a Web UI / Telegram Mini App, backup/restore, and
portable Windows + VPS/Docker deployment — all from **one codebase**.

> Runs locally on a weak Windows PC (portable, no Python/Node/Docker required for
> end users) and on a VPS via Docker, without a separate "server version".

**Current stable release: `v1.0.5`.**

## What it does

- **Manager Bot** — control the suite from Telegram (admin whitelist, notifications).
- **Managed Bots** — add/health/remove Telegram bots; tokens sealed at rest.
- **Bot ↔ channel bindings** — connect a bot to a channel, verify its rights and
  the channel's available reactions (bot-only, no account needed).
- **User Sessions** — MTProto accounts with an interactive auth wizard.
- **Audience** — parse members of channels/groups, search, tag, export.
- **Invite Manager** — build, dry-run, approve and run invite campaigns.
- **Кампании** — invite-link promotion with the manager bot only (no account) and
  explainable source-quality indicators.
- **Reaction Manager** — reaction profiles, emoji weights, delays, simulation.
- **Rules Engine** — per-category rules with allowed/preferred/forbidden emoji.
- **Tiny AI** — optional local classifier (rules-only mode is fully supported).
- **Analytics** — per-channel content, reactions, audience and takeaways.
- **Channel Registry** — one shared channel identity for every module.
- **Mini App** — the same SPA opens inside Telegram (one-click setup helper).
- **Diagnostics** — per-component status in plain language + a redacted report.
- **Setup Wizard** — a resumable first-run guide that reflects real system state.
- **Auto-update** — off-by-default, checks/downloads a SHA-256-verified release.
- **Backup / Restore** — data backups, reviewable config export/import and
  optional delivery destinations (local / Telegram / Google Drive / Яндекс.Диск).
- **Windows Portable** — unpack, run `run.bat`, open the Web UI (zero setup).
- **Docker / VPS** — one compose file, optional Caddy TLS overlay.

## Documentation (project memory)

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system fits together
- [docs/ROADMAP.md](docs/ROADMAP.md) — phased plan (all phases complete)
- [docs/SETUP.md](docs/SETUP.md) — install & run (local / portable / Docker)
- [docs/SECURITY.md](docs/SECURITY.md) — secret & limits policy
- [docs/UI.md](docs/UI.md) — UI/UX principles
- [docs/API.md](docs/API.md) — REST contract
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — fixes & recovery

## Agent / developer state

Persistent memory so work can continue across sessions:

- [agent/CURRENT_STATE.md](agent/CURRENT_STATE.md) — what exists now
- [agent/NEXT_TASK.md](agent/NEXT_TASK.md) — what to do next
- [agent/DECISIONS.md](agent/DECISIONS.md) — locked architecture decisions
- [agent/CHANGELOG.md](agent/CHANGELOG.md) — history

## Status

**PHASE 0–11 complete.** The suite is feature-complete against the planned
roadmap and shipped as **v1.0.5** (the roadmap has no open phases; remaining work
is maintenance / optional extensions). Post-1.0 additions include versioned
Alembic migrations (replacing `create_all`), the shared Channel Registry,
per-channel analytics, GitHub Actions CI, a one-click Mini App setup helper,
reproducible cross-platform portable packaging (a versioned Windows ZIP is built
and attached to each GitHub Release automatically), the **Diagnostics** page
with a **redacted diagnostic report** for support, and a **product slice**:
bot↔channel bindings + reaction capabilities, session-free invite **Кампании**
with source-quality indicators, **backup delivery destinations**, a first-run
**Setup Wizard**, and a conservative, off-by-default **auto-update**.
See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Deployment modes

- **Local dev** — `python -m backend.app.main` (http://127.0.0.1:8000).
- **Windows portable** — unpack the ZIP, run `run.bat`; no Python/Node/Docker.
- **VPS / Docker** — `docker compose -f docker/docker-compose.yml up -d --build`,
  with an optional Caddy TLS overlay (`docker/docker-compose.proxy.yml`).
  See [docs/SETUP.md](docs/SETUP.md).

## Quick start (development)

```bash
cp .env.example .env          # then set APP_SECRET_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
python -m backend.app.main    # http://127.0.0.1:8000
```

## Security

Never commit `.env`, bot tokens, API hashes, session files, passwords, or keys.
See [docs/SECURITY.md](docs/SECURITY.md).
