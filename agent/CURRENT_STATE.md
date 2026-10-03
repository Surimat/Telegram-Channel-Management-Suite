# CURRENT STATE — Telegram Channel Management Suite

> Persistent project memory. **A new agent must be able to continue from this
> file + git + code alone.** Update this after every major phase.

**Last updated:** 2026-10-03
**Current phase:** PHASE 0 — completed; starting PHASE 1.
**Repository status:** clean, committed.
**Branch:** `main`

---

## 1. Repository audit result

The repository started as an **empty project**: only a 1-line `README.md` and a
shallow clone of `main`. No code, no dependencies, no prior work existed.
Therefore there was nothing to preserve or avoid deleting.

Git: shallow clone → history may be incomplete. Run
`git rev-parse --is-shallow-repository` before history-dependent operations.

## 2. What exists now

Documentation & foundation (PHASE 0):

- `docs/ARCHITECTURE.md` — system architecture, stack, provider abstraction,
  data model, reliability principles, deployment targets, security model.
- `docs/ROADMAP.md` — phased plan (PHASE 0–11).
- `docs/SETUP.md` — local / portable / Docker setup.
- `docs/SECURITY.md` — secret & limits policy + checklists.
- `docs/UI.md` — UI/UX principles and section map.
- `docs/API.md` — REST contract.
- `docs/TROUBLESHOOTING.md` — plain-language fixes.
- `agent/` — persistent memory (this file, NEXT_TASK, DECISIONS, CHANGELOG).
- `.gitignore` — protects secrets, sessions, data, logs, backups, models.
- `.env.example` — annotated configuration template.
- Directory skeleton: `backend/`, `frontend/`, `tests/`, `scripts/`, `docker/`,
  `portable/`, `data/`, `sessions/`, `backups/`, `logs/`, `exports/`.

## 3. What works

- Nothing executable yet (no application code). Documentation and layout only.
- Repository is clean and ready for PHASE 1 code.

## 4. What does NOT exist yet

- FastAPI app, database models, config, logging, health checks.
- Frontend SPA.
- Any Telegram integration.
- Tests.
- Docker / portable packaging.

## 5. Next action

Start **PHASE 1** (see `agent/NEXT_TASK.md`): FastAPI skeleton + config + logging
+ SQLAlchemy/SQLite + health + settings/events/queue models + Vue 3 UI foundation
+ Windows run scripts + Docker foundation + tests + commit.

## 6. Locked decisions (do not break)

See `agent/DECISIONS.md`. Key ones:

- Provider/adapter abstraction for all Telegram access.
- SQLite now, PostgreSQL later, without business-logic rewrite.
- One SPA for Web UI and Mini App; one API.
- One backend for Windows/Linux/portable/Docker.
- AI optional and disableable.
- No bypassing Telegram FloodWait / privacy / admin restrictions.
- Secrets never committed or displayed.

## 7. How to verify state after opening a new chat

```bash
git status && git log --oneline -20
cat agent/CURRENT_STATE.md
cat agent/NEXT_TASK.md
cat agent/DECISIONS.md
cat docs/ROADMAP.md
```
