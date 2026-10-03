# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 8 (Analytics) is **COMPLETE**. Start **PHASE 9** below.

---

## Active task: PHASE 9 — Telegram Mini App

**Goal:** let the *same* Vue SPA run inside Telegram as a Mini App. Do **not**
create a second interface (decision D-003): reuse `frontend/` and the one API.

### Requirements (from the brief)

- Reuse the existing frontend; no separate Mini App codebase.
- Telegram authentication via `initData` (verify the HMAC signature server-side;
  never trust the client).
- Responsive mobile layout inside the Telegram webview.
- At minimum expose: Dashboard, Bots, Reactions, Queue, Audience statistics,
  System health, Settings.
- Local mode still runs at `http://127.0.0.1:<port>` with **no** public server
  required; VPS mode uses the HTTPS public URL. A public server must never be a
  prerequisite for the normal local Web UI.

### Suggested vertical slice (backend + UI + tests + docs)

1. **Backend**
   - Add a `MiniAppService` / auth dependency that verifies Telegram
     `initData` (HMAC-SHA256 with the bot token as the secret key, per Telegram
     docs), checks `auth_date` freshness, and maps the Telegram user id to the
     configured owner/admin.
   - Endpoints: `POST /api/v1/miniapp/auth` (verify + establish a local session),
     `GET /api/v1/miniapp/config` (bot username / feature flags for the client).
   - Settings: mini-app enable flag, allowed owner id(s), `auth_date` max age.
     Keep secrets sealed; never log `initData` or the bot token.
   - Gate mini-app-only access without breaking the local Web UI (local requests
     from `127.0.0.1` remain trusted; see existing security notes).
2. **Frontend**
   - Detect Telegram WebApp (`window.Telegram.WebApp`), call `initData` auth on
     load, and adjust layout (no sidebar on mobile -> bottom/tab navigation).
   - Add the Telegram WebApp script (bundled/static, no CDN dependency for the
     portable runtime) and expand `index.html`/`main.ts` bootstrapping.
   - Keep the desktop Web UI unchanged when not running inside Telegram.
3. **Tests**
   - Unit tests for `initData` verification (valid, tampered, expired, missing).
   - API tests for `/api/v1/miniapp/auth` + `/config` (fake bot token, no network).
   - Ensure no secret/`initData` leaks in responses or logs.
4. **Docs + memory**
   - Update `docs/UI.md`, `docs/API.md`, `docs/SECURITY.md`, `docs/ROADMAP.md`.
   - Update `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` (record the Mini App
     auth decision), `agent/CHANGELOG.md`; then commit.

### Do NOT

- Do not re-open PHASE 8 — it is complete.
- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not require a public HTTPS server for the local Web UI.
- Do not store or log bot tokens, `initData`, or session contents.

### After PHASE 9 (later, in order)

PHASE 10 — Portable Windows packaging (`portable/`, `run.bat`, backup/restore,
smoke tests) and PHASE 11 — VPS/Docker production config + HTTPS docs. Dedicated
Audience/Sources frontend views are also still pending and can be folded into the
UI work.

### Verification checklist for any phase

```bash
python -m pytest                 # must stay green (currently 294 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
