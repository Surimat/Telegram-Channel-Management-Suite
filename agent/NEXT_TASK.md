# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 0–11 **and** the polish items (Audience/Sources views, automated
portable runtime staging) are complete. Everything left is optional hardening.

---

## Active task (optional): hardening backlog

The core product is feature-complete and green. Pick the next item only if asked
or if it unblocks a real user problem; keep each change a runnable vertical slice.

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
python -m pytest                 # must stay green (currently 333 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
