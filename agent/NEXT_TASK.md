# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-05
**Status:** **v1.2.0 Content Studio is released** (PR #8 `develop → main`, merge
`ea6c161`, tag `v1.2.0`; GitHub Release with the Windows portable ZIP + `.sha256`,
built by CI — D-060). It adds the v1.2 **content-studio foundation**
(D-071…D-076): content sources (Telegram / RSS / Atom / manual), deduplication, an
explainable cleaner, usage-rights tracking + attribution, markup validation + a
Telegram-like preview, inline buttons, per-source moderation, multi-channel
planning/calendar, and publishing through a `PostingProvider` (bot by default)
with durable auto-delete and first comments. v1.1.0 remains released. The roadmap
(PHASE 0–11) is complete. Version strings read `1.2.0`. Suite is green at **611
passed**; `ruff` clean; `vue-tsc` + `npm run build` clean; CI enforces the gates
(D-053).

---

## Active task: maintenance only

**Do NOT add new large features and do NOT open a new PHASE.** The suite is
feature-complete; there is no required next phase.

### 1. Release v1.2.0 (done)

Merged via reviewed PR #8 (`develop → main`, merge `ea6c161`), tagged `v1.2.0`;
the Release workflow created the GitHub Release and attached the Windows portable
ZIP + `.sha256` (D-060). `develop` was synced back to the merge commit. Do **not**
push directly to `main` and do **not** move/rewrite the `v1.0.0`–`v1.2.0` tags
(D-050).

### 2. Release history (done)

v1.1.0 merged via reviewed PR #7 (`develop → main`, merge `3438305`), tagged
`v1.1.0`. v1.0.5 published from `develop` via reviewed PR #6 (`develop → main`,
merge `496598f`) → tag `v1.0.5` → Release workflow created the GitHub Release and
attached the Windows portable ZIP + `.sha256` (~24 MB, checksum verified). No
manual step. (v1.0.4: PR #5, merge `3f42c3d`, tag `v1.0.4`;
v1.0.3: PR #4, merge `f18f53a`, tag `v1.0.3`.)

### 3. Maintenance / optional extensions (only if the owner asks)

- A fully automated @BotFather Mini App flow (the one-click menu-button
  registration exists, D-054).
- Short-lived signed session tokens for the Mini App if it is ever exposed beyond
  the owner (D-035).
- A reliable, permissively-licensed TDATA converter adapter behind the existing
  `TdataImportProvider` seam (D-070); today TDATA honestly reports
  `NOT AVAILABLE` when no converter is installed.
- Any new feature explicitly requested by the owner.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` lists what is done (§2, §2a–§2h).
- **v1.2.0 Content Studio (D-071…D-076):** `/api/v1/content/*` (sources, grab,
  items, clean, rewrite, rights, buttons, plan, schedule, publish, retry,
  calendar, dashboard, tick) + the `/content` RU-first UI page. Models
  `ContentSource`/`ContentItem`/`MediaAsset`/`Publication`/`ButtonSet`/
  `CommentPlan`; migration `20261005_1200_c4a1f8b2e6d9`. The `content.posting`
  durable periodic tick drives due work.
- **v1.1.0 (D-065…D-070):** `/api/v1/proxies` (network routes), `/api/v1/discovery`
  (donor discovery), the lightweight encoder + `/api/v1/ai/encoder/*`, the Account
  Hub importer (`/api/v1/sessions/import/detect`, `/import/artifact`,
  `/{id}/risk`), intent-narrowed reactions, bot-only analytics and the adaptive
  wizard. Migrations: `20261004_2047_76d92fe3e70b` (+ posts.intent /
  restriction_count follow-ups).
- **Diagnostics** (v1.0.3, D-061): `/api/v1/diagnostics` + `/diagnostics` page,
  redacted report (json/txt/zip), safe actions.
- Versioned Alembic migrations (D-052); Channel Registry (D-051/D-055);
  manager-bot runtime + permission probe (D-047–D-049); reproducible portable
  build + Release workflow (D-056/D-059/D-060).
- Product slice (D-064): `/api/v1/bindings`, `/api/v1/capabilities`,
  `/api/v1/campaigns`, `/api/v1/donors`, `/api/v1/backup/destinations`,
  `/api/v1/promotion`, `/api/v1/update` + RU-first UI.
- Portable build: `scripts/build_portable.sh` (+ `build_win_runtime.py`,
  `win-requirements.lock`). Release process: `docs/RELEASE_CHECKLIST.md`.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `tdata`, `.env`, models or secrets into the
  portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006); proxies are a
  connection route only (D-065).
- Do not add secrets or database contents to the diagnostics report (D-061).
- Do not auto-install updates: the updater only checks and stages a verified file.
- Do not search for, download or bulk-register third-party accounts (D-070).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 574 passed)
ruff check backend tests         # must stay clean
cd frontend && npx vue-tsc --noEmit && npm run build   # outputs to backend/app/static
```
