# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 10 (Portable packaging + backup/restore) is **COMPLETE**.
Start **PHASE 11** below.

---

## Active task: PHASE 11 — VPS / Docker production configuration

**Goal:** the *same* codebase runs on a VPS via Docker Compose with production
settings, HTTPS documented, and backups work the same way. No separate "server
version".

### Requirements (from the brief)

- Production `Dockerfile` + `docker-compose.yml` + `.env.example` (already
  sketched in `docker/` from PHASE 1 — review, harden, and finish).
- Same architecture and code as local/portable; do **not** fork the backend.
- HTTPS / reverse-proxy documentation (e.g. Caddy/Traefik/nginx) — the owner
  terminates TLS; the app itself stays plain HTTP behind the proxy.
- Backup/restore docs for VPS (use the PHASE 10 `/api/v1/backup` endpoints;
  bind-mount `data/`, `sessions/`, `backups/`, `logs/`, `exports/`).
- Production secret handling: `APP_SECRET_KEY`, `APP_ENV=production`,
  `APP_HOST=0.0.0.0`, secrets via environment / Docker secrets — never in git.

### Suggested vertical slice

1. **Docker**: verify the multi-stage build (Node build → Python runtime,
   non-root) still serves the SPA; ensure volumes and healthcheck (`/health`).
2. **Compose**: one service, named volumes/bind mounts for mutable state,
   `restart: unless-stopped`, env from `.env`.
3. **Reverse proxy**: document HTTPS (Caddy example + nginx example); note the
   Mini App `MINIAPP_PUBLIC_URL` must be the public HTTPS URL.
4. **Docs + memory**: `docs/SETUP.md` (mode C), `docs/SECURITY.md` (VPS
   secrets), `docs/TROUBLESHOOTING.md` (container issues); update
   `agent/CURRENT_STATE.md`, `agent/DECISIONS.md`, `agent/CHANGELOG.md`,
   `docs/ROADMAP.md`; commit.

### Do NOT

- Do not re-open PHASE 8/9/10 — they are complete.
- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not require a public HTTPS server for the local Web UI.
- Do not store or log bot tokens, `initData`, or session contents.
- Do not create a second backend for server mode (D-004).

### After PHASE 11

Dedicated Audience/Sources frontend views remain the main UI gap. A fully
self-contained Windows binary (embedded Python staged into `runtime/`) is an
assembly/packaging step, not a code change.

### Verification checklist for any phase

```bash
python -m pytest                 # must stay green (currently 330 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
