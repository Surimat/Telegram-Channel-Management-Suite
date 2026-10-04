# AGENTS.md — Telegram Channel Management Suite

Persistent, repository-resident memory for AI agents. **Read this first, then
continue only from repository files + git + code** — never rely on chat history.

## Start-of-session checklist

```bash
git status && git log --oneline -20
cat agent/CURRENT_STATE.md      # what exists / what works / what is next
cat agent/NEXT_TASK.md          # the single active task
cat agent/DECISIONS.md          # locked decisions — do not break
cat docs/ROADMAP.md             # phases 0–11
```

## How to work

- Deliver **large vertical phases** (backend + DB + UI + tests for one feature),
  not chains of micro-tasks. Each phase must leave the project runnable.
- Obey locked decisions in `agent/DECISIONS.md` (provider abstraction, SQLite
  now/Postgres later, one SPA + one API, one backend for all platforms, AI
  optional, no bypassing Telegram limits, durable DB queue, never commit or log
  secrets).
- At the end of every phase: update `agent/CURRENT_STATE.md`,
  `agent/NEXT_TASK.md`, `agent/DECISIONS.md`, `agent/CHANGELOG.md`; review
  `git diff`; run tests; commit.

## Commands

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest                # must stay green
python -m backend.app.main      # http://127.0.0.1:8000
ruff check backend tests        # must stay clean

# Frontend (only when changing the UI)
cd frontend && npm install && npm run build   # outputs to backend/app/static
```

## Layout

- `backend/app/` — core → db/models → db/repositories → services → api (+
  scheduler, providers).
- `frontend/` — Vue 3 + Vite + TypeScript SPA; builds into `backend/app/static`.
- `tests/` — unit + db + api + scheduler + smoke, using a temporary SQLite DB.
- `docs/` — architecture, roadmap, setup, security, UI, API, troubleshooting,
  release checklist.
- `agent/` — persistent project memory (the source of truth for continuity).
- `scripts/`, `docker/`, `portable/` — run/build/packaging.

## Releasing

See `docs/RELEASE_CHECKLIST.md`. A release requires all gates green (`pytest`,
`ruff`, `vue-tsc`/`npm run build`), a clean secret scan, memory/docs updated, and
PR `develop → main` merged (never a direct push to `main`).

The version lives in `backend/app/__init__.py` (mirrored in `pyproject.toml` and
`frontend/package.json`). Tag the merged `main` commit `vX.Y.Z`; the **Release**
workflow (`.github/workflows/release.yml`) then builds the Windows portable ZIP
via `scripts/build_portable.sh` and attaches it (+ `.sha256`) to the GitHub
Release. The portable build is reproducible and runs on a Linux CI host.

## Security (non-negotiable)

Never commit or display `.env`, bot tokens, API hashes, session files,
passwords, DB secrets, or keys. A logging redaction filter is mandatory. See
`docs/SECURITY.md`.
