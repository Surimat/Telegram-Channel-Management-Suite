# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-04
**Status:** **v1.1.0 READY TO RELEASE** (on `develop`). The roadmap (PHASE 0–11)
is complete. **v1.0.5 is released** (merge `496598f` on `main`; PR #6; tag
`v1.0.5`; GitHub Release with the Windows portable ZIP + `.sha256`, built by CI —
D-060). **v1.1.0** completes the requested vertical slice: the multi-format
**Account Hub** importer, optional per-account **network routes (proxies)**,
**donor discovery**, a **lightweight local encoder** (+ optional **ruBERT-tiny2**
embeddings) and the **bot-only / risk UX**. Version strings already read `1.1.0`.
Suite is green at **574 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean;
CI enforces the gates (D-053).

---

## Active task: release v1.1.0, then maintenance only

**Do NOT add new large features and do NOT open a new PHASE.**

### 1. Release v1.1.0 (next action)

Follow `docs/RELEASE_CHECKLIST.md`:

1. Commit the v1.1.0 work on `develop` (docs + agent memory + tests + `.gitignore`
   + the cp775 mojibake fix in `docs/API.md`) and push `develop`.
2. Wait for green CI (`ruff` + `pytest`; `npm ci` + `npm run build`).
3. Open a reviewed **`develop → main`** PR, merge it (never a direct push to
   `main`).
4. Tag the merged `main` commit **`v1.1.0`** and push the tag; the **Release**
   workflow builds the Windows portable ZIP via `scripts/build_portable.sh` and
   attaches it (+ `.sha256`) to the GitHub Release (D-060).

Do **not** move/rewrite the `v1.0.0`–`v1.0.5` tags (D-050).

### 2. Release history (done)

v1.0.5 published from `develop` via reviewed PR #6 (`develop → main`, merge
`496598f`) → tag `v1.0.5` → Release workflow created the GitHub Release and
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

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` lists what is done (§2, §2a–§2g).
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
