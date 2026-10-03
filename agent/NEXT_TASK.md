# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 0–11, the polish items, the RC/hardening pass, **and the
post-1.0 hardening pass are complete in code**: manager-bot runtime + command
loop + notification forwarding, and the standalone account permission probe.
Suite is green at **384 passed**; `ruff` clean; SPA builds.

---

## Active task: commit & push the hardening pass (then optional items)

The hardening pass (D-047/D-048/D-049) is written, tested and documented but
**not yet committed**. First action:

1. `git add -A && git commit` on `develop` (message: manager runtime +
   notifications + permission probe).
2. Push `develop` (fast-forward, no force) and refresh PR #1
   (https://github.com/Surimat/Telegram-Channel-Management-Suite/pull/1).

After that, only optional items remain:

### Candidates (in rough priority)

1. **Alembic migrations** — replace `create_all` at startup with versioned
   migrations (do not break the current startup path until migrations are proven).
   This is the last documented hardening gap.
2. **Channel binding registry/UI** — an explicit channel registry so posts,
   analytics and permissions share one channel identity.
3. **Mini App BotFather registration** helper — currently a documented manual
   deployment step.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` §2a/§4 lists what is done and the
  remaining gaps.
- Manager bot: `backend/app/manager/{bus,service,runtime}.py`, `/api/v1/manager/*`,
  RU commands, admin whitelist, notification toggles in Settings UI.
- Permission probe: `PermissionService`, `PermissionCheck`, `/api/v1/permissions/*`,
  panel in the Sessions page.
- Portable build is zero-setup: `scripts/fetch_embedded_python.sh` +
  `scripts/build_portable.sh` (D-043).

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 384 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
