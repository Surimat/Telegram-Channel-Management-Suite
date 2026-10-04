# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-04
**Status:** MAINTENANCE / OPTIONAL EXTENSIONS. The roadmap (PHASE 0–11) is complete.
**v1.0.5 is released** (`develop` prepared it; tag `v1.0.5`; GitHub Release with
the Windows portable ZIP + `.sha256`, built by CI — D-060). The v1.0.5 product
slice: bot↔channel **bindings** + channel **reaction capabilities**, session-free
invite **Кампании** + explainable **donor quality**, **backup delivery
destinations**, a resumable first-run **Setup Wizard**, and a conservative,
off-by-default **auto-update**. Suite is green at **491 passed**; `ruff` clean;
`vue-tsc` + `npm run build` clean; CI enforces the gates (D-053).

---

## Active task: maintenance only (v1.0.5 released)

**Do NOT add new large features and do NOT open a new PHASE.** The goal is to keep
v1.x a tidy product for a real user: accuracy of docs, diagnostics, supportability.

### 1. Release history (done)

v1.0.5 published from `develop` via a reviewed `develop → main` PR → tag `v1.0.5`
→ Release workflow creates the GitHub Release and attaches the Windows portable
ZIP + `.sha256`. No manual step. (v1.0.4: PR #5, merge `3f42c3d`, tag `v1.0.4`;
v1.0.3: PR #4, merge `f18f53a`, tag `v1.0.3`.)

Follow `docs/RELEASE_CHECKLIST.md`. Do **not** push directly to `main`; land via a
reviewed PR. Do **not** move/rewrite the `v1.0.x` tags (D-050).

### 2. Maintenance / optional extensions (only if the owner asks)

The suite is feature-complete. Optional, non-urgent ideas (each needs a recorded
decision and the vertical-slice workflow — backend + DB + UI + tests + docs +
memory + commit):

- A fully automated @BotFather Mini App flow (the one-click menu-button
  registration exists, D-054).
- Short-lived signed session tokens for the Mini App if it is ever exposed beyond
  the owner (D-035).
- Any new feature explicitly requested by the owner.

### 2a. Product slice (done, v1.0.5)

A vertical product slice made the suite usable without a user account:
bot↔channel bindings + channel reaction capabilities (the reaction planner now
honours the channel's real emoji set); session-free invite campaigns with
conservative risk modes; explainable donor-quality indicators; backup delivery
destinations (local / Telegram / Google Drive / Яндекс.Диск, credentials sealed);
a resumable first-run Setup Wizard; and a conservative auto-update. New API +
RU-first UI + tests; Diagnostics gained the new rows/report sections. See
`agent/CHANGELOG.md` and `agent/DECISIONS.md` D-064.

### 2b. Docs-consistency pass (done)

A factual audit brought the docs and memory back in line with the shipped code:
`docs/API.md` (obsolete paths replaced, missing sections added), `docs/UI.md`
(built-views inventory + terminology), `docs/SETUP.md`, `README.md` and the agent
memory. Docs are re-checked against the code each maintenance pass (D-063).

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` lists what is done (§2, §2a–§2f).
- **Diagnostics** (v1.0.3, D-061): `/api/v1/diagnostics` + `/diagnostics` page,
  redacted report (json/txt/zip), safe actions (restart scheduler, recheck
  Telegram, recheck channels, cleanup jobs).
- Versioned Alembic migrations (D-052); Channel Registry (D-051/D-055); manager-bot
  runtime + permission probe (D-047–D-049); reproducible portable build + Release
  workflow (D-056/D-059/D-060).
- Product slice (D-064): `/api/v1/bindings`, `/api/v1/capabilities`,
  `/api/v1/campaigns`, `/api/v1/donors`, `/api/v1/backup/destinations`,
  `/api/v1/promotion`, `/api/v1/update` + RU-first UI.
- Portable build: `scripts/build_portable.sh` (+ `build_win_runtime.py`,
  `win-requirements.lock`). Release process: `docs/RELEASE_CHECKLIST.md`.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006).
- Do not add secrets or database contents to the diagnostics report (D-061).
- Do not auto-install updates: the updater only checks and stages a verified file.

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 491 passed)
ruff check backend tests         # must stay clean
cd frontend && npx vue-tsc --noEmit && npm run build   # outputs to backend/app/static
```
