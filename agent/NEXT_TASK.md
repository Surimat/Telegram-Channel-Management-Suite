# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 0–11, the polish items, the RC/hardening pass, **and the
post-1.0 hardening pass are complete, committed and pushed** on `develop`
(manager-bot runtime + command loop + notification forwarding; standalone
account permission probe). Suite is green at **384 passed**; `ruff` clean; SPA
builds.

---

## Active task: cut the v1.0.0 release, then optional items

The code is feature-complete and stable on `develop`. The immediate job is to
**release**, not to write new features:

1. Merge PR #1 (`develop → main`) via the GitHub API — do **not** ask the owner.
   PR #1: https://github.com/Surimat/Telegram-Channel-Management-Suite/pull/1
2. Tag `v1.0.0` on the merged `main` commit and publish a GitHub Release with
   notes built from the shipped features.
3. Continue development on `develop` afterwards.

If the merge or release cannot be performed (missing rights / API unavailable),
do **not** fake it: record exactly what happened in `agent/CURRENT_STATE.md` and
leave `develop` stable and pushed.

After the release, only optional items remain:

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
- Release checklist: `docs/RELEASE_CHECKLIST.md`.

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
