# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 0–11, the polish items, **and the RC/hardening pass are complete
in code**. Three real bugs were found by an end-to-end RC run and fixed (D-044,
D-045, D-046) with regression tests; the suite is green at **336 passed**.

---

## Active task: optional hardening (RC is shipped)

The RC hardening commit is pushed to `develop` and PR #1
(https://github.com/Surimat/Telegram-Channel-Management-Suite/pull/1) is
refreshed and awaiting owner merge. Nothing is blocking. Pick the next item only
if asked or if it unblocks a real user problem:

### Candidates (in rough priority)

1. **Manager-bot runtime** — a command loop + admin whitelist + notification
   forwarding for the manager bot (today it is only registered from settings).
   Keep Telegram calls behind the existing providers (D-001).
2. **Alembic migrations** — replace `create_all` at startup with versioned
   migrations (do not break the current startup path until migrations are proven).
3. **Account permission probe** — a standalone "check channel read/post rights"
   flow using `SessionProvider.resolve_entity` / `get_participants`.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` §4 lists every remaining gap.
- Portable build is zero-setup: `scripts/fetch_embedded_python.sh` +
  `scripts/build_portable.sh` (D-043).
- Audience/Sources UI: `frontend/src/views/{SourcesView,AudienceView}.vue` (D-042).

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 336 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
