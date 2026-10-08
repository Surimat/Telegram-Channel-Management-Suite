# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-08
**Status:** **v1.9.0 Content Operations 2.0 is RELEASED (2026-10-08).** The existing **Content Studio** is extended (not duplicated) into a single pipeline: `source → gather → clean → mini-AI → moderation → publish → comment/delete`. It adds reusable **AI profiles** (prompt/instructions/language/tone/max-length/provider-policy/actions as data), a **lightweight local mini-AI** classifier (category + intent, never an emoji), **human moderation** states, declarative **automation rules** (`SOURCE + CONDITION → ACTION`, a fixed field allow-list, not a script engine) and **secret-free pipeline analytics**. An AI failure never loses material: the item moves to `needs_review` with `ai_status=ai_unavailable` and a clear note. Publication tracks `comment_status` and `delete_status` independently. Version string is **1.9.0**. Additive only — no account registration and no Telegram-limit bypass.

Released via a reviewed `develop → main` PR #22 (merge `997999e`), tag `v1.9.0`;
the Release workflow (run `37775533451`) created the GitHub Release and attached
the Windows portable ZIP (**24 929 020 bytes**, sha256
`3227988c…d2ac`) + `.sha256`. `main` HEAD = `997999e`; `develop` HEAD = `bbe59ac`.
Release ZIP scan: no `.session`/TDATA/DB/model.

Version string is **1.9.0** across `backend/app/__init__.py`,
`pyproject.toml`, `frontend/package.json` + lock.

### What this change does (D-116, additive)

- **AI profiles (as data).** `ai_profiles` table + `AiProfileService`
  (`services/ai_profiles.py`): key, title, language, tone, max length, system
  instructions, provider policy and a validated list of pipeline actions. Built-in
  profiles are seeded and protected from deletion.
- **Automation rules (declarative, not a script engine).**
  `automation_rules` table + `AutomationRuleService`
  (`services/automation_rules.py`): `SOURCE + CONDITION → ACTION` over a fixed
  condition field allow-list and a fixed action allow-list; an unknown action is
  dropped, never executed.
- **Single pipeline service.** `services/content_pipeline.py`
  (`ContentPipelineService`): `classify` (local encoder, advisory), `process`
  (apply a profile through the AI Gateway with failover), `moderate` (human
  approve/reject/review), apply matching rule actions, and secret-free pipeline
  analytics/audit records.
- **Pipeline records.** `content_operations` table — append-only metadata per
  stage; stores no text, keys or credentials.
- **Independent comment/delete tracking.** `publications` gains `profile_key`,
  `ai_instructions`, `comment_status`, `delete_status`.
- **API (`/api/v1/content/*`, all additive):** `ai-profiles` CRUD,
  `/items/{id}/ai/classify`, `/items/{id}/ai/process`, `/items/{id}/moderate`,
  `automation-rules` CRUD, `/items/{id}/apply-rules`, `/pipeline/analytics`.
- **UI.** A new «ИИ и правила» tab in `ContentStudioView.vue` plus per-item
  mini-AI/moderation controls and a `content_operations` help topic.
- **Migration.** `20261012_0900_c3d4e5f6a7b8_v1_9_content_operations.py`
  (revises `b2c3d4e5f6a7`); every new column carries a server default, so an
  existing v1.8 database upgrades in place.

### No active task

**v1.9.0 is RELEASED and verified — there is no pending task.** Do **not** add new
large features. The quality gate was run and passed before the release:

```bash
python -m pytest                                  # 946 passed, 8 skipped
ruff check backend tests                          # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py    # 30/30, 0 false positives
```

The only commit on `develop` after the release is **documentation/memory-only**
(`bbe59ac` release facts), so `develop` is one commit ahead of `main` with **no
code change**. For the next release (only when the owner asks):
branch from `develop`, then a reviewed `develop → main` PR + tag.

**Prior release:** **v1.8.1 (AI Gateway verification patch, D-114) is RELEASED**
via a reviewed `develop → main` PR #20 (merge `bc8382b`), tag `v1.8.1`; the
Release workflow (run `37705225761`) created the GitHub Release and attached the
Windows portable ZIP (24 905 404 bytes, sha256 `0ec6aca1…a9d4`) + `.sha256`.
`main` HEAD = `bc8382b`; `develop` re-synced to `bc8382b`.
An independent verification of the v1.8.0 **AI Gateway + Web Wrapper Hub** proved
it *works* (routing, retry, failover, wrapper engine, availability, secret
safety), not merely that it compiles, and fixed two real defects plus a version
drift — **no new features**. (1) A `web` provider whose `wrapper_id` has no
matching `WrapperDefinition` was reported `available` and lost its configured
name; it is now forced `unavailable` with an explicit reason and keeps its
configured name so a pinned provider still routes by name. (2) `AIRouter._attempt`
returned a transient *response* without retrying (only raised errors were
retried); it now retries both, bounded by the retry budget, then fails over.
(3) `frontend/package-lock.json` read `1.7.0` while the app read `1.8.0` — synced
to the app version and locked by an assertion. New independent gateway behaviour
tests (retry/failover/availability/identity/e2e web answer) and three runtime
meta-audit cases (capability dependency, orphan provider class, unwired control).
Additive only: no account registration and no CAPTCHA/MFA/regional-block or
Telegram-limit bypass. Version strings read **1.8.1**; full suite green (909
passed); `ruff` clean; frontend `vue-tsc` + `npm run build` clean; meta-audit
**30/30, 100%, 0 false positives**.

**Prior release:** **v1.8.0 (AI Gateway + Web Wrapper Hub, D-111…D-113) is
RELEASED** via a reviewed `develop → main` PR #19 (merge `d8c62c1`), tag `v1.8.0`;
the Release workflow (run `37653661662`) created the GitHub Release and attached
the Windows portable ZIP (24 904 789 bytes, sha256 `9bb39e4b…d353c`) + `.sha256`.
`main` HEAD = `d8c62c1`. One access layer over many AI
providers (OpenAI-compatible, OpenRouter, Google, Anthropic, DeepSeek, local
Ollama) plus browser **web wrappers** that drive the owner's own logged-in
session, with strategy-based routing, bounded retries, a per-provider circuit
breaker and automatic failover. Keys are sealed and write-only; the request
journal stores metadata only; the wrapper engine stops at a login wall.

**Previous release:** **v1.7.0 (Bot Factory creation queue) is RELEASED** via a
reviewed `develop → main` PR #18 (merge `48eecdc`), tag `v1.7.0`; the Release
workflow (run `37634439503`) created the GitHub Release and attached the Windows
portable ZIP (24 853 898 bytes, sha256 `a444bb55…e5af`) + `.sha256`. The Bot
Factory batch is now a **durable creation queue** (D-109): the scheduler job
`bot_factory.create` creates the free candidates **one operation per tick**, so a
batch is restart-resumable and can be stopped/resumed; a failed candidate can be
retried or skipped; already-created bots are never rolled back. A display-only
`token_mask` (`1234…xyz`) is derived from the **non-secret numeric bot id**
(D-110). Deep-link batches are not background-ticked. Additive: no account
registration and no Telegram-limit bypass.

**Previous release:** **v1.6.1** (verification patch) via a reviewed
`develop → main` PR #17 (merge `a38823d`), tag `v1.6.1`; the Release workflow (run
`37601801598`) attached the Windows portable ZIP (24 846 601 bytes, sha256
`8b6d7c18…f519`) + `.sha256`. v1.6.1 is a patch over v1.6.0 (Owner Auth + Config
Sync, D-105/D-106); it fixed the owner-guard path-normalisation weakness, the
`config_sync` capability state and the Google Drive `/owner` UI wiring (D-107).

The meta-audit remains a *runtime mutation engine* (D-102) and still detects
**every** seeded defect: **25 total, 25 detected, 0 missed, 100.0%, 0 false
positives, 0 critical/high misses** (`status: clean`); `KNOWN_GAP_IDS` is empty.

Previous release: **v1.5.4** (auditor gaps N/O/P closed, D-104) via a reviewed
`develop → main` PR #15 (merge `b219341`), tag `v1.5.4`; the Release workflow (run
`37522394131`) attached the Windows portable ZIP (24 807 288 bytes, sha256
`ff01f787…dc67a`) + `.sha256`.
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

## Legacy notes: v1.8.0 release (historical — superseded by v1.8.2 at the top)

**v1.8.0 was RELEASED** via a reviewed `develop → main` PR #19 (merge `d8c62c1`),
tag `v1.8.0`; the Release workflow (run `37653661662`) created the GitHub Release
and attached the Windows portable ZIP (24 904 789 bytes, sha256 `9bb39e4b…d353c`)
+ `.sha256`. `main` HEAD = `d8c62c1`; `develop` re-synced to `d8c62c1`. Nothing is
required to follow up. Do **not** add new large features.

### What shipped (additive, v1.8.0)

- **AI Gateway domain** (`backend/app/ai/gateway/`): types, errors, reliability
  (bounded backoff + per-provider circuit breaker + rate-limit cooldown +
  `HealthStore`), `AIProvider` protocol, `HttpTransport` (httpx + fake), `AIRouter`
  (ordering, retry, failover, `describe()` dry-run), registry (single extension
  point).
- **Providers:** OpenAI-compatible, OpenRouter, Google, Anthropic, DeepSeek,
  Ollama (local) and the `web` wrapper provider.
- **Web wrappers:** `WrapperDefinition` (URL, selectors, extraction, login
  markers) + `WebWrapperEngine` driving the owner's own browser session; returns
  `AUTH_REQUIRED` and stops on a login wall. Optional Playwright runtime + fake.
- **Persistence:** `ai_providers` / `ai_route_settings` / `ai_gateway_requests`
  (+ repository), migration `20261008_1200_b2c3d4e5f6a7_v1_8_ai_gateway.py`.
- **Service + API:** `services/ai_gateway_service.py`,
  `api/v1/ai_gateway.py` (injected via `api/deps.py::get_ai_gateway_service`).
- **UI:** `AiGatewayView.vue` (`/ai-gateway`, "Центр ИИ") + nav entry + two help
  topics (`ai_gateway`, `ai_gateway_wrapper`).
- **Guardrails:** `ai_gateway` capability + consistency anchor, i18n keys,
  meta-audit mutations `V_gateway_capability_anchor` and
  `W_frontend_unknown_gateway`.

### Verification

```bash
python -m pytest                 # full suite green
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py         # 27/27, 100%
```

## Previous release: v1.7.0 (Bot Factory creation queue)

**v1.7.0 is RELEASED** via a reviewed `develop → main` PR #18 (merge `48eecdc`),
tag `v1.7.0`; the Release workflow (run `37634439503`) created the GitHub Release
and attached the Windows portable ZIP (24 853 898 bytes, sha256 `a444bb55…e5af`).
`main` HEAD = `48eecdc`; `develop` re-synced to `48eecdc`.

### What shipped (additive)

- **Bot Factory durable creation queue (D-109).** `enqueue_candidates` /
  `run_queue_once` / `queue_progress` / `retry_candidate` / `skip_candidate` /
  `cancel_queue` / `resume_queue`; scheduler job `bot_factory.create` (one op per
  tick, restart-resumable); deep-link batches are not background-ticked.
- **API queue endpoints** under `/api/v1/bot-factory/*` plus a `queue` block on
  the dashboard.
- **`token_mask` (D-110).** Display-only, derived from the non-secret numeric bot
  id; the raw token is never returned/logged/exported.
- Migration `20261008_0900_a1b2c3d4e5f6_v1_7_bot_factory_queue.py`; capability
  `bot_factory`, Diagnostics check, Promotion Wizard step, help topic and
  `BotFactoryView.vue` queue UI.

### Verification

```bash
python -m pytest                 # 854 passed
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
```

## Active task (previous): none — v1.6.1 released

**v1.6.1 is RELEASED** via a reviewed `develop → main` PR #17 (merge `a38823d`),
tag `v1.6.1`; the Release workflow (run `37601801598`) created the GitHub Release
and attached the Windows portable ZIP (24 846 601 bytes, sha256 `8b6d7c18…f519`).
`main` HEAD = `a38823d`; `develop` = `a38823d` (re-synced). Nothing is required to
follow up. Do not add new features.



The v1.6.0 Owner Auth + Config Sync slice was independently verified (D-107). Two
defects and one unwired control were fixed, **additively and with no new features**:

1. **Owner guard path normalisation** — a leading `//` (`//api/v1/...`) skipped the
   guard while the router still matched it; `is_protected` now normalises slashes
   and dot segments and matches the allowlist by segment boundary. Verified on a
   real server with `curl --path-as-is`.
2. **`config_sync` capability** — dropped `minimal=(owner_auth,)`; it is
   `needs_setup` (never `partial`) until a provider is connected.
3. **Google Drive `/owner` UI** — added the missing token field + "save token"
   button calling the existing `syncGoogleConnect` endpoint.

Released as **v1.6.1** (patch) via a reviewed `develop → main` PR and tag; the
Release workflow builds the Windows portable ZIP. After the merge, re-sync
`develop` to the merge commit and record the facts here.

### Verification for this patch

```bash
python -m pytest                 # 843 passed expected
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py         # 25/25, 100%
```

## Active task: none — v1.6.1 released

There is **no required next task**. v1.6.1 is released (PR #17, tag `v1.6.1`) and
the meta-audit still reaches **100% (25/25, 0 false positives)**.

1. **Optional follow-up (next cycle):** only if the owner asks — e.g. a remote
   job-dispatch + worker-execution loop over `MeshTransport`, a reliable
   permissively-licensed TDATA converter, or a dependency-free Windows toast
   backend. Record a decision first.

Do **not** add new large features and do **not** open a new PHASE.

### Owner Auth + Config Sync (v1.6) — implemented, do not rebuild

- **Owner Auth:** `core/owner_security.py` (PBKDF2 verifier + bundle key),
  `services/owner_auth_service.py`, `db/models/owner.py`,
  `db/repositories/owners.py`, `api/owner_guard.py` (default-on middleware),
  `api/schemas/owner.py`, `api/v1/owner.py`; `/owner` UI page + `owner_auth` help
  topic.
- **Config Sync:** `services/config_bundle.py` (AES-256-GCM bundle + secret
  denylist), `services/config_sync_service.py`, `providers/config_sync_base.py` +
  `config_sync_local.py` + `config_sync_gdrive.py`, `db/models/config_sync.py`;
  `/api/v1/owner/sync/*`; `config_sync` help topic, capability and wizard step.
- **Migration:** `20261007_1000_f8b2d3e5a7c9` (`owner_identities`,
  `config_sync_state`).
- **Consistency Auditor:** section `5b-2` guards the config-sync providers and the
  bundle's secret anchors.
- **Tests:** `tests/test_owner_auth.py`, `tests/test_config_sync.py`,
  `tests/test_owner_api.py`.

### Meta-audit engine (D-102) — implemented, do not rebuild

- **Engine:** `tests/meta_audit/engine.py` — `MutationSandbox` (isolated copy),
  `run_mutation`, `run_suite`, `SuiteResult` (derived `detected`/`missed`/
  `kill_rate`/`false_positives`/`critical_misses`/`high_misses`), `write_report`,
  `regression_against`, and a CLI (`python tests/meta_audit/engine.py`).
- **Registry:** `tests/meta_audit/mutations.py` — 25 mutations + 8 negative
  controls. No `detected` field anywhere; `KNOWN_GAP_IDS` is empty (all gaps
  closed).
- **Tests:** `tests/test_consistency_mutations.py` (per-mutation runtime
  classification, negative controls, detector-removal proof, new-mutation proof,
  working-tree isolation) and `tests/test_meta_audit.py` (silent-failure guard,
  runtime drift, generated-report provenance + arithmetic, closed-gap M/N/O/P/Q
  regression).
- **CI job `meta-audit`:** runs the engine, then the tests, then asserts the
  working tree has no synthetic defect. It does **not** compare against a
  hardcoded percentage.
- **Detected now (25):** A, B, C, D, E1, E2, F, F2, G, H, I, J, K, K2, L, M, N, O,
  P, Q, R1, R2, S, T, U.
- **Missed / recorded gaps (0):** none.

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
