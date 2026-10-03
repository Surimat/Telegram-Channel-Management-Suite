# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** v1.0.0 released; **hardening on `develop`**: versioned Alembic
migrations, the Channel Registry, CI, the Mini App setup helper and per-channel
analytics are complete (committed). Suite is green at **422 passed**; `ruff`
clean; SPA builds.

---

## Active task: continue on `develop` (optional items)

The project is released and stable. Continue development on `develop`; pick the
highest-value optional item, work it as one vertical slice (code + tests + docs +
memory), keep the suite green, and push `develop` (no force). No known functional
gaps remain — treat further work as polish/robustness only:

1. **Robustness sweeps** — e.g. broader error-path coverage, portable/Docker
   smoke checks, or UX polish. Keep each change small and verified.

Done recently (do not rebuild):
- GitHub Actions CI (D-053, `.github/workflows/ci.yml`) runs ruff + pytest and the
  frontend build on `main`/`develop`.
- **Mini App setup helper** (D-054, `POST /api/v1/miniapp/setup` + the Settings
  card) registers the bot's Web App menu button — no manual @BotFather step.
- **Per-channel analytics** (D-055): `/api/v1/analytics/*` accept `channel_id`;
  the Analytics page has a channel selector.

Do **not** create artificial new phases and do **not** re-open PHASE 8–11.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` §2a/§2b/§4 lists what is done and the
  remaining gaps.
- Manager bot: `backend/app/manager/{bus,service,runtime}.py`, `/api/v1/manager/*`,
  RU commands, admin whitelist, notification toggles in Settings UI.
- Permission probe: `PermissionService`, `PermissionCheck`, `/api/v1/permissions/*`,
  panel in the Sessions page.
- Portable build is zero-setup: `scripts/fetch_embedded_python.sh` +
  `scripts/build_portable.sh` (D-043).
- Release process: `docs/RELEASE_CHECKLIST.md`.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 413 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
