# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-06
**Status:** **v1.5.0 forensic audit complete; five confirmed fixes applied (D-095…D-098).**
An independent audit verified the claimed v1.5.0 state against the code and fixed:
(1) `config_sync`/`media_conversion` falsely reported `available` — now
`not_implemented` (`implemented=False`) with a CI check
(`check_capability_implementation`); (2) consistency checks that raised were
silently swallowed — now an `error` finding `audit.check_failed.<name>`;
(3) the stored `language` preference was write-only — `GET /api/v1/capability-graph`
now honours it and Settings has a real RU/EN selector; (4) the runtime Docker image
reported `overall: fail` because it ships no frontend/docs source — source checks
now report `audit.source_unavailable.<name>` as **info**; (5) `README.md` version
drift. Suite green at **731 passed**; `ruff` clean; `vue-tsc` + `npm run build`
clean; Docker `/api/v1/consistency` = `pass`. **Remaining:** commit on `develop`,
push, open a `develop → main` PR and merge per the release checklist
(D-050/D-060); no new features.
Previous: **v1.5.0 Capability graph + i18n + Consistency Auditor is released**
(PR #11, merge `ad24bc6`, tag `v1.5.0`). The roadmap (PHASE 0–11) is complete.

---

## Active task: finish the v1.5.0 forensic audit (commit → push → PR)

The audit is done and the fixes are applied and tested on `develop` (uncommitted).
The single remaining step is to **commit, push `develop`, open a reviewed
`develop → main` PR and merge** (never a direct push to `main`; never force-push;
D-050/D-060). This is a **patch-level maintenance change** (audit fixes only, no
new features): release as **v1.5.1**. Do **not** add new large features and do
**not** open a new PHASE.

### Forensic audit findings (D-095…D-098) — fixed, do not re-fix

1. **False capability** — `config_sync` returned `available` on an empty install
   with no implementation; `media_conversion` was listed with no ffmpeg tooling.
   Fixed: `Capability.implemented=False` → `STATE_NOT_IMPLEMENTED`
   ("Не реализовано"), mirrored through the API; `check_capability_implementation()`
   fails CI if any capability claims `implemented` without code.
2. **Silent failure** — `ConsistencyAuditor._runtime_findings` and
   `run_static_checks` used `except Exception: continue`. Fixed: a raising check
   now emits an `error` finding `audit.check_failed.<name>`.
3. **Write-only language preference** — the `language` setting and i18n catalog
   were never consumed. Fixed: `GET /api/v1/capability-graph` resolves the saved
   preference; Settings gained an RU/EN selector; the help store exposes
   `language`/`availableLanguages`.
4. **Runtime-image false failure** — the Docker smoke surfaced that the honest
   no-silent-failure runner reported `overall: fail` in the runtime image (no
   `frontend/`/`docs/` source). Fixed: source-comparison checks report
   `audit.source_unavailable.<name>` as **info** and are skipped; Docker is `pass`.
5. **Doc drift** — `README.md` said "Current stable release: `v1.4.0`". Fixed.

Tests added: `test_unimplemented_capabilities_are_never_available`,
`test_capability_graph_language_follows_ui_preference`,
`test_capabilities_have_implementations`,
`test_auditor_never_swallows_a_failed_check`,
`test_missing_source_tree_is_info_not_error`.

### Verification for this change

```bash
python -m pytest                 # 731 passed
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
```

### What v1.5.0 adds (do not rebuild)

- **Capability graph** (D-092): `services/capability_graph.py`
  (`context_from_db`, `evaluate_all`, `CapabilityState`),
  `api/v1/capability_graph.py` + `api/schemas/capability.py`
  (`GET /api/v1/capability-graph`), embedded in `WizardState.capabilities` and
  rendered on the Dashboard ("Что уже доступно").
- **i18n** (D-093): `core/i18n.py` (RU/EN catalog, `translate`,
  `normalize_language`, `missing_keys`), `services/ui_prefs.py` (`language`
  preference on `/api/v1/help/prefs`).
- **Consistency Auditor** (D-094): `services/consistency_types.py`,
  `services/consistency_checks.py` (static), `services/consistency.py` (runtime),
  `api/v1/consistency.py` + `api/schemas/consistency.py`
  (`GET /api/v1/consistency`), Diagnostics "Проверка целостности" panel. Static
  checks also run in `pytest` (`tests/test_architecture_consistency.py`).

### 1. Release v1.5.0 (done)

Merged via a reviewed PR #11 (`develop → main`, merge `ad24bc6`), tagged `v1.5.0`;
the Release workflow (run `37442056281`) created the GitHub Release and attached
the Windows portable ZIP + `.sha256` (D-060). `develop` was synced back to the
merge commit. No direct push to `main`; the `v1.0.0`–`v1.4.0` tags were not moved
(D-050).

### 2. Release history (done)

v1.4.0 merged via reviewed PR #10 (`develop → main`, merge `306672e`), tagged
`v1.4.0`. v1.3.0 merged via reviewed PR #9 (`develop → main`, merge `7788125`),
tagged `v1.3.0`. v1.2.0 merged via reviewed PR #8 (`develop → main`, merge
`ea6c161`), tagged `v1.2.0`. v1.1.0 via PR #7 (merge `3438305`), tag `v1.1.0`.
v1.0.5 via PR #6 (merge `496598f`) → tag `v1.0.5` → Release workflow created the
GitHub Release and attached the Windows portable ZIP + `.sha256`. No manual step.
(v1.0.4: PR #5, merge `3f42c3d`, tag `v1.0.4`; v1.0.3: PR #4, merge `f18f53a`,
tag `v1.0.3`.)

### 3. Worker Mesh verification (done — verified 2026-10-05)

**Status: PARTIAL.** The LAN Mesh ships the *worker primitives* (the `WORKER`
role, capability advertisement/matching, fencing-token leases that a worker can
acquire/complete, `reclaim_expired`, coordinator election, and the
coordinator-only poller guard in `main.py`), but there is **no remote
job-dispatch + worker-execution loop** — `MeshTransport` is used only for the
`/api/v1/mesh/ping` liveness probe, and leases are acquired/completed locally via
`/api/v1/mesh/leases/*`. `MeshMode.VPS_WORKER` is a declared enum/config value
only; there is no PostgreSQL control plane (D-002). So the LAN Mesh is a real
coordination layer for the owner's own computers, **not** a distributed job mesh.
Do not claim remote worker execution until a dispatch + execution loop exists.

### 4. Maintenance / optional extensions (only if the owner asks)

- A remote job-dispatch + worker-execution loop over `MeshTransport` (turning the
  PARTIAL Worker Mesh primitives into real remote execution) — only if the owner
  asks; record a decision first.
- A fully automated @BotFather Mini App flow (the one-click menu-button
  registration exists, D-054).
- Short-lived signed session tokens for the Mini App if it is ever exposed beyond
  the owner (D-035).
- A reliable, permissively-licensed TDATA converter adapter behind the existing
  `TdataImportProvider` seam (D-070); today TDATA honestly reports
  `NOT AVAILABLE` when no converter is installed.
- Windows toast delivery currently depends on an optional toast library; a
  bundled, dependency-free toast backend could remove that condition.
- Any new feature explicitly requested by the owner.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` lists what is done (§2, §2a–§2h).
- **v1.4.0 Notification Center + Tray Agent + Editorial Workspace (D-084…D-091):**
  `/api/v1/notifications/*` (settings, history, dashboard, test, read) +
  `/api/v1/editorial/*` (rooms, check, members, board, items, move, reorder,
  audit); models `NotificationRecord`/`NotificationDelivery`/`EditorialRoom`/
  `EditorialMember`/`EditorialItem`/`EditorialAuditEntry`; migration
  `20261006_1000_e7a1c9d2f4b8`; the `tray/` package
  (`python -m backend.app.tray.agent`); two RU-first UI pages (`/notifications`,
  `/editorial`).
- **v1.3.0 Bot Factory + LAN Mesh (D-077…D-083):** `/api/v1/bot-factory/*`
  (templates, dashboard, batches, check, create, adopt, tokens, bind) +
  `/api/v1/mesh/*` (status, discover, peers, pairing-code, pair, unpair, probe,
  elect, leases) and two RU-first UI pages (`/bot-factory`, `/mesh`). Models
  `BotBatch`/`BotCandidate`/`MeshNode`/`MeshPeer`/`PairingCode`/`MeshLease`;
  migration `20261005_1600_d5b2e9c3f7a1`; the `mesh.tick` durable maintenance job.
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
- Do not add secrets or database contents to the diagnostics report (D-061) or to
  the notification history (D-084).
- Do not auto-install updates: the updater only checks and stages a verified file.
- Do not search for, download or bulk-register third-party accounts (D-070).
- Do not treat a Telegram username as an identity (editorial roles use numeric
  ids, D-090).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 702 passed)
ruff check backend tests         # must stay clean
cd frontend && npx vue-tsc --noEmit && npm run build   # outputs to backend/app/static
```
