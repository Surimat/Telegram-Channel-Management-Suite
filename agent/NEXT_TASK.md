# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 1 — Application skeleton

---

## Goal of this phase

Leave the project **runnable** with a solid backend + DB + config + logging +
health checks + a minimal UI foundation + Windows scripts + Docker foundation,
covered by tests.

## Deliverables

### Backend
- [ ] `backend/app/main.py` — FastAPI app factory, lifespan (startup/shutdown).
- [ ] `backend/app/core/config.py` — pydantic-settings, reads `.env`, `SecretStr`
      for secrets, paths for data/sessions/logs/backups.
- [ ] `backend/app/core/logging.py` — structured logging + **secret redaction**.
- [ ] `backend/app/core/paths.py` — resolves predictable runtime directories.
- [ ] `backend/app/core/security.py` — secret key handling, hashing helpers.
- [ ] `backend/app/db/base.py` — declarative Base, naming convention.
- [ ] `backend/app/db/session.py` — async engine + session factory.
- [ ] `backend/app/db/models/` — `settings`, `events`, `job_queue` (start here;
      more models per phase).
- [ ] `backend/app/db/repositories/` — repository layer (no raw SQL in services).
- [ ] `backend/app/services/settings_service.py`, `events_service.py`,
      `queue_service.py`.
- [ ] `backend/app/api/v1/` — `system`, `settings`, `events`, `queue` routers.
- [ ] `backend/app/api/schemas/` — pydantic request/response models.
- [ ] `backend/app/api/errors.py` — uniform error envelope + handlers.
- [ ] Health endpoints `/health`, `/health/deep`.
- [ ] Static file hosting for the built SPA.
- [ ] Alembic scaffold.

### Frontend
- [ ] `frontend/` Vue 3 + Vite + TS.
- [ ] App shell, routing, API client.
- [ ] Sections scaffolding: Dashboard, System, Settings, Logs, Queue (placeholders
      wired to real endpoints where available).
- [ ] Build output → `backend/app/static/`.

### Ops / packaging
- [ ] `backend/requirements.txt` + `requirements-dev.txt`.
- [ ] `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- [ ] `portable/run.bat`, `portable/stop.bat` (skeleton; full packaging PHASE 10).
- [ ] `docker/Dockerfile`, `docker/docker-compose.yml`, `docker/.dockerignore`.

### Tests
- [ ] config, db, health, settings/events/queue API smoke tests.
- [ ] Pytest fixtures with a temporary SQLite DB.

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`.
- [ ] `git diff` review + security checklist.
- [ ] Commit.

## Constraints / reminders

- Do not add Redis/Kafka/Celery/PostgreSQL.
- Do not hardcode credentials; never log secrets.
- Keep it runnable: the app must start and serve `/health` at the end.

## After PHASE 1

Proceed to **PHASE 2 — Telegram foundation** (see `docs/ROADMAP.md`).
