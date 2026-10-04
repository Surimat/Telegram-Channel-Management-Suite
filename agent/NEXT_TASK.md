# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-04
**Status:** MAINTENANCE / OPTIONAL EXTENSIONS. The roadmap (PHASE 0–11) is complete.
`main` = `61d39fa` (tag `v1.0.2`, GitHub Release with the Windows portable ZIP +
`.sha256`). `develop` carries the **v1.0.3 product polish** (Diagnostics + redacted
report + safe maintenance actions). Suite is green at **447 passed**; `ruff`
clean; `vue-tsc` + `npm run build` clean; CI enforces the gates (D-053).

---

## Active task: publish v1.0.3, then maintenance only

**Do NOT add new large features and do NOT open a new PHASE.** The goal is to keep
v1.x a tidy product for a real user: accuracy of docs, diagnostics, supportability.

### 1. Publish v1.0.3 (standard flow)

1. Push `develop`; confirm CI green.
2. Open/merge the reviewed `develop → main` PR (no force).
3. Tag the merged `main` commit `v1.0.3` (annotated) and push it.
4. The **Release** workflow (`.github/workflows/release.yml`) creates the GitHub
   Release and attaches the Windows portable ZIP + `.sha256` — fully automated
   (D-060).
5. Verify the release, assets and checksum; sync `main` back into `develop`.
6. Update memory; keep this task at MAINTENANCE / OPTIONAL EXTENSIONS.

Follow `docs/RELEASE_CHECKLIST.md`. Do **not** push directly to `main`; land via a
reviewed PR. Do **not** move/rewrite `v1.0.0`/`v1.0.1`/`v1.0.2` tags (D-050).

### 2. Maintenance / optional extensions (only if the owner asks)

The suite is feature-complete. Optional, non-urgent ideas (each needs a recorded
decision and the vertical-slice workflow — backend + DB + UI + tests + docs +
memory + commit):

- A fully automated @BotFather Mini App flow (the one-click menu-button
  registration exists, D-054).
- Short-lived signed session tokens for the Mini App if it is ever exposed beyond
  the owner (D-035).
- Any new feature explicitly requested by the owner.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` lists what is done (§2, §2a–§2d).
- **Diagnostics** (v1.0.3, D-061): `/api/v1/diagnostics` + `/diagnostics` page,
  redacted report (json/txt/zip), safe actions (restart scheduler, recheck
  Telegram, recheck channels, cleanup jobs).
- Versioned Alembic migrations (D-052); Channel Registry (D-051/D-055); manager-bot
  runtime + permission probe (D-047–D-049); reproducible portable build + Release
  workflow (D-056/D-059/D-060).
- Portable build: `scripts/build_portable.sh` (+ `build_win_runtime.py`,
  `win-requirements.lock`). Release process: `docs/RELEASE_CHECKLIST.md`.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006).
- Do not add secrets or database contents to the diagnostics report (D-061).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 447 passed)
ruff check backend tests         # must stay clean
cd frontend && npx vue-tsc --noEmit && npm run build   # outputs to backend/app/static
```
