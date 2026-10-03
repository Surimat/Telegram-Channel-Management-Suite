# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 9 (Mini App) is **COMPLETE**. Start **PHASE 10** below.

---

## Active task: PHASE 10 — Portable Windows packaging

**Goal:** unpack a folder → run `run.bat` → the app starts → the browser opens →
it works. No Python/Node/npm/Docker/PostgreSQL/Redis installation required.

### Requirements (from the brief)

- Self-contained: embed the Python runtime and dependencies; the built SPA is
  already served by FastAPI (no Node at runtime, D-012).
- Predictable layout, e.g.:
  ```
  TelegramChannelManagementSuite/
      app/        runtime/    data/
      sessions/   backups/    logs/
      exports/    run.bat     stop.bat   README.txt
  ```
- All mutable state under `data/`, `sessions/`, `backups/`, `logs/`, `exports/`.
- `run.bat`: start the server and open the browser; `stop.bat`: graceful
  shutdown. Reuse the existing `TCMS_ROOT`/paths layer (D-004) — do not fork a
  "portable version" of the backend.
- Backup/restore: SQLite DB, configuration, rules, reaction profiles, app state;
  **session files handled separately and safely**. Add Create/Restore backup +
  Export/Import configuration.
- A portable **startup smoke test** (starts the app, checks `/health`, stops it).

### Suggested vertical slice

1. **Scripts**: finish `portable/run.bat`, `portable/stop.bat`; add a build
   script that assembles the portable folder from the repo (`scripts/`), copying
   `backend/`, the built `backend/app/static/`, `runtime/`, and empty data dirs.
2. **Backup/Restore service + API**: `services/backup_service.py` (zip the DB +
   settings/rules/profiles/state; sessions optional and separate),
   `api/v1/backup.py` (`GET/POST create`, `POST restore`, `export/import config`),
   and a `SettingsView`/`SystemView` control. Never include session files by
   default; never log secrets.
3. **Smoke test**: `tests/test_portable_smoke.py` (start app with `TCMS_ROOT` in
   a temp dir, assert `/health` + SPA serve, clean shutdown).
4. **Docs + memory**: `docs/SETUP.md`, `docs/TROUBLESHOOTING.md`, `README.txt`
   (portable), then update `agent/CURRENT_STATE.md`, `agent/DECISIONS.md`,
   `agent/CHANGELOG.md`, `docs/ROADMAP.md`; commit.

### Do NOT

- Do not re-open PHASE 8/PHASE 9 — they are complete.
- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not require a public HTTPS server for the local Web UI.
- Do not store or log bot tokens, `initData`, or session contents.
- Do not create a second backend for portable mode (D-004).

### After PHASE 10

PHASE 11 — VPS/Docker production config + HTTPS docs. Dedicated Audience/Sources
frontend views are still pending and can be folded into UI work.

### Verification checklist for any phase

```bash
python -m pytest                 # must stay green (currently 313 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
