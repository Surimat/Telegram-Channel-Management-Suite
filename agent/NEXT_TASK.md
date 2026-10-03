# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 11 (VPS/Docker) is **COMPLETE**; the planned PHASE 0–11 roadmap
is done. Start the **post-roadmap polish** task below.

---

## Active task: Audience & Sources frontend views (post-roadmap polish)

**Goal:** close the main UI gap. The Audience/Sources **API is already complete**
(PHASE 5) — only the Vue views are missing. Do not change the backend unless a
bug is found.

### What exists (do not rebuild)

- `backend/app/api/v1/audience.py` + `schemas/audience.py` — sources CRUD, scan,
  user list (search/filter/tags/sort/pagination), export/import, statistics.
- `frontend/src/api/client.ts` — audit it for existing audience/source methods;
  add typed methods/types if missing.
- Existing views to mirror for style: `BotsView.vue`, `AudienceView`/`Sources`
  placeholders if present, `AnalyticsView.vue` (charts), `BackupView.vue` (RU
  copy + confirmations).

### Deliverable (one vertical slice)

1. **SourcesView.vue** — list sources (title, username, type, last scan,
   participants found, status/errors); add source; trigger scan; per-source
   statistics; enable/disable.
2. **AudienceView.vue** — paginated user table; search, filters, tags, sorting;
   empty/loading states; export; import; friendly Telegram-error messaging.
3. Router + sidebar nav entries; RU-first copy; help tooltips; confirmations.
4. Tests: extend `tests/test_audience_api.py` only if backend changes; otherwise
   verify the build and the existing API tests stay green.
5. Docs + memory: `docs/UI.md`, `agent/CURRENT_STATE.md`, `agent/CHANGELOG.md`,
   `docs/ROADMAP.md`; commit.

### Secondary (only after the above)

- Automate staging the Windows embeddable Python into `runtime/` in
  `scripts/build_portable.sh` for a truly zero-setup binary (D-040).

### Do NOT

- Do not re-open PHASE 8–11 — they are complete.
- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not store or log bot tokens, `initData`, or session contents.

### Verification checklist for any phase

```bash
python -m pytest                 # must stay green (currently 330 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
