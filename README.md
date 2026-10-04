# Telegram Channel Management Suite

A modular, locally runnable suite for managing a Telegram channel: a manager bot,
managed bots, user (MTProto) accounts, audience parsing, invites, automatic
reactions, a rules engine with an optional tiny AI classifier, analytics, a
scheduler, a Web UI / Telegram Mini App, and portable Windows + VPS/Docker
deployment — all from **one codebase**.

> Runs locally on a weak Windows PC (portable, no Python/Node/Docker required for
> end users) and on a VPS via Docker, without a separate "server version".

## Documentation (project memory)

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system fits together
- [docs/ROADMAP.md](docs/ROADMAP.md) — phased plan
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

**PHASE 0–11 complete + post-1.0 hardening (v1.0.2).** The suite is
feature-complete against the planned roadmap: manager bot + managed bots, MTProto
user sessions, audience parsing, invites, automatic reactions with a rules engine
and an optional tiny AI classifier, analytics (per-channel), a durable scheduler,
one Vue SPA for the Web UI and the Telegram Mini App, backup/restore, a portable
Windows package, and a VPS/Docker deployment. The post-1.0 work adds versioned
Alembic migrations, a shared Channel Registry, per-channel analytics, CI, a
one-click Mini App setup helper, and reproducible cross-platform portable
packaging (a versioned Windows ZIP is built and attached to each GitHub Release
automatically by the Release workflow).
See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Deployment modes

- **Local dev** — `python -m backend.app.main` (http://127.0.0.1:8000).
- **Windows portable** — unpack, run `portable/run.bat`; no Python/Node/Docker.
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
