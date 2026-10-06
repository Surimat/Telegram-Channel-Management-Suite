# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-06
**Status:** **v1.5.3 is RELEASED; the meta-audit is a *runtime mutation engine*
(D-102) and gaps M and Q are CLOSED (D-103).** The kill rate is **computed from
real executions**: `tests/meta_audit/` builds an isolated copy of the source tree
(or a fresh temp DB for runtime checks), injects one seeded defect, runs the
**real** auditor, semantically matches the finding it actually produced, and
records ``detected`` / ``missed``. The report `agent/META_AUDIT_RESULT.json`
carries `result_source: "computed from runtime mutation executions"` and the
arithmetic (`detected + missed == total`, `kill_rate == detected/total*100`) is
asserted in `pytest` and CI. Removing a detector flips its mutation to `missed` and
lowers the kill rate automatically; adding a mutation changes `total`
automatically. There are **25** mutations and **5 negative controls** (a
clean/correct tree must not produce a mutation finding → 0 false positives).
Current computed result: **25 total, 22 detected, 3 missed, kill rate 88.0%,
0 false positives, 0 critical misses, 0 high misses** (`status: gaps_found`).
Two new static detectors closed the remaining HIGH gaps: `check_write_only_settings`
(M — a setting written via `SettingsService.set` with no reader) and
`check_channel_registry_usage` (Q — a channel-aware service module that never uses
a canonical channel identity). The 3 remaining gaps (N unused DB field, O service
without caller, P control without behavior) are recorded in `KNOWN_GAP_IDS` and
still **executed** — not hardcoded as misses.
Released as the patch `v1.5.3` via a reviewed `develop → main` PR; the Release
workflow attaches the Windows portable ZIP + `.sha256`. **`main` = the released tag
`v1.5.3`; `develop` was re-synced from `main` after the release merge.** Latest tag
`v1.5.3`; latest release v1.5.3.
Version strings read **1.5.3**; `ruff` clean; frontend `vue-tsc` + `npm run build`
clean; Docker smoke clean (`/health` → `1.5.2` on the pre-release tree, SPA `200`,
`/api/v1/consistency` → `pass`, 0 error / 0 warning / 6 info).
Previous: **v1.5.1 forensic-audit fixes are released** — reviewed `develop → main`
PR #12 (merge `f41ebc8`), tag `v1.5.1`; the Release workflow (run `37453582161`)
attached the Windows portable ZIP + `.sha256` (D-060). It fixes five confirmed
discrepancies (D-095…D-098): false `available` capabilities; a consistency check
that raised being silently swallowed; a write-only `language` preference;
source-unavailable checks reported as info in the runtime image; and `README.md`
version drift. Previous: **v1.5.0 Capability graph + i18n + Consistency Auditor is
released** (PR #11, merge `ad24bc6`, tag `v1.5.0`). The roadmap (PHASE 0–11) is
complete.

---

## Active task: none — v1.5.3 released (optional: promote the remaining gaps)

There is **no required next task**. v1.5.3 is released, the meta-audit is a
runtime engine (D-102), and the two HIGH gaps M and Q are closed (D-103).

1. **Optional follow-up (next cycle):** promote one of the three remaining
   recorded auditor gaps (N unused DB field, O service without caller, P control
   without behavior — all below high) to a real check. When a gap is closed,
   remove its id from `KNOWN_GAP_IDS` in `tests/meta_audit/mutations.py`; the kill
   rate then rises automatically on the next engine run (no report hand-editing).

Do **not** add new large features, do **not** open a new PHASE, and do **not**
create a release without the owner's ask.

### Meta-audit engine (D-102) — implemented, do not rebuild

- **Engine:** `tests/meta_audit/engine.py` — `MutationSandbox` (isolated copy),
  `run_mutation`, `run_suite`, `SuiteResult` (derived `detected`/`missed`/
  `kill_rate`/`false_positives`/`critical_misses`/`high_misses`), `write_report`,
  `regression_against`, and a CLI (`python tests/meta_audit/engine.py`).
- **Registry:** `tests/meta_audit/mutations.py` — 25 mutations + 3 negative
  controls. No `detected` field anywhere; `KNOWN_GAP_IDS` marks documented gaps
  that are still executed.
- **Tests:** `tests/test_consistency_mutations.py` (per-mutation runtime
  classification, negative controls, detector-removal proof, new-mutation proof,
  working-tree isolation) and `tests/test_meta_audit.py` (silent-failure guard,
  runtime drift, generated-report provenance + arithmetic).
- **CI job `meta-audit`:** runs the engine, then the tests, then asserts the
  working tree has no synthetic defect. It does **not** compare against a
  hardcoded percentage.
- **Detected now (20):** A, B, C, D, E1, E2, F, F2, G, H, I, J, K, K2, L, R1, R2,
  S, T, U.
- **Missed / recorded gaps (5):** M (high), N, O, P, Q (high).

### Verification for this change

```bash
python -m pytest                 # full suite (green)
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py         # regenerates the report
python -m pytest tests/test_consistency_mutations.py tests/test_meta_audit.py -q
```

### What v1.5.1 adds (do not rebuild)

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
python -m pytest                 # must stay green
ruff check backend tests         # must stay clean
cd frontend && npx vue-tsc --noEmit && npm run build   # outputs to backend/app/static
PYTHONPATH=. python tests/meta_audit/engine.py         # regenerates META_AUDIT_RESULT.json
```
