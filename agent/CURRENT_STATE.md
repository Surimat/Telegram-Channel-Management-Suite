# CURRENT STATE ‚Äî Telegram Channel Management Suite

> Persistent project memory. **A new agent must be able to continue from this
> file + git + code alone.** Update this after every major phase.

**Last updated:** 2026-10-09
**Current phase:** **v2.0.0 — the three agreed v2.0 stages (AI Gateway + free multimodal providers, Target Language, mass bot-to-channel onboarding, Content Operations 2.0, hidden windowless launch) — RELEASED (2026-10-09).** Shipped via a reviewed `develop → main` PR #23 (merge `926a3b3`), tag `v2.0.0`; the Release workflow (run `37982855350`) created the GitHub Release and attached the Windows portable ZIP (24 977 686 bytes, sha256 `4d62a52f…bd649`) + `.sha256` (D-060). Release ZIP scan: no `.session`/TDATA/DB/model. Additive migrations `20261012_0900_c3d4e5f6a7b8_v1_9_content_operations.py`, `20261013_0900_d4e5f6a7b8c9_v2_0_target_language.py`, `20261014_0900_e5f6a7b8c9d0_v2_0_bot_onboarding.py`. Version strings read **2.0.0** across `backend/app/__init__.py`, `pyproject.toml`, `frontend/package.json` + lock.
**v1.8.2 RELEASED (2026-10-08) — Web Wrapper Hub practical verification (D-115).** The v1.8.1 wrapper work was "architecturally implemented" but not exercised on practical scenarios end to end. A verification pass over the real engine→provider→router pipeline found a **real defect in the genuine Playwright runtime**: `extract()` read `href` from the matched node itself, so extracting a container (`li.link`, `tr.row`) returned empty links (only visible when the real browser ran). Fixed: extraction now prefers a nested `<a>`; `WrapperDefinition.extract_attrs` configures which attributes are read; the `diagnostics()` `"wrapers"` typo is fixed to `"wrappers"`. Added a deterministic **local fixture site** (`tests/support/web_fixtures.py`), a **benchmark** (`tests/web_wrapper_bench.py`, 7/7), CI-safe verification tests and an optional real-Chromium test (skips when Playwright/Chromium is absent). Released via reviewed PR #21 (merge `8542d4c`), tag `v1.8.2`; Release workflow run `37747125558`, ZIP 24 906 383 bytes, sha256 `f0c6984d…f619`. No schema change.
**v1.8.1 RELEASED (2026-10-08).** AI Gateway verification patch (D-114) shipped via a reviewed `develop ‚Üí main` PR #20 (merge `bc8382b`), tag `v1.8.1`; the Release workflow (run `37705225761`) created the GitHub Release and attached the Windows portable ZIP (24 905 404 bytes, sha256 `0ec6aca1‚Ä¶a9d4`) + `.sha256`. An independent verification of the v1.8.0 **AI Gateway + Web Wrapper Hub** proved it *works* (not just compiles) and fixed two real defects plus a version drift ‚Äî no new features. (1) A `web` provider whose `wrapper_id` has no matching `WrapperDefinition` was reported `available` and lost its configured name; it is now forced `unavailable` with an explicit reason and keeps its configured name so a pinned provider still routes. (2) `AIRouter._attempt` returned a transient *response* without retrying (only raised errors were retried); it now retries both, bounded by the retry budget. (3) `frontend/package-lock.json` read `1.7.0` while the app read `1.8.0` ‚Äî synced + locked by an assertion. New independent gateway behaviour tests (retry/failover/availability/identity/e2e web answer) and three runtime meta-audit cases (capability dependency, orphan provider class, unwired control). Additive only ‚Äî no account registration and no CAPTCHA/MFA/regional-block or Telegram-limit bypass. Version strings read **1.8.1**; full suite green (909 passed); `ruff` clean; `vue-tsc` + `npm run build` clean; meta-audit **30/30, 100%, 0 false positives**.
**v1.7.0 RELEASED (2026-10-08).** Bot Factory creation queue (D-109/D-110) shipped via a reviewed `develop ‚Üí main` PR #18 (merge `48eecdc`), tag `v1.7.0`; the Release workflow (run `37634439503`) created the GitHub Release and attached the Windows portable ZIP (24 853 898 bytes, sha256 `a444bb55‚Ä¶e5af`) + `.sha256`.
**v1.6.1 (patch) is an independent verification of v1.6.0:** it fixes an owner-guard path-normalisation weakness (a leading `//` used to skip the guard while the router still matched it), corrects the `config_sync` capability so "owner ready, no provider" reports `needs_setup` (never a false `partial`), and wires the existing Google Drive token endpoint into `/owner` (D-107). No new features, no schema change. Version strings read **1.6.1**; full suite green (843 passed); `ruff` clean; `vue-tsc` + `npm run build` clean; meta-audit **25/25, 100%, 0 false positives**.
**v1.6.0 (minor) adds an Owner Auth + Config Sync vertical slice (D-105/D-106):** a local owner profile (password/PIN) protects the panel with a PBKDF2 verifier and an HMAC-signed session token (`X-Owner-Token`, default-on middleware), and a **versioned encrypted configuration bundle** (canonical JSON ‚Üí AES-256-GCM, secret denylist) moves settings to a new computer via a local folder or Google Drive (app-data scope) ‚Äî never the DB, sessions or TDATA. Owner Auth is **local-first**: while no profile exists the panel stays open exactly as before; sync detects conflicts instead of overwriting silently. The `/owner` RU-first UI page, `/api/v1/owner/*` endpoints, `owner_auth`/`config_sync` help topics, Diagnostics checks and a Promotion Wizard step are wired in. Additive only; no account registration and no Telegram-limit bypass. That release read **1.6.0** with 822 tests; `ruff` clean; `vue-tsc` + `npm run build` clean; meta-audit **25/25, 100%, 0 false positives**.
**v1.5.4 (patch) closed the last three Consistency Auditor gaps N, O and P (D-104); the meta-audit is a *runtime mutation engine* (D-102) and now reaches 100%.** The kill rate is **computed from real executions**: `tests/meta_audit/engine.py` builds an isolated copy of `backend/app`, `frontend/src`, `migrations/versions`, `docs` in a temp dir (or a fresh temp DB for runtime checks), injects one seeded defect, runs the **real** auditor, semantically matches the finding it actually produced (exact id or a family prefix; an unrelated finding is never a detection), and records ``detected`` / ``missed``. `agent/META_AUDIT_RESULT.json` is a **generated** artifact: it carries `result_source: "computed from runtime mutation executions"`, `generated_at`, `baseline_sha`, per-mutation `{id, detected, expected, actual_findings, severity}`, and derived totals. Arithmetic (`detected + missed == total`, `kill_rate == detected/total*100`, `critical_misses`/`high_misses` from the records) is asserted by `SuiteResult.verify()` in `pytest` and CI ‚Äî no hardcoded `25`/`25`/`100.0` in logic. There are **25** mutations and **8 negative controls** (a clean/correct tree must not produce a mutation finding). Removing a detector flips its mutation to `missed` and lowers the kill rate automatically (proven for F, M, N, O, P and Q); adding a mutation changes `total` automatically (proven by `test_new_mutation_changes_total_without_code_edits`). Current computed result: **25 total, 25 detected, 0 missed, kill rate 100.0%, 0 false positives, 0 critical misses, 0 high misses** (`status: clean`). Five static detectors closed the gaps: `check_write_only_settings` (M), `check_channel_registry_usage` (Q), `check_unused_model_columns` (N ‚Äî an ORM column no module reads/writes, info), `check_orphan_service_classes` (O ‚Äî a public service class no module references, info) and `check_frontend_unwired_controls` (P ‚Äî an `@click`/`@change`/`@submit` handler that is undefined or has an empty body, warning). `KNOWN_GAP_IDS` is now **empty**. CI job `meta-audit` runs the engine, the tests, and a working-tree leak assertion; it does **not** compare against a hardcoded percentage.
**v1.5.4 released** via a reviewed `develop ‚Üí main` PR #15 (merge `b219341`), tag `v1.5.4`; the Release workflow (run `37522394131`) created the GitHub Release and attached the Windows portable ZIP (24 807 288 bytes, sha256 `ff01f787‚Ä¶dc67a`) + `.sha256`. It is a patch over v1.5.3: it closes the last three auditor gaps (N, O, P) with static detectors, so the meta-audit reaches 100%.
**Factual git state:** v2.0.0 is released. `main` HEAD = `926a3b3` (= `origin/main`, tag `v2.0.0`). `develop` HEAD = `926a3b3` (re-synced to `main`). Version strings read **2.0.0** across `backend/app/__init__.py`, `pyproject.toml`, `frontend/package.json` + lock. Latest release: v2.0.0 — PR #23 (merge `926a3b3`), tag `v2.0.0`, Release workflow run `37982855350`, Windows portable ZIP 24 977 686 bytes, sha256 `4d62a52f…bd649`. Previous release: v1.9.0 — PR #22 (merge `997999e`), tag `v1.9.0`, Release workflow run `37775533451`, ZIP 24 929 020 bytes, sha256 `3227988c…d2ac`.
Previous: **v1.5.1 forensic-audit fixes are released** ‚Äî reviewed `develop ‚Üí main` PR #12 (merge `f41ebc8`), tag `v1.5.1`; the Release workflow (run `37453582161`) created the GitHub Release and attached the Windows portable ZIP (24 796 203 bytes, sha256 `b46f9333‚Ä¶68dee`) + `.sha256` (D-060). It fixes five confirmed discrepancies found by an independent audit of v1.5.0 (D-095‚Ä¶D-098): a capability with no implementation can never report `available` (`config_sync`/`media_conversion` ‚Üí `not_implemented`, guarded by a CI check); a consistency check that raises is an `error` finding, never silently skipped; the stored `language` preference is actually consumed (capability graph + a Settings RU/EN selector); source-comparison checks report `audit.source_unavailable` as `info` when the runtime image has no frontend/docs source (so Docker `/api/v1/consistency` is `pass`); and `README.md` version drift. Version strings read **1.5.1**. Suite **731 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean; Docker smoke clean; artifact/secret scan clean.
Previous: **v1.5.0 Capability graph + i18n + Consistency Auditor is released** ‚Äî reviewed `develop ‚Üí main` PR #11 (merge `ad24bc6`), tag `v1.5.0`; the Release workflow (run `37442056281`) created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds (D-092‚Ä¶D-094): It adds three small, additive cross-cutting layers: a machine-readable **capability graph** (`services/capability_graph.py`, `GET /api/v1/capability-graph`, embedded in the Promotion Wizard's `WizardState.capabilities` and shown on the Dashboard as "–ß—Ç–æ —É–∂–µ –¥–æ—Å—Ç—É–ø–Ω–æ"); a bilingual RU/EN **i18n catalog** (`core/i18n.py`) with a stored `language` preference on `/api/v1/help/prefs`; and a **Consistency Auditor** (`services/consistency_checks.py` static + `services/consistency.py` runtime, `GET /api/v1/consistency`, Diagnostics "–ü—Ä–æ–≤–µ—Ä–∫–∞ —Ü–µ–ª–æ—Å—Ç–Ω–æ—Å—Ç–∏" panel) whose static checks run in `pytest` so cross-module drift fails a PR. Version strings read **1.5.0**. Suite **726 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean; Docker smoke clean; artifact/secret scan clean.
Previous: **v1.4.0 Notification Center + Tray Agent + Editorial Workspace is released** ‚Äî reviewed `develop ‚Üí main` PR #10 (merge `306672e`), tag `v1.4.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds the **Notification Center** (D-084‚Ä¶D-086): a durable, queryable history of important events with categories, priorities, per-category routing (owner DM / notification group / Windows toast), quiet hours that postpone only non-urgent messages, anti-spam aggregation, a dashboard and a history API/UI; the **TCMS Tray Agent** (D-087/D-088): a light Windows supervisor that starts the backend hidden, waits for `/health` (never a fixed sleep), restarts a crashed backend with a bounded backoff (5/hour), offers optional Startup-folder autostart (no admin) and writes only a secret-free `data/tray.json` snapshot surfaced in Diagnostics; and the **Editorial Workspace** (D-089‚Ä¶D-091): a linked Telegram forum supergroup where the owner, editors and moderators work the same publication queue as the Web UI (honest, verified bot rights; roles by numeric Telegram id; optimistic-version moves; a full audit trail; publishing reuses the Content Studio posting path). None of these features register accounts or bypass Telegram limits.
Earlier: **v1.3.0 Bot Factory + LAN Mesh is released** ‚Äî PR #9 (`develop ‚Üí main`, merge `7788125`), tag `v1.3.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds the **Bot Factory** (D-077/D-078): plan a set of worker bots, check usernames with Telegram, create each bot through the official owner-confirmed @BotFather flow and adopt it, then bind it through the existing binding rules; and the **optional LAN Mesh / offline control plane** (D-079‚Ä¶D-082): deterministic identity, bounded broadcast discovery + manual peers, one-time-code pairing, deterministic coordinator election, fencing leases, a `mesh.tick` maintenance job and a guard so only the coordinator polls Telegram. Standalone (one computer) stays the default. New API (`/api/v1/bot-factory/*`, `/api/v1/mesh/*`), two RU-first UI pages (`/bot-factory`, `/mesh`) and offline tests. Pre-release hardening (D-083): pairing never persists/returns anything derived from a secret, and `/api/v1/mesh/ping` authenticates the shared secret; help topics `bot_factory` / `lan_mesh` added.
Earlier: **v1.2.0 Content Studio is released** ‚Äî PR #8 (`develop ‚Üí main`, merge `ea6c161`), tag `v1.2.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It adds the v1.2 **content-studio foundation** (D-071‚Ä¶D-076): content sources (Telegram / RSS / Atom / manual) with deduplication, a deterministic explainable cleaner, usage-rights tracking + attribution, Telegram markup validation + a Telegram-like preview, inline button sets, per-source moderation (blocked keywords + quiet hours), multi-channel planning/calendar, publishing through a `PostingProvider` (bot by default; user account only in the expanded mode), durable auto-delete and first comments, and a bounded restart-safe posting tick (`content.posting`). Nothing is published without an explicit owner action; protected content keeps only its link (D-006/D-074); the AI narrows, it never picks emoji (D-033/D-076).
Earlier: **v1.1.0 is released** ‚Äî PR #7 (`develop ‚Üí main`, merge commit `3438305`), tag `v1.1.0`; the Release workflow created the GitHub Release and attached the Windows portable ZIP + `.sha256` (D-060). It carries the multi-format **Account Hub** importer (`.session`, `.session`+JSON, StringSession, optional TDATA; D-070), optional per-account **network routes (proxies)** (D-065), **donor discovery** (candidate proposals only, D-066), a **lightweight local encoder** classifier mode (D-067) with the optional **ruBERT-tiny2** embedding backend + install flow (D-068), and the bot-only/risk UX (D-069). The v1.0.5 **product slice** (D-064): bot‚Üîchannel **bindings** + channel **reaction capabilities**, session-free invite **–ö–∞–º–ø–∞–Ω–∏–∏** + explainable **donor quality**, **backup delivery destinations**, a resumable first-run **Setup Wizard**, and a conservative, off-by-default **auto-update**. `v1.0.0`‚Äì`v1.1.0` stay immutable (D-050).
Version string is **2.0.0** across `backend/app/__init__.py`, `pyproject.toml`, `frontend/package.json` + lock.
All gates pass: `pytest` **1046 collected, full suite green** (real-browser Playwright/Chromium tests included), `ruff` clean, `vue-tsc` + `npm run build` clean, meta-audit **32/32 (0 missed, 0 false positives)**; **GitHub Actions CI** (D-053) enforces the backend, frontend, `browser-tests` (Playwright + Chromium) and `meta-audit` (runtime mutation engine) gates. Shipped in v2.0.0: end-to-end integration tests (`tests/test_content_pipeline_e2e.py`, `tests/test_bot_onboarding_e2e.py`), a Windows hidden-console test (`tests/test_windows_hidden_console.py`) and release-hygiene guards in `tests/test_meta_audit.py` §6.

### v1.8.1 RELEASED (2026-10-08, D-114)

Merged via a reviewed `develop ‚Üí main` PR #20 (merge `bc8382b`), tag `v1.8.1`; the
Release workflow (run `37705225761`) created the GitHub Release and attached the
Windows portable ZIP (24 905 404 bytes, sha256 `0ec6aca1fbd16787d3c0dc4d71e26d8801bcd4c0e20a38f192e317994e2aa9d4`)
+ `.sha256`. `main` HEAD = `bc8382b`; CI on the PR (`37703750591` push / `37703761961`
PR) and `main` (`37705182043`) green across backend, frontend and meta-audit.

Independent verification of the v1.8.0 **AI Gateway + Web Wrapper Hub**; **no new
features**. It proved the gateway *works* by behaviour (routing, retry, failover,
wrapper engine, availability, secret safety), not by reading code, and fixed:

1. **False availability (D-112).** A `web` provider whose `wrapper_id` has no
   matching `WrapperDefinition` was built from the generic fallback and ‚Äî if the
   owner marked it enabled ‚Äî reported `available`/usable. It is now forced
   `unavailable` with `–æ–ø—Ä–µ–¥–µ–ª–µ–Ω–∏–µ –æ–±—ë—Ä—Ç–∫–∏ ¬´‚Ä¶¬ª –Ω–µ –Ω–∞–π–¥–µ–Ω–æ`.
2. **Lost wrapper identity (D-111).** `GenericWebWrapperProvider` always exposed
   `web:<id>`, so a provider pinned under a custom name could not be routed to by
   name. It now keeps the configured name (`web:<id>` is only a fallback).
3. **Decorative retry (D-111).** `AIRouter._attempt` returned a transient
   *response* without retrying; only raised `GatewayError`s were retried. It now
   retries a returned transient response (and a raised error) bounded by the retry
   budget, then fails over.
4. **Lockfile version drift.** `frontend/package-lock.json` read `1.7.0`; synced
   to `1.8.1` and asserted by `test_repo_version_is_consistent`.

New tests: `tests/test_ai_gateway.py` (response/exception transient retries bounded
by `max_attempts`, timeout/region-block/rate-limit failover, text-only provider
never serving an image request, unknown wrapper never `available`, identity
preserved, browser crash classified), `tests/test_ai_gateway_api.py` (e2e web
answer, custom-name routing, unknown wrapper not usable), and three runtime
meta-audit mutations (capability dependency, orphan provider class, unwired
control). Gates: `pytest` **909 passed**, `ruff` clean, `vue-tsc` + `npm run
build` clean, meta-audit **30/30, 100%, 0 false positives**.

### v1.6.1 released (2026-10-07)

Merged via a reviewed `develop ‚Üí main` PR #17 (merge `a38823d`), tag `v1.6.1`;
the Release workflow (run `37601801598`) created the GitHub Release and attached
the Windows portable ZIP (24 846 601 bytes, sha256 `8b6d7c18‚Ä¶f519`) + `.sha256`.
`main` HEAD = `a38823d`; `develop` = `a38823d` (re-synced). CI on `develop`
(run `37598750525`) and the PR (run `37600256647`) both green across backend,
frontend and meta-audit.

### v1.6.1 verification patch (2026-10-07, D-107)

Independent verification of the v1.6.0 Owner Auth + Config Sync slice; **no new
features**. Three fixes:
1. **Owner guard path normalisation (security).** `is_protected` used the raw path
   with `startswith`, so `//api/v1/...` was treated as non-API and skipped the
   guard while the router still matched it. It now collapses redundant slashes,
   resolves dot segments (`posixpath.normpath`) and matches the allowlist by exact
   path or segment boundary. Verified on a real uvicorn server with
   `curl --path-as-is` (`//api/v1/settings` & co. now **401**; allowlist and
   valid-token access unchanged).
2. **`config_sync` capability.** Dropped `minimal=(owner_auth,)`; the states are
   `needs_setup` ‚Üí `available` ‚Üí `error` per D-106. `docs/UI.md` updated.
3. **Google Drive UI wiring.** Added the missing token input + "save token" button
   in `OwnerView.vue`, calling the **existing**
   `POST /api/v1/owner/sync/google/connect` (no new API).
New `tests/test_v16_verification.py` locks these behaviours (middleware-level
leading-`//` 401, capability never `partial`, plus bundle tamper/wrong-key and
no-alternative-endpoint auth checks). Gates: `pytest` 843 passed, `ruff` clean,
`vue-tsc` + `npm run build` clean, meta-audit 25/25.

### v1.6.0 Owner Auth + Config Sync (2026-10-07, D-105/D-106)

**What it is.** A **local owner profile** protects the panel on this computer, and a
**versioned encrypted configuration bundle** moves the owner's settings to a new
computer. Neither is tied to a Telegram account; nothing here registers accounts or
bypasses Telegram limits.

**Owner Auth (D-105).** `core/owner_security.py` derives two independent values from
what the owner types: a slow **PBKDF2-HMAC-SHA256 verifier** (200k iterations,
stored) used only to check a login, and a **config-bundle key** (password + a
non-secret `sync_salt`, never stored). `services/owner_auth_service.py` owns
create/login/logout/lock/unlock/change/delete and rate-limits wrong attempts (5 ‚Üí
15-minute lock). A successful login issues an **HMAC-signed opaque token**
(`api/owner_guard.py`, `X-Owner-Token`). `OwnerGuardMiddleware` is default-on for
every `/api/` path outside a small allowlist, so a new router cannot be added
unguarded; it is **local-first** (open while no profile exists / protection off).

**Config Sync (D-106).** `services/config_bundle.py` builds a **versioned** document
(canonical JSON) and encrypts it with **AES-256-GCM** (schema version authenticated
as associated data). `FORBIDDEN_KEY_MARKERS` + `scan_for_secrets` exclude anything
that looks secret before an export. `services/config_sync_service.py` ties owner
auth + bundle + a `ConfigSyncProvider` together, detects **conflicts** and never
overwrites silently; restore is preview-first. Providers: `config_sync_local.py`
(folder) and `config_sync_gdrive.py` (owner's Drive **app-data scope**, no bundled
OAuth secret).

**Wiring.** `/api/v1/owner/*` + `/api/v1/owner/sync/*`; the `/owner` RU-first UI
page (status, setup, login, change password, sync configure/upload/preview/apply);
`owner_auth` / `config_sync` help topics; capability `config_sync` (now
`implemented`); Diagnostics checks + non-secret payloads; Setup Wizard
`owner_auth_check` / `config_sync_check`; a Promotion Wizard step. Consistency
Auditor section **5b-2** guards the config-sync providers and the bundle's secret
anchors. Migration `20261007_1000_f8b2d3e5a7c9` (`owner_identities`,
`config_sync_state`). Tests `tests/test_owner_auth.py`, `tests/test_config_sync.py`,
`tests/test_owner_api.py`. No secret is ever logged, returned or included in
diagnostics.

### Consistency Auditor gaps M, N, O, P and Q all closed (2026-10-06, D-103)

**Question:** the runtime mutation engine still missed the auditor gaps. All are
now closed by **static** detectors in `services/consistency_checks.py`:

- **M ‚Äî `check_write_only_settings`.** Parses the backend AST and builds the set of
  setting keys **written** (`SettingsService(...)`/alias/`self.settings`/`self.repo`
  ‚Üí `.set(<literal>)`) and **read** (`.get_typed`/`.get_raw`/declared
  `*_SETTING_SPECS`). Any literal write with no reader is a finding
  `settings.write_only.<key>`. Conservative: env-backed (`OPENHANDS_*`/`TCMS_*`)
  keys are skipped, and aliased service locals are resolved.
- **Q ‚Äî `check_channel_registry_usage`.** Flags a service module that is
  channel-aware (a class/function named `*channel*`, or a function taking
  `channel_id`/`registry_channel_id`) but never uses a canonical channel identity
  (no `Channel*` import, no canonical param). Finding
  `channel-aware.module.<module>`. Exempt list avoids self-flagging.
- **N ‚Äî `check_unused_model_columns`.** Derives ORM columns from `mapped_column`
  and flags any column whose name never appears as an attribute, keyword argument
  or string literal outside the model files (so serialisers, `getattr`/`setattr`
  and JSON keys count as use). Finding `db.unused_column.<module>.<Class>.<name>`,
  severity `info`, confidence `medium`. On the real tree it reports 12 genuinely
  dead columns (e.g. `JoinRequest.link_id`, `MediaAsset.width`, `DonorMetrics.
  posts_per_week`) ‚Äî the honest orphan signal.
- **O ‚Äî `check_orphan_service_classes`.** Flags a public service class no module
  references (a plain `import` does not count). Finding
  `dead.service.<module>.<Class>`, severity `info`. On the real tree it reports
  `notification_destinations.RecordingDestination` (a test-support helper).
- **P ‚Äî `check_frontend_unwired_controls`.** Flags a Vue `@click`/`@change`/
  `@submit` handler that names a function the component never defines, or a
  function with an empty body. Inline assignments/expressions are out of scope.
  Finding `frontend.control_unwired.<name>`, severity `warning` (a user-visible
  dead control). On the real tree it is **clean**.

The static detectors run in `run_static_checks()` (so `pytest` and CI fail on
regression) and their mutations are now **detected at runtime** by the engine.
Three new **negative controls** prove precision: `NC6_used_db_column` (added *and*
read ‚Üí not flagged), `NC7_referenced_service` (added *and* instantiated ‚Üí not
flagged) and `NC8_wired_frontend_control` (control *and* handler ‚Üí not flagged);
plus the v1.5.3 `NC4_setting_with_reader` / `NC5_channel_aware_with_registry`. The
runtime `_known_setting_keys()` allow-list is honest.

**Result:** **25 total, 25 detected, 0 missed, kill rate 100.0%, 0 false positives,
0 critical misses, 0 high misses** (`status: clean`). `KNOWN_GAP_IDS` is empty.
See D-103 in `agent/DECISIONS.md`.

### Runtime mutation engine for the Consistency Auditor (2026-10-06, D-102)

**Question:** can the Consistency Auditor actually detect the breakages it is meant
to catch? Answer: **88% of seeded defects, 0 critical/high misses ‚Äî and the number
is computed from real executions, not declared.**

`tests/meta_audit/engine.py` builds an isolated copy of `backend/app`,
`frontend/src`, `migrations/versions` and `docs` in a temp dir (or a fresh temp DB
for runtime checks), points the auditor at the copy, injects one synthetic defect,
runs the **real** auditor, and classifies the result by comparing the findings it
actually produced against the expected finding id/severity. The copy is discarded;
**nothing is written to the working tree** (asserted by a test and by CI).
`agent/META_AUDIT_RESULT.json` is generated by `write_report` and carries
`result_source: "computed from runtime mutation executions"`.

**Dynamism guarantees (all tested):**
- *Detector removal* ‚Äî disabling a detector makes its mutation `missed` and lowers
  the kill rate (`test_removing_a_detector_turns_its_mutation_into_a_miss`, plus
  `test_removing_a_gap_detector_turns_it_into_a_miss` parametrised over M, N, O, P
  and Q).
- *New mutation* ‚Äî adding a mutation changes `total` with no code edits
  (`test_new_mutation_changes_total_without_code_edits`).

**Negative controls:** 8 clean/correct-tree controls must produce **0 false
positives** (asserted). Current run: **25 total, 25 detected, 0 missed, kill rate
100.0%, 0 false positives, 0 critical misses, 0 high misses.**

**Closed earlier (D-099/D-100):** false capability / stray-string mask (strong
`CAPABILITY_SERVICE_ANCHORS`), provider-registry pointing at a missing module,
i18n gaps, hardcoded UI placeholder strings; new `check_router_registration`,
`check_backup_destination_registry`, `check_notification_routing`; capability-key
dependencies enforced in `capability_graph.evaluate()`.

**Real defect found and fixed:** runtime `_check_channel_aware()` queried
`ContentItem.channel_id` (no such column) and swallowed the resulting error ‚Äî the
check had never detected anything. Now uses `ContentSource.channel_id`.

**Remaining gaps (honest, still executed):** none. `KNOWN_GAP_IDS` is now empty;
N, O and P were closed in v1.5.4 (D-103) and are detected at runtime.

### Forensic audit of v1.5.0 (2026-10-06, D-095‚Ä¶D-098)

An independent audit verified the claimed v1.5.0 state against the code and fixed
five confirmed discrepancies (all additive, no new features):

1. **False capability (fixed):** `config_sync` reported **`available` on an empty
   install** while no sync implementation existed; `media_conversion` was listed
   but no ffmpeg/media tooling exists. Both are now `implemented=False` ‚Üí
   `not_implemented` ("–ù–µ —Ä–µ–∞–ª–∏–∑–æ–≤–∞–Ω–æ"), and `check_capability_implementation()`
   fails CI if any capability claims `implemented` without code (D-095).
2. **Silent failure (fixed):** `_runtime_findings` (and `run_static_checks`)
   swallowed check exceptions with `except Exception: continue`; a check that
   never ran looked like a pass. A raising check is now an `error` finding
   `audit.check_failed.<name>` (D-096).
3. **Write-only language preference (fixed):** the stored `language` preference and
   the i18n catalog were never consumed by the UI. `GET /api/v1/capability-graph`
   now honours the saved preference, and Settings has a real RU/EN selector
   (D-097). Scope is honest: the RU-first help catalog stays RU (not
   machine-translated).
4. **Runtime-image false failure (fixed):** the Docker smoke surfaced that the new
   no-silent-failure runner reported `overall: fail` in the runtime image (it
   ships no `frontend/`/`docs/` source). Source-comparison checks now report
   `audit.source_unavailable.<name>` as **info** and are skipped, so the Docker
   report is `pass`; the dev checkout and CI still run every check (D-098).
5. **Doc drift (fixed):** `README.md` still said "Current stable release: `v1.4.0`"
   in two places; updated to `v1.5.0`/`v1.5.1`.

Evidence: `pytest` **731 passed** (was 726; +5 audit tests), `ruff` clean,
`vue-tsc` + `npm run build` clean, capability graph on an empty DB reports
`config_sync`/`media_conversion` as `not_implemented`, the EN preference returns
EN capability labels end-to-end, and the Docker `/api/v1/consistency` report is
`pass` (5 info, 0 error).
**Repository status (historical snapshot, v1.5.4 era):** at that time `main` was the released tag `v1.6.1` and `develop` was the release-facts commit `b8ee5ca`; every GitHub Release carries the Windows portable ZIP + `.sha256` (built by CI, D-060). **This line is history only — the current latest release is v2.0.0 (see the top of this file); `main` HEAD = `926a3b3`, latest tag = `v2.0.0`, and `develop` is re-synced to `main`.**
**Branch:** develop (working branch); main is released and updated only via pull request.
**Latest work (D-104 + D-103 + D-102):** `backend/app/services/consistency_checks.py` gained five static detectors ‚Äî `check_write_only_settings` (gap M), `check_channel_registry_usage` (gap Q), `check_unused_model_columns` (gap N), `check_orphan_service_classes` (gap O) and `check_frontend_unwired_controls` (gap P); `backend/app/services/consistency.py` `_known_setting_keys()` made honest; `tests/meta_audit/engine.py` (sandbox, `run_mutation`, `run_suite`, `SuiteResult` derived totals, `write_report`, `regression_against`, CLI), `tests/meta_audit/mutations.py` (25 mutations + 8 negative controls, `KNOWN_GAP_IDS` = ‚àÖ), `tests/test_consistency_mutations.py` (per-mutation runtime classification + detector-removal + new-mutation + isolation proofs), `tests/test_meta_audit.py` (silent-failure guard, runtime drift, generated-report provenance/arithmetic, closed-gap M/N/O/P/Q regression), `.github/workflows/ci.yml` (`meta-audit` job runs the engine + tests + leak assertion), regenerated `agent/META_AUDIT_RESULT.json` (25 total, 25 detected, 0 missed, 100.0%, 0 critical/high). The declarative `_DETECTABLE`/`_MISSED` lists and the `strict=True` xfail gap tests were removed.
**Previous work (v1.5.1 forensic-audit fixes ‚Äî released):** `services/capability_graph.py` (`implemented` flag + `STATE_NOT_IMPLEMENTED`), `services/consistency_checks.py` (`check_capability_implementation` + `_SOURCE_CHECKS` runtime-image guard + no-silent-failure runner), `services/consistency.py` (no-silent-failure runtime auditor), `api/v1/capability_graph.py` (language from the saved UI preference), `core/i18n.py` (`cap.state.not_implemented`), `services/ui_prefs.py` (`language` preference consumed), `frontend/src/stores/help.ts` + `SettingsView.vue` (RU/EN selector), `DashboardView.vue` (renders the `not_implemented` note). Released via a reviewed `develop ‚Üí main` PR #12 (merge `f41ebc8`), tag `v1.5.1`; Release workflow (run `37453582161`) attached the Windows portable ZIP (24 796 203 bytes, sha256 `b46f9333‚Ä¶68dee`) + `.sha256`. Docker smoke: `/health` ‚Üí `1.5.1`, SPA `200`, `/api/v1/capability-graph` ‚Üí `not_implemented` for `config_sync`/`media_conversion`, `/api/v1/consistency` ‚Üí `pass`; artifact scan clean (no sessions/TDATA/DB/model).

---

## 1. Repository audit result

The repository started as an **empty project**: only a 1-line `README.md` and a
shallow clone of `main`. No code, no dependencies, no prior work existed.

Git: shallow clone ‚Üí history may be incomplete. Run
`git rev-parse --is-shallow-repository` before history-dependent operations.

## 2. What exists now

### Documentation & memory (PHASE 0)
- `docs/` ‚Äî `ARCHITECTURE.md`, `ROADMAP.md`, `SETUP.md`, `SECURITY.md`,
  `UI.md`, `API.md`, `TROUBLESHOOTING.md`.
- `agent/` ‚Äî this file, `NEXT_TASK.md`, `DECISIONS.md` (D-001‚Ä¶D-064),
  `CHANGELOG.md`.
- `.gitignore` (secrets/sessions/data/logs/backups/models protected),
  `.env.example`, `README.md`.
- `.github/workflows/ci.yml` ‚Äî CI on pushes/PRs to `main`/`develop`: backend
  (`ruff` + `pytest`) and frontend (`npm ci` + `npm run build`).

### Backend application (PHASE 1) ‚Äî runnable
Layered architecture: **core ‚Üí db/models ‚Üí db/repositories ‚Üí services ‚Üí api**.

- `backend/app/main.py` ‚Äî FastAPI app factory + lifespan; mounts the built SPA;
  starts/stops the scheduler; `/health` and `/health/deep`.
- `backend/app/core/` ‚Äî `paths.py` (predictable runtime dirs, `TCMS_ROOT`),
  `config.py` (pydantic-settings, `SecretStr`), `logging.py` (structured +
  **secret redaction filter**), `security.py` (secret-key validation, key
  derivation, HMAC signing).
- `backend/app/db/` ‚Äî `base.py` (declarative base + naming convention),
  `session.py` (async engine, `init_models`, `session_scope`),
  `models/` (`setting`, `event`, `job`), `repositories/` (`settings`, `events`,
  `jobs`).
- `backend/app/services/` ‚Äî `settings_service`, `events_service`,
  `queue_service`, `system_service` (Setup Wizard checks, plain-language).
- `backend/app/api/` ‚Äî `errors.py` (uniform error envelope, no stack traces),
  `schemas/` (common/events/settings/jobs/system/bots/reactions), `v1/` routers:
  `system`, `settings`, `events`, `queue`, `bots`, `reactions`, aggregated in
  `v1/router.py`.
- `backend/app/scheduler/` ‚Äî `scheduler.py`: pure-asyncio durable scheduler;
  recovers RUNNING jobs on startup, claims due jobs, runs registered handlers,
  records failures to the Event Center.
- `backend/app/providers/` ‚Äî **PHASE 2**: `base.py` (`TelegramBotProvider`
  Protocol), `types.py` (DTOs), `errors.py` (friendly provider errors),
  `fake_bot.py` (`FakeTelegramBotProvider`, deterministic, no I/O),
  `aiogram_bot.py` (`AiogramBotProvider`, the only aiogram importer; covers the
  official managed-bot methods), `registry.py` (`build_bot_provider`).

### PHASE 2 ‚Äî Telegram foundation (bots)
- `backend/app/db/models/bot.py` ‚Äî `Bot` model (`kind` = manager|managed|ordinary,
  `enabled`, `telegram_id`, `username`, `title`, `token_encrypted` (sealed),
  `provider_name`, `owner_id`/`owner_username`, `can_manage_bots`,
  `health` enum, `health_message`/`health_hint`/`last_error`, `last_health_at`).
- `backend/app/db/repositories/bots.py` ‚Äî CRUD + `get_manager`, `count_by_kind`.
- `backend/app/services/bot_service.py` ‚Äî `BotService`: add (validate+seal),
  enable/disable, remove, `health_check`, `ensure_manager_bot`,
  `register_managed_bot`, `fetch_managed_bot_token`,
  `replace_managed_bot_token`, `manager_link`, `summary`.
- `backend/app/api/deps.py` ‚Äî `get_provider_factory` (overridable in tests),
  `get_bot_service`.
- `backend/app/api/schemas/bots.py`, `backend/app/api/v1/bots.py` ‚Äî full bot
  inventory + managed-bot endpoints (tokens never returned; `has_token` only).
- `backend/app/core/security.py` ‚Äî `seal_secret`/`open_secret` (Fernet, key from
  `APP_SECRET_KEY`).
- `backend/app/api/errors.py` ‚Äî `ApiError` carrying a friendly message + hint.
- `SystemService` ‚Äî DB-backed `manager_bot_db_check`, `managed_bots_check`; wired
  into `/api/v1/system/status`, `/api/v1/system/setup`, `/health/deep`.
- `main.py` lifespan ‚Äî best-effort `ensure_manager_bot()` from settings.

### PHASE 3 ‚Äî Reaction Manager (rules + planner + scheduling + UI)
- `backend/app/rules/engine.py` ‚Äî `RulesEngine`, `Category` (9 categories),
  `RuleSpec`, `RuleMatch`. Deterministic keyword/phrase/regex matching with
  exclusions, `min_confidence`, priority, language gate, `manual_override`.
- `backend/app/rules/delays.py` ‚Äî `DelayPreset` (`early`/`normal`/`spread`),
  `scaled_window`, `distribution_for`, `UniformDelay`.
- `backend/app/rules/defaults.py` ‚Äî `default_rule_specs()` seed RU+EN rules.
- `backend/app/db/models/post.py` ‚Äî `Post` (text, category, confidence,
  classification_source, status, channel/message ids).
- `backend/app/db/models/reaction.py` ‚Äî `ReactionProfile`, `ReactionRule`,
  `ReactionJob` (+ `ReactionJobStatus`): `post_id, bot_id, reaction,
  scheduled_at, status, attempts, error, completed_at, queue_job_id`.
- `backend/app/db/repositories/posts.py`, `repositories/reactions.py`.
- `backend/app/services/reaction_planner.py` ‚Äî pure `ReactionPlanner` + RNG.
- `backend/app/services/reaction_service.py` ‚Äî the vertical-slice service
  (profiles/rules CRUD, classify, simulate, ingest/plan, execute, recover, stats).
- `backend/app/api/schemas/reactions.py`, `api/v1/reactions.py`,
  `api/deps.py::get_reaction_service`, router registration.
- `backend/app/providers/*` ‚Äî `set_reaction` on the provider protocol, fake
  (deterministic recorder + injectable failures) and aiogram implementations.
- `backend/app/scheduler/scheduler.py` ‚Äî handlers receive `(session, job)`
  (fixes a nested-session SQLite deadlock; important on weak machines).
- `backend/app/services/system_service.py` ‚Äî `reactions` Setup-Wizard check.
- `frontend/src/views/ReactionsView.vue` + reaction types/methods in
  `api/client.ts`, `/reactions` route, nav link, Dashboard Reactions card.

### PHASE 4 ‚Äî User Session Manager (MTProto accounts)
- `backend/app/providers/session_base.py` ‚Äî `SessionProvider` protocol
  (send_code, sign_in, sign_in_password, get_me, health, export_session,
  resolve_entity, get_participants, invite_to_channel, aclose).
- `backend/app/providers/telethon_session.py` ‚Äî `TelethonSessionProvider`: the
  **only** Telethon importer; lazy per-operation connect/disconnect; Telethon
  errors translated to friendly provider errors.
- `backend/app/providers/fake_session.py` ‚Äî `FakeSessionProvider` +
  `FakeAuthScenario` (deterministic, no I/O) for tests/offline mode.
- `backend/app/providers/registry.py` ‚Äî `build_session_provider(...)`;
  `providers/errors.py` + `providers/types.py` extended with user-account
  errors/DTOs (`ApiCredentialsInvalidError`, `AuthCode*`, `Password*`,
  `PhoneNumber*`, `SessionInvalidError`; `UserIdentity`, `SendCodeResult`,
  `SignInResult`, `SessionFileInfo`, `EntityRef`).
- `backend/app/db/models/session.py` ‚Äî `UserSession` + `SessionStatus`
  (online/auth_required/disconnected/flood_wait/error/disabled). Full phone and
  api_hash stored **sealed**; only `phone_masked` + `api_id` in plaintext;
  `session_ref` is a UUID basename.
- `backend/app/db/repositories/sessions.py` ‚Äî `SessionRepository`.
- `backend/app/services/session_service.py` ‚Äî `SessionService`: durable guided
  auth wizard (api_id/hash + phone ‚Üí code ‚Üí optional 2FA), `.session` import
  (with rollback on failure), health checks, enable/disable, delete (+ file
  removal), logout/re-auth, `recover()` for interrupted flows.
- `backend/app/api/schemas/sessions.py`, `backend/app/api/v1/sessions.py`,
  `api/deps.py::get_session_service` / `get_session_provider_factory`, router
  registration. Responses never expose secrets (only `phone_masked`, `has_*`).
- `backend/app/services/system_service.py` ‚Äî new Setup-Wizard checks `telethon`,
  `sessions_dir`, `accounts` (plain-language).
- `backend/app/main.py` lifespan ‚Äî best-effort `SessionService.recover()`.
- `frontend/src/views/SessionsView.vue` + session types/methods in
  `api/client.ts`, `/sessions` route, sidebar ¬´–ê–∫–∫–∞—É–Ω—Ç—ã¬ª, Dashboard card.
- `tests/` ‚Äî `test_fake_session_provider.py`, `test_session_service.py`,
  `test_sessions_api.py`, `test_session_security.py`; `conftest.py` gained a
  `session_client` fixture (fake session provider).

### PHASE 5 ‚Äî Audience (sources + parsing + database + export)
- `backend/app/providers/audience_base.py` ‚Äî `AudienceProvider` protocol
  (`resolve_entity`, `iter_participant_pages`).
- `backend/app/providers/session_audience.py` ‚Äî `SessionAudienceProvider`: thin
  adapter over the PHASE 4 `SessionProvider` (no Telethon import here).
- `backend/app/providers/fake_audience.py` ‚Äî `FakeAudienceProvider` +
  `FakeAudienceScenario` (pure, offline); `fake_session.py` gained
  `FakeAudienceScenario` + `make_fake_users` and participant-page support.
- `backend/app/providers/registry.py` ‚Äî `build_audience_provider(...)`; `errors.py`
  + `types.py` gained audience errors/DTOs (`EntityNotFoundError`,
  `PrivacyRestrictedError`, `ChatAdminRequiredError`; `EntityRef` extended with
  `participants_count`/`participants_hidden`, `ParticipantPage`).
- `backend/app/db/models/audience.py` ‚Äî `AudienceSource`, `AudienceUser`,
  `SourceUserLink` (+ enums `SourceType`, `ScanStatus`, `Completeness`,
  `MemberStatus`); dedup via unique `telegram_user_id` and unique
  `(source_id, user_id)` links.
- `backend/app/db/repositories/audience.py` ‚Äî `AudienceSourceRepository`,
  `AudienceUserRepository`, `SourceUserLinkRepository` (filters, pagination,
  sorting, counts, batch streaming, bulk ops; enum-key normalization).
- `backend/app/services/audience_service.py` ‚Äî `AudienceService`: sources CRUD,
  `check_source`, `preview_scan` (dry-run), durable scanning with per-chunk
  commits, completeness logic, pause/resume/cancel, `recover()`, tags, explainable
  scoring, dashboard/statistics, streaming CSV/JSON export, CSV/JSON import.
- `backend/app/api/schemas/audience.py`, `backend/app/api/v1/audience.py`,
  `api/deps.py::get_audience_service`, router registration. Responses never
  expose secrets or raw phones; PII export gated by settings.
- `backend/app/services/system_service.py` ‚Äî new Setup-Wizard `audience` check.
- `backend/app/main.py` lifespan ‚Äî `AudienceService.recover()` (pauses
  interrupted scans) + registered the `audience.scan` durable job handler.
- `backend/app/db/session.py` ‚Äî SQLite `lower`/`upper` registered as Python
  functions so case-insensitive Cyrillic search works (SQLite's built-in `lower`
  is ASCII-only).
- `tests/` ‚Äî `test_audience_models.py`, `test_audience_service.py`,
  `test_audience_api.py`, `test_audience_providers.py`,
  `test_audience_security.py`; `conftest.py` gained an `audience_client` fixture.

### PHASE 6 ‚Äî Invite Manager (queue + confirmation + safe execution)
- `backend/app/db/models/invite.py` ‚Äî `InviteJob` (`target`, `account_ids`/
  `source_ids`/`filters` snapshots, `status`, counters, `confirmed_at`/
  `confirmed_summary`, `waiting_account_id`/`wait_until`, `queue_job_id`) and
  `InviteTask` (`job_id`, `user_id`, `telegram_user_id`, `account_id`, `status`,
  `attempts`, `scheduled_at`, `completed_at`, `wait_until`, `error`); enums
  `InviteJobStatus`, `InviteStatus`, `TERMINAL_INVITE_STATUSES`.
- `backend/app/db/repositories/invites.py` ‚Äî `InviteJobRepository` and
  `InviteTaskRepository` (list/filter, status counts, `claim_batch`, `pending_count`,
  `unfinished_count`, `next_due`, `retry_failed`).
- `backend/app/services/invite_service.py` ‚Äî `InviteService`: `preview` (dry-run
  summary: source/target/users/accounts/filters/planned ops), `create_job` (draft +
  task planning with randomized per-account spacing), `confirm_and_start`,
  `start`/`pause`/`resume`/`stop`, `retry_failed`, `run_tick` (one bounded batch per
  tick ‚Üí `done`/`more`/`paused`), `recover`, `summary`, `explain_job`. FloodWait
  pauses + records the wait; privacy/admin become non-retryable user statuses.
- `backend/app/api/schemas/invites.py`, `backend/app/api/v1/invites.py`,
  `api/deps.py::get_invite_service`, router registration. No secret leaks.
- `providers/errors.py` + `fake_session.py` (`FakeInviteScenario`) +
  `telethon_session.py` ‚Äî invite error coverage.
- `main.py` lifespan ‚Äî `InviteService.recover()` + `invite.batch` durable handler
  (re-schedules itself while work remains).
- `services/system_service.py` ‚Äî Setup-Wizard `invites` check.
- `frontend/src/views/InvitesView.vue` + invite types/methods in `api/client.ts`,
  `/invites` route, sidebar ¬´–ü—Ä–∏–≥–ª–∞—à–µ–Ω–∏—è¬ª.
- `tests/` ‚Äî `test_invite_service.py`, `test_invite_api.py`; `conftest.py` gained an
  `invite_client` fixture.

### PHASE 7 ‚Äî Tiny AI classifier (rules-first, optional)
- `backend/app/ai/` ‚Äî the whole AI layer, free of Telegram/FastAPI imports:
  - `types.py` ‚Äî `Classifier` Protocol, `ClassificationResult`
    (`category`/`tone`/`confidence`/`source`), `ClassificationContext`, `Tone`,
    and the source/mode vocabularies (`rules`/`llm`/`manual`/`fallback`/`default`;
    `auto`/`rules`/`ai`).
  - `errors.py` ‚Äî friendly, non-leaking errors (`AiDisabledError`,
    `ModelNotConfigured/NotFoundError`, `RuntimeUnavailableError`,
    `InferenceTimeoutError`, `InvalidModelOutputError`, `ModelLoadError`).
  - `schema.py` ‚Äî `parse_classification`: tolerant about framing, strict about
    values (unknown category/tone, non-numeric/bool/out-of-range confidence ‚Üí
    `InvalidModelOutputError`).
  - `classifiers.py` ‚Äî `RulesClassifier` (wraps the Rules Engine),
    `LlmClassifier` (prompt + `run_bounded` + strict parse), `FakeClassifier`.
  - `router.py` ‚Äî `RoutingClassifier` (rules fast path ‚Üí AI only when unsure ‚Üí
    graceful fallback), explainable `RoutingOutcome`, `category_title`.
  - `inference.py` ‚Äî `run_bounded`: one shared single-worker executor; timeout
    raises `InferenceTimeoutError`; `shutdown_executor()` on app exit.
  - `backends/` ‚Äî `base.LlmBackend`, `FakeLlmBackend` (data-block-only keyword
    heuristic; scriptable failures), `LlamaCppBackend` (the only `llama_cpp`
    importer; lazy load, lock-serialized, optional), registry `build_backend`.
- `backend/app/db/models/ai.py` (`AiMetric` single-row counters, `AiRecord` recent
  diagnostics) + `repositories/ai.py` (`AiRepository`).
- `backend/app/services/ai_service.py` ‚Äî `AiService`: effective (DB-overridable)
  config, `status`, `list_models`/`check_model`/`load_model`/`unload_model`,
  `router(mode)`, `classify`, metrics/history, event recording, `_backend()`
  cache. `ai_help.py` ‚Äî per-setting plain-language help + `human_size`.
- `backend/app/api/schemas/ai.py` + `api/v1/ai.py` ‚Äî 11 routes: `/ai/status`,
  `/ai/overview`, `/ai/settings` (GET/PUT), `/ai/classify`, `/ai/test`,
  `/ai/models`, `/ai/model/check|load|unload`, `/ai/metrics`, `/ai/history`;
  registered in `v1/router.py`.
- `Settings` ‚Äî AI block + `resolve_models_dir()`; `paths.models_dir()`
  (`MODELS_DIRNAME`). Model files live in gitignored `/models/`, never
  auto-downloaded.
- `ReactionService` ‚Äî `_classify` routes through `RoutingClassifier`
  (`_route`/`_result_to_match`/`_public_source`); `simulate` and `ingest_post`
  accept `mode`/`force_category`; simulation response carries the AI fields.
- `services/system_service.py` ‚Äî `ai_check_async` (live service) wired into the
  Setup Wizard's `ai` check (off = OK, missing runtime/model = warning, never an
  error).
- `frontend/src/views/AiView.vue` ‚Äî tabs –û–±–∑–æ—Ä / –ú–æ–¥–µ–ª—å / –ù–∞—Å—Ç—Ä–æ–π–∫–∏ / –ü—Ä–æ–≤–µ—Ä–∫–∞ /
  –î–∏–∞–≥–Ω–æ—Å—Ç–∏–∫–∞; AI types + methods in `api/client.ts`; `/ai` route; sidebar ¬´–ú–∏–Ω–∏-–ò–ò¬ª.
- `tests/` ‚Äî `test_ai_classifier.py` (schema/classifiers/routing/inference) and
  `test_ai_api.py` (service + API + reaction simulation AI fields + setup check).

### PHASE 8 ‚Äî Analytics (content, reactions, audience + Dashboard insight)
- `backend/app/db/repositories/analytics.py` ‚Äî `AnalyticsRepository`: read-only
  aggregates over posts, reaction jobs, audience sources/users/links and invite
  tasks. Per-day series are bucketed in Python (`_buckets`/`_day_key`) for
  portability; helpers `_rows`/`_scalar`/`_scalars`/`_value`. Every query takes an
  optional `channel_id` (D-055) and scopes via `_scoped_posts`/`_scoped_reactions`/
  `_scoped_audience_users`/`_channel_source_ids`.
- `backend/app/services/analytics_service.py` ‚Äî `AnalyticsService`:
  `content()`/`reactions()`/`audience()`/`overview()` (all accept `channel_id`),
  RU plain-language summaries, percent-change vs. the previous window, titled
  counts (`_CATEGORY_TITLES`/`_SOURCE_TITLES`/`_AUDIENCE_STATUS_TITLES`),
  `_clamp_days`.
- `backend/app/api/schemas/analytics.py` + `api/v1/analytics.py` ‚Äî
  `GET /api/v1/analytics/overview|content|reactions|audience?days=1..365&channel_id=`;
  registered in `v1/router.py`; `api/deps.py::get_analytics_service`.
  `AnalyticsOverviewOut` echoes `channel_id`.
- `frontend/src/views/AnalyticsView.vue` ‚Äî channel + period switches, headline
  metrics, sparklines, category/emoji bars, audience status, source effectiveness
  table; `/analytics` route + sidebar ¬´–ê–Ω–∞–ª–∏—Ç–∏–∫–∞¬ª.
- `frontend/src/components/Sparkline.vue` + `BarList.vue` ‚Äî dependency-free
  inline-SVG/CSS charts (D-037).
- `frontend/src/views/DashboardView.vue` ‚Äî new "–ß—Ç–æ –ø–æ–∫–∞–∑—ã–≤–∞—é—Ç —Ü–∏—Ñ—Ä—ã" block
  (backend summary + two sparklines) linking to `/analytics`.
- Analytics types + client methods in `frontend/src/api/client.ts`; analytics
  styles appended to `frontend/src/styles.css`.
- `tests/` ‚Äî `test_analytics_service.py`, `test_analytics_api.py` (13 tests).

### PHASE 9 ‚Äî Telegram Mini App (same SPA, one API)
- `backend/app/miniapp/auth.py` ‚Äî `verify_init_data()`: HMAC-SHA256
  (`HMAC_SHA256(bot_token, "WebAppData")`) over sorted pairs, constant-time
  compare, `auth_date` freshness, user parse. `MiniAppAuthError`, `MiniAppUser`.
- `backend/app/miniapp/sessions.py` ‚Äî `issue_session`/`verify_session`: HMAC
  tokens keyed by `derive_key("miniapp-session")`; `MiniAppSessionError`.
- `backend/app/miniapp/service.py` ‚Äî `MiniAppService`: sealed manager-token read,
  owner allow-list (`settings.admin_ids`), DB-overridable `miniapp_enabled` /
  `miniapp_public_url`, plain-language `MiniAppStatus`, and `setup()` ‚Äî the
  one-click registration helper (D-054) that points the manager bot's Web App
  menu button at a public HTTPS URL.
- `backend/app/api/schemas/miniapp.py` + `api/v1/miniapp.py` ‚Äî
  `GET /config`, `POST /setup` (register menu button), `POST /auth` (sets
  `HttpOnly` `tcms_miniapp` cookie), `GET /me`, `POST /logout`; registered in
  `v1/router.py`; `api/deps.py::get_miniapp_service`.
- `backend/app/providers/base.py` ‚Äî `TelegramBotProvider.set_menu_button`;
  implemented by `aiogram_bot.py` (`set_chat_menu_button`) and `fake_bot.py`.
- `backend/app/services/system_service.py` ‚Äî `miniapp_check` added to the Setup
  Wizard checks.
- `backend/app/core/config.py` + `.env.example` ‚Äî `miniapp_enabled` (off by
  default), `miniapp_initdata_max_age`, `miniapp_session_ttl`,
  `miniapp_public_url`.
- `frontend/src/telegram.ts` ‚Äî typed Telegram WebApp SDK wrapper;
  `frontend/src/stores/miniapp.ts` ‚Äî Pinia bootstrap store (inert in a browser).
- `frontend/src/App.vue` ‚Äî Telegram gate + mobile bottom nav + user line;
  `index.html` loads the WebApp SDK and uses `viewport-fit=cover`;
  Mini App types/methods in `api/client.ts`; responsive + dark styles in
  `styles.css`.
- `tests/` ‚Äî `test_miniapp_auth.py`, `test_miniapp_api.py` (19 tests).

### PHASE 10 ‚Äî Portable packaging + backup/restore
- `backend/app/services/backup_service.py` ‚Äî `BackupService`: `.tcmsbak` zip
  (DB + `manifest.json`), unique filenames, retention prune, safety backup on
  restore, config export/import (`settings`/`reaction_profiles`/`reaction_rules`
  only), path-traversal guard, sessions excluded by default.
- `backend/app/api/schemas/backup.py` + `api/v1/backup.py` ‚Äî `/backup`
  info/list/create/download/restore/delete + `/backup/config/{export,import}`;
  `api/deps.py::get_backup_service`; registered in `v1/router.py`.
- `backend/app/core/config.py` + `.env.example` ‚Äî `backup_dir`,
  `backup_retention`, `backup_include_sessions`.
- `backend/app/core/paths.py` ‚Äî `static_dir()` now package-relative.
- `frontend/src/views/BackupView.vue` (–Ý–µ–∑–µ—Ä–≤–Ω—ã–µ –∫–æ–ø–∏–∏) + route + nav + client
  types/methods.
- `portable/run.bat` (sets `TCMS_ROOT`/`PYTHONPATH`, opens browser),
  `portable/stop.bat`, `portable/README.txt`.
- **Release-engineering packaging (D-056/D-057):** `scripts/build_portable.sh`
  is now cross-platform and emits a versioned ZIP (+ `.sha256`);
  `scripts/build_win_runtime.py` stages the embedded Windows CPython + pinned
  `win_amd64` wheels from `scripts/win-requirements.lock` (extracted flat, no
  compiler ‚Äî `pyaes` comes from its pure-Python sdist);
  `scripts/fetch_embedded_python.sh` retained (now with `--no-deps`).
  `.github/workflows/release.yml` builds and attaches the ZIP to the GitHub
  Release on a `v*` tag.
- `tests/` ‚Äî `test_backup_service.py` (9), `test_backup_api.py` (7),
  `test_portable_smoke.py` (1 startup smoke + offline-tree/ZIP-layout + builder
  dry-runs).

### PHASE 11 ‚Äî VPS / Docker production config
- `docker/Dockerfile` ‚Äî multi-stage (Node SPA build ‚Üí `python:3.12-slim`,
  non-root uid 10001). Built and smoke-tested locally.
- `docker/docker-compose.yml` ‚Äî one `app` service; optional `.env`; bind-mounted
  `data/ sessions/ backups/ logs/ exports/`; `/health` healthcheck;
  `restart: unless-stopped`; publishes `127.0.0.1:8000` only.
- `docker/docker-compose.proxy.yml` + `docker/Caddyfile` ‚Äî optional TLS overlay
  (Caddy, automatic Let's Encrypt) fronting `app:8000`.
- Docs: `docs/SETUP.md` (mode C full walkthrough + nginx alt), `docs/SECURITY.md`
  (VPS specifics), `docs/TROUBLESHOOTING.md` (container issues),
  `docs/ARCHITECTURE.md` (¬ß11 Docker/VPS).

### Frontend (PHASE 1) ‚Äî Vue 3 + Vite + TypeScript
- `frontend/` ‚Äî `package.json`, `vite.config.ts` (builds into
  `backend/app/static/`), `tsconfig.json`, `index.html`.
- `src/` ‚Äî `main.ts`, `App.vue` (sidebar shell), `router.ts`,
  `api/client.ts` (typed client, uniform error handling), `stores/app.ts`
  (Pinia), `styles.css` (modern desktop look, responsive), views:
  `DashboardView`, `SystemView` (Setup Wizard table), `SettingsView`,
  `LogsView`, `QueueView`, `NotFoundView`.
- **PHASE 2**: `src/views/BotsView.vue` (inventory, health, enable/disable,
  add, managed-bot workflow), bot types + methods in `api/client.ts`, `/bots`
  route, nav link, and a Telegram summary card on the Dashboard.
- **Post-roadmap polish**: `src/views/SourcesView.vue` (source list, add, check,
  scan confirmation + progress, pause/resume/cancel) and
  `src/views/AudienceView.vue` (paginated user table, search/filters/presets,
  tags, bulk actions, detail, export/import); `/sources` and `/audience` routes,
  sidebar + Mini App nav entries, and audience types/methods in `api/client.ts`.

### Ops / packaging (PHASE 1 foundation)
- `backend/requirements.txt`, `backend/requirements-dev.txt`.
- `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- `portable/run.bat`, `portable/stop.bat`, `portable/README.txt` ‚Äî completed in
  PHASE 10 (see the PHASE 10 section above).
- `docker/Dockerfile` (multi-stage: Node build ‚Üí Python runtime, non-root),
  `docker/docker-compose.yml`, root `.dockerignore`.
- `pyproject.toml` (ruff config), `pytest.ini`.
- `tests/` ‚Äî config, logging redaction, db/queue/events, API, scheduler.
- **PHASE 2 tests**: `tests/test_providers.py`, `tests/test_bot_service.py`,
  `tests/test_bots_api.py`; `tests/conftest.py` gained a `bot_client` fixture
  that overrides `get_provider_factory` with the fake provider.

## 3. What works (verified)

- App starts and serves `/health`, `/health/deep`, `/api/v1/*`, and the SPA.
- Setup Wizard checks return plain-language status for: runtime, database,
  filesystem, secret key, Telegram API, manager bot, managed bots, AI.
- Settings CRUD, events (log/error center) list + resolve, queue list +
  retry/cancel.
- Durable queue recovers jobs after restart; scheduler executes handlers.
- **Bots**: add (validated + sealed), list/summary, enable/disable, remove,
  health check, managed-bot preview/register/fetch-token ‚Äî verified live in
  offline mode (server + curl) and covered by tests.
- **Reactions (PHASE 3)**: profiles/rules CRUD, deterministic classification,
  weighted/randomized planning, simulation (no Telegram), ingest+plan creating
  durable jobs, execution via the provider with FloodWait handling, and startup
  recovery ‚Äî verified live in offline mode (add bot ‚Üí enable ‚Üí ingest ‚Üí job
  created) and covered by 48 tests.
- `ruff check backend tests` ‚Üí clean. `pytest` ‚Üí **413 passed** (after the hardening tests).
- Frontend `npm run build` ‚Üí outputs to `backend/app/static/` successfully
  (`vue-tsc` clean).
- **Sessions (PHASE 4)**: guided auth wizard (start ‚Üí code ‚Üí 2FA), `.session`
  import (+ rollback), health, enable/disable, delete, logout, startup recovery ‚Äî
  verified live in offline mode (start ‚Üí code ‚Üí list; no secret in responses) and
  covered by 45 tests.
- **Audience (PHASE 5)**: sources CRUD, `check`, dry-run preview, chunked durable
  scan (pause/resume/cancel, restart recovery), dedup, filters/search/sort/tags,
  bulk status, dashboard/statistics, streaming export, import ‚Äî verified in
  offline mode and covered by API/service/model/provider/security tests. No
  secret or raw phone appears in responses, exports default to no PII.
- **Invites (PHASE 6)**: dry-run preview, draft‚Üíconfirm‚Üístart, bounded durable
  execution (one batch per tick, re-scheduled), per-account/per-user statuses,
  pause/resume/stop, safe retry, FloodWait pause + recorded wait, privacy/admin
  statuses, and restart recovery (`recover()` pauses running jobs) ‚Äî covered by
  `test_invite_service.py` + `test_invite_api.py`; responses never leak secrets.
- **Tiny AI (PHASE 7)**: rules-first routing (AI only when rules are unsure),
  strict-JSON classification, optional GGUF backend that degrades gracefully when
  llama.cpp/the model is absent, model check/load/unload, DB-overridable UI
  settings, metrics/history, and an `ai` Setup-Wizard check ‚Äî verified live in
  offline mode (status ‚Üí enable fake ‚Üí classify via rules and via AI) and covered
  by 43 AI tests. The SPA builds with the new ¬´–ú–∏–Ω–∏-–ò–ò¬ª page.
- **Analytics (PHASE 8)**: read-only `/api/v1/analytics/*` aggregates over posts,
  reactions, audience and invites, with RU plain-language summaries and
  percent-change; the ¬´–ê–Ω–∞–ª–∏—Ç–∏–∫–∞¬ª page (charts, bars, tables) and a Dashboard
  "–ß—Ç–æ –ø–æ–∫–∞–∑—ã–≤–∞—é—Ç —Ü–∏—Ñ—Ä—ã" block render them. Verified in offline mode (server +
  curl ‚Üí `/analytics/overview`, SPA `/analytics` ‚Üí 200) and covered by 13 tests.
  Responses contain only aggregate counts (no secrets/PII).
- **Mini App (PHASE 9)**: the same SPA detects Telegram WebApp `initData`,
  authenticates via `/api/v1/miniapp/auth` (server-side HMAC verification),
  and shows a mobile bottom-nav layout inside Telegram while the desktop Web UI
  is unchanged. Verified in offline mode (`/miniapp/config` ‚Üí 200 with a
  plain-language unavailable reason, `/miniapp/me` ‚Üí `authenticated:false`, SPA
  `/` ‚Üí 200) and covered by 19 tests. No token/`initData` leak in responses.

## 4. What does NOT exist yet

- **Worker Mesh remote dispatch/execution ‚Äî PARTIAL (verified 2026-10-05).** The
  LAN Mesh ships the *worker primitives* (the `WORKER` role, capability
  advertisement/matching, fencing-token leases that a worker can acquire/complete,
  `reclaim_expired`, coordinator election, and the coordinator-only poller guard
  in `main.py`), but there is **no remote job-dispatch + worker-execution loop**:
  `MeshTransport` is used only for the `/api/v1/mesh/ping` liveness probe, and
  leases are acquired/completed locally through `/api/v1/mesh/leases/*`, not pulled
  from a coordinator and executed on a peer. **VPS Worker mode** (`MeshMode.VPS_WORKER`)
  is a declared enum/config value only ‚Äî there is no PostgreSQL control plane
  (SQLite-now/Postgres-later, D-002). So the LAN Mesh is a real *coordination layer*
  for the owner's own computers, not a distributed job mesh.
- Mini App: BotFather Web App **menu-button** registration is automated
  (`POST /api/v1/miniapp/setup`, D-054); providing a public HTTPS URL remains the
  owner's deployment step. The Mini App is off by default.
- Reactions/audience store their own channel text in places; invites, posts,
  audience sources, the permission probe and analytics consume the registry.
- ~~Channel binding registry/UI~~ ‚Äî **done** (hardening, see ¬ß2b).
- ~~Alembic migrations~~ ‚Äî **done** (hardening, see ¬ß2b).
- ~~Account permission probe~~ ‚Äî **done** (post-1.0 hardening, see ¬ß2a).
- ~~Manager-bot runtime / command loop / notifications~~ ‚Äî **done** (post-1.0
  hardening, see ¬ß2a).
- ~~Owner-facing diagnostics / redacted support report~~ ‚Äî **done** (v1.0.3,
  see ¬ß2d).

## 2a. Post-1.0 hardening (2026-10-03) ‚Äî complete in code

**Account permission probe.**
- `backend/app/providers/session_base.py` ‚Äî `SessionProvider` gained
  `probe_permissions(...)`; `providers/types.py` gained `PermissionReport`;
  implemented in `telethon_session.py` and the fake (`FakePermissionScenario`).
- `backend/app/db/models/permission.py` (`PermissionCheck`) +
  `db/repositories/permissions.py`.
- `backend/app/services/permission_service.py` ‚Äî `MODULE="permissions"`; maps
  provider errors to `ok|partial|no_access|auth_required|admin_required|
  privacy_restricted|flood_wait|error`; stores each check; `latest()`/`history()`.
- `backend/app/api/schemas/permissions.py`, `api/v1/permissions.py`,
  `api/deps.py::get_permission_service`, router registered in `v1/router.py`.
- Frontend: permission-probe panel in `SessionsView.vue`.

**Manager-bot runtime + notifications.**
- `backend/app/manager/bus.py` ‚Äî bounded, non-blocking `NotificationBus`; six
  categories (`system|telegram|reactions|audience|invites|ai`); `MODULE_TO_CATEGORY`,
  `category_for_module`, `publish`, `reset_notification_bus`.
- `backend/app/manager/service.py` ‚Äî `ManagerBotService`: admin whitelist
  (`MANAGER_BOT_ADMIN_IDS`), RU commands, provider construction,
  `deliver_pending`, `notification_settings`/`update_notification_settings`
  (stored in the existing `settings` table).
- `backend/app/manager/runtime.py` ‚Äî `ManagerBotRuntime` (one asyncio task, short
  polling, exponential backoff, graceful stop).
- `backend/app/api/schemas/manager.py`, `api/v1/manager.py` (`/manager/status`,
  `/manager/notifications`), `api/deps.py` deps, router registered.
- `backend/app/main.py` ‚Äî starts/stops the runtime in lifespan (gated by
  `MANAGER_RUNTIME_ENABLED`); publishes start/stop notifications.
- Provider extensions: `TelegramBotProvider.get_managed_bots`, update/command
  support (aiogram + fake). Notifications wired into `events_service`,
  `ai_service`, `backup_service`.
- Frontend: notification toggles in `SettingsView.vue`; manager card in
  `SystemView.vue`; types/methods in `api/client.ts`.
- Config: `manager_runtime_enabled`, `manager_runtime_poll_interval`.
- Tests: `tests/test_manager_bot.py` (26), `tests/test_permission_service.py` (13),
  `tests/test_hardening_api.py` (9); `conftest.py` gained `permission_client` /
  `manager_client` fixtures and sets `MANAGER_RUNTIME_ENABLED=false`.

Decisions: D-047, D-048, D-049.

## 2b. Hardening (2026-10-03) ‚Äî versioned migrations + Channel Registry

**Versioned Alembic migrations (replace `create_all` at startup).**
- `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, and a baseline
  revision under `migrations/versions/` autogenerated from the models (revision id
  changes whenever the baseline is regenerated).
- `backend/app/db/migrate.py` ‚Äî guarded runner: fresh install / existing
  `create_all` DB (adopt + stamp) / normal upgrade, pre-migration backup,
  transaction-per-migration, DB state constants.
- `backend/app/core/paths.py` ‚Äî `project_root()`, `code_root()`, `alembic_ini()`
  (migration dir resolved relative to code, not the mutable data root).
- `backend/app/main.py` ‚Äî startup applies migrations (no `create_all`).
- `backend/app/services/system_service.py` ‚Äî DB check is migration-aware;
  `api/schemas/system.py` + `api/v1/system.py` expose migration status/upgrade.
- `docker/Dockerfile` ships `alembic.ini` + `migrations/`; `scripts/build_portable.sh`
  copies them into the portable bundle.
- Docs: `docs/database-migrations.md`. Tests: `tests/test_migrations.py`.

**Channel Registry (one shared channel identity).**
- `backend/app/db/models/channel.py` (`Channel`, `ChannelKind`, `ChannelStatus`) ‚Äî
  reference/telegram_id/username/title/kind/status/is_default/modules(JSON)/
  verification fields/participants_count/note; registered in models `__init__`.
- `backend/app/db/repositories/channels.py`, `services/channel_service.py`
  (`normalize_reference`, add/verify/set_modules/set_default/delete/list/summary),
  `api/schemas/channels.py`, `api/v1/channels.py`, `api/deps.py::get_channel_service`,
  router registered. Verification reuses `PermissionService` (never bypasses limits).
- Invite integration: `invite_jobs.channel_id` added; invite create/preview resolve
  the target from the chosen registry channel (fallback to a typed target).
- Post ingestion + audience sources: `posts.registry_channel_id` and
  `audience_sources.channel_id` link to the registry; the API resolves the
  channel's reference/username from a chosen registry id (friendly 404 if
  unknown). Migration `e3b5890e407e`.
- Permission probe: `permission_checks.registry_channel_id` links a probe to the
  chosen registry channel; `POST /api/v1/permissions/check` accepts `channel_id`
  and `ChannelService.verify` links its probe. Migration `6816b29afc76`.
- Frontend: RU-first "–ö–∞–Ω–∞–ª—ã" page (`ChannelsView.vue`, nav + route), channel
  types/methods in `api/client.ts`; invite form, audience source form, reactions
  simulation/ingest panel and the Sessions permission panel each gained a channel
  picker.
- Tests: `tests/test_channels.py` (21) + `tests/test_permission_service.py` + `conftest.py::channel_client`.

Decisions: D-051, D-052.

**Migration adoption fix (high severity).** A v1.0.0 install (built with
`create_all`, no `channels` table) was stamped at Alembic *head* without running
the registry migration, so the app crashed on the missing `channels` table.
`migrate.py` is now **baseline-aware**: it stamps such a database at the baseline
revision and upgrades through the deltas, and `database_status` reports a pending
upgrade. Migration history: `0191baf5265f` (baseline = v1.0.0 schema) ‚Üí
`561f0631d045` (channel registry) ‚Üí `e3b5890e407e` (registry links for sources
and posts) ‚Üí `6816b29afc76` (registry link for permission checks). Regression
test upgrades a v1.0.0-shaped database with existing rows. Decisions: D-052.

## 2c. Release engineering (2026-10-04) ‚Äî reproducible, installable packaging

**Version is `1.0.2`** across `backend/app/__init__.py`,
`pyproject.toml`, `frontend/package.json` and `frontend/package-lock.json`
(was `1.0.1`; D-057, D-060).

**Cross-platform, reproducible Windows portable runtime.**
- `scripts/build_win_runtime.py` ‚Äî downloads the official Windows **embeddable**
  CPython (`python-3.12.7-embed-amd64.zip`) and the pinned `win_amd64` wheels,
  extracts them flat into `runtime/site-packages`, and writes `python312._pth`
  (`python312.zip`, `.`, `../app`, `site-packages`, `import site`). No compiler:
  `pyaes` (Telethon dep, sdist-only) is extracted from its pure-Python sdist.
- `scripts/win-requirements.lock` ‚Äî pinned Windows runtime set (uvicorn base, not
  `[standard]`; see D-056).
- `scripts/build_portable.sh` ‚Äî cross-platform; builds the SPA, stages the app +
  runtime, and writes a versioned ZIP
  (`Telegram-Channel-Management-Suite-Windows-Portable-<version>.zip`) plus
  `.sha256`. New flags `--no-runtime`, `--no-zip`, `--no-frontend`.
- `scripts/fetch_embedded_python.sh` ‚Äî retained (host-driven path), gained
  `--no-deps`.

**CI/release automation.**
- `.github/workflows/release.yml` ‚Äî on a `v*` tag (or manual dispatch): verify
  (ruff + pytest + SPA build), build the portable ZIP, upload it as an artifact
  and attach it (+ checksum) to the GitHub Release.
- `.github/workflows/ci.yml` (D-053) unchanged.

**Dependencies.** `backend/requirements.txt` now uses base `uvicorn` instead of
`uvicorn[standard]` (the app uses no WebSockets and the default asyncio loop;
this removes uvloop/httptools/watchfiles/websockets and keeps the portable
runtime small and cross-buildable). `--reload` now needs `watchfiles`
(documented).

**Verification (this pass).** `pytest` **427 passed**; `ruff` clean; `vue-tsc` +
`npm run build` clean; `docker build` succeeded and the container served
`/health` + the SPA; the staged portable tree started end-to-end from a path with
spaces and Cyrillic, applied migrations, created a backup, restored it, and shut
down gracefully via `/api/v1/system/shutdown`. Decisions: D-056, D-057.

## 2d. Product polish (v1.0.3, 2026-10-04) ‚Äî Diagnostics + redacted report

**Version is `1.0.3`** across `backend/app/__init__.py`, `pyproject.toml`,
`frontend/package.json` + `package-lock.json`.

**Backend.**
- `backend/app/core/redaction.py` ‚Äî reusable redaction: masks bot tokens
  (`\d{6,}:[A-Za-z0-9_-]{30,}`), `api_hash`/`api_id` key-value pairs, Telethon
  session strings, E.164 phones, registered secrets, and long hex/base64 blobs.
  `redact_text`, `redact_mapping` (drops forbidden keys), `scan` (finds leaks) and
  `redact_and_verify` (redact + re-scan safety gate).
- `backend/app/services/diagnostics_service.py` ‚Äî `DiagnosticsService`: aggregates
  14 subsystem checks (application, database via `migrate.database_status`,
  telegram_api, manager_bot, managed_bots, sessions, channels, audience, reactions,
  invites, ai, scheduler, storage, portable_runtime) into `DiagnosticsReport`; the
  report payload (`build_report_payload`) plus `build_report(fmt)` for
  json/txt/zip; and the safe actions `restart_scheduler`, `recheck_telegram`,
  `recheck_channels`, `cleanup_jobs`.
- `backend/app/scheduler/handlers.py` ‚Äî `register_handlers(scheduler)` (the
  durable-queue handlers moved out of `main.py`) so a UI scheduler restart rewires
  identically.
- `backend/app/api/v1/diagnostics.py` + `api/schemas/diagnostics.py` +
  `api/deps.py::get_diagnostics_service` ‚Äî endpoints under `/api/v1/diagnostics`.
- `backend/app/db/repositories/jobs.py` ‚Äî added read/safe-mutation helpers:
  `list_stuck_running`, `list_overdue`, `cancel_many`, `status_counts`,
  `kind_counts`, `failed_since`, `oldest_pending_at`.
- **Frontend** ‚Äî `frontend/src/views/DiagnosticsView.vue` (`/diagnostics`, sidebar
  ¬´–î–∏–∞–≥–Ω–æ—Å—Ç–∏–∫–∞¬ª), diagnostics types + methods in `api/client.ts`.

**Report safety.** The report is redacted then re-scanned; if `clean` is false no
file is produced (`DiagnosticsError` ‚Üí HTTP 500 with a friendly message). It
contains no tokens, keys, session data, phones, passwords, DB contents, audience
records or private logs. Header `X-Diagnostics-Redacted: true`.

**Tests.** `tests/test_diagnostics.py` ‚Äî redaction of every secret kind, mapping
key-dropping, the safety scan, report generation (json/txt/zip), absence of
secrets/DB contents, status aggregation, the API, non-destructive cleanup, and
graceful degradation (a failing check or report section yields a friendly row /
safe empty section instead of HTTP 500). Full suite: **462 passed**, `ruff`
clean, `vue-tsc` + `npm run build` clean.

**UI wording.** Audience page title ‚Üí ¬´–ê—É–¥–∏—Ç–æ—Ä–∏—è¬ª; invites task list ‚Üí ¬´–ó–∞–¥–∞–Ω–∏—è¬ª;
Queue page ‚Üí Russian labels for job kinds/statuses (one term per entity;
`docs/UI.md` ¬ß11). Decisions: D-061.

## 2e. v1.0.4 ‚Äî startup robustness + beginner polish (2026-10-04, released)

Patch release (merge `3f42c3d`, PR #5, tag `v1.0.4`). No new phases/features.

- **Corrupt database is explained, not fatal.** A damaged `data/app.db` used to
  make the Diagnostics page return HTTP 500 (the exact case it exists to explain)
  and could abort scheduler recovery during startup. Now every DB-backed check in
  `DiagnosticsService.collect` is guarded (`_guarded`) and degrades to a friendly
  `error` row; the report's DB-backed sections fall back to safe empty values
  (`_safe`); `SystemService.database_check` reports a damaged file distinctly
  (via `_schema_readable`) with a concrete recovery step; and
  `Scheduler.start()` guards `_recover()`. The app now starts and explains.
- **Queue page labels** ‚Äî `frontend/src/views/QueueView.vue` maps raw job kinds
  (`reaction.job`, `audience.scan`, `invite.batch`) and statuses to plain Russian.
- **Beginner polish** (from the prior maintenance session): a startup readiness
  wait (`core/startup.py`), in-UI help hints (`InfoHint`, `services/help_topics.py`,
  `/api/v1/help`), and a novice-mode setting.
- `docs/TROUBLESHOOTING.md` gained a damaged-database entry; `docs/ROADMAP.md`
  corrected stale Alembic/PHASE-2 claims; `docs/RELEASE_CHECKLIST.md` records the
  v1.0.3 results and a v1.0.4 section.
- Tests added: `tests/test_diagnostics.py` (degradation), `tests/test_scheduler.py`
  (recovery-failure resilience), `tests/test_startup_readiness.py`,
  `tests/test_help.py`.
- Verified: Docker image builds and runs (health, SPA, migrations, persistent
  volumes, graceful + SIGKILL restart all OK); `scripts/build_portable.sh`
  produced a clean v1.0.4 ZIP (no `.env`/`.db`/`.session`/`.gguf`; empty runtime
  dirs; `sha256sum -c` OK); the automated Release workflow attached the ZIP +
  `.sha256` to the GitHub Release.

## 2f. v1.0.5 ‚Äî product slice (2026-10-04, released)

Product-slice release (D-064). No new phase. Makes the suite useful **without a
user (MTProto) account**, plus a first-run guide and a conservative updater. One
Alembic migration (`7cb72d22d35b`, autogenerate-drift clean) adds every new table.

- **Bot‚Üîchannel bindings + reaction capabilities** ‚Äî `bot_channel_bindings` +
  `channel_capabilities` tables, repositories, `binding_service` /
  `capability_service`, `/api/v1/bindings*` + `/api/v1/capabilities/*`. The
  reaction planner intersects the profile emoji with the channel's confirmed set
  (`reaction_policy.intersect_reactions`), so it never schedules an unsupported
  reaction.
- **Invite campaigns (session-free)** ‚Äî `invite_campaigns` / `invite_links` /
  `join_requests` + `campaign_service` + `/api/v1/campaigns*`, with conservative
  risk modes and Bot-API-only link actions.
- **Donor quality** ‚Äî `donor_metrics` + `donor_heuristics` / `donor_service` +
  `/api/v1/donors*`; explainable bands, and the bot-share estimate stays `null`
  when member data is unavailable (never invented).
- **Backup delivery destinations** ‚Äî `backup_destinations` +
  `destination_service` + `services/backup_backends/*` (local, Telegram, Google
  Drive, –Ø–Ω–¥–µ–∫—Å.–î–∏—Å–∫) + `/api/v1/backup/destinations*`; credentials sealed, a
  local destination auto-created and non-deletable. Fixed delivery so the archive
  bytes (not raw DB bytes) reach every enabled destination.
- **Setup Wizard** ‚Äî `promotion_progress` + `promotion_service` +
  `/api/v1/promotion*`; resumable, preset-driven, reflects real state, session
  steps become `optional` without a session.
- **Conservative auto-update** ‚Äî `update_state` + `update_service` +
  `core/versioning` + `/api/v1/update*`; off by default, checks GitHub releases
  and stages a SHA-256-verified file, never auto-installs.
- **Diagnostics** ‚Äî new subsystem rows (`bindings`, `capabilities`,
  `backup_destinations`) and redacted-report sections (`queue`, `bindings`,
  `capabilities`, `campaigns`, `donors`, `backup_destinations`, `update`).
- **Frontend (RU-first)** ‚Äî new `CampaignsView.vue` (`/campaigns`), a
  "–ë–æ—Ç –∏ —Ä–µ–∞–∫—Ü–∏–∏" column in `ChannelsView.vue`, backup destinations in
  `BackupView.vue`, and the Setup Wizard + Update cards in `SystemView.vue`.
- **Ops** ‚Äî `updates/` git-ignored and created by `scripts/build_portable.sh`.
- Tests: `tests/test_bindings_api.py`, `tests/test_campaigns_api.py`,
  `tests/test_product_api.py`, extended `tests/test_diagnostics.py`. Suite
  **491 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

## 2g. v1.1.0 ‚Äî Account Hub, discovery, encoder, bot-only UX (2026-10-04, on develop)

Maintenance/minor release completing the requested vertical slice. No new phase;
every addition is opt-in and never bypasses Telegram limits. Migrations:
`20261004_2047_76d92fe3e70b` (proxy_profiles, donor_candidates,
user_sessions.proxy_id) and the posts.intent / restriction_count follow-ups.

- **Account Hub ‚Äî local session import (D-070).** `services/session_import.py`
  defines one `SessionImportProvider` protocol with four providers: Telethon
  `.session` (SQLite header), `.session` + companion JSON (whitelisted keys
  `api_id`/`app_id`/`api_hash`/`app_hash`/`phone`/`dc_id`; secret keys never
  read), StringSession (written to `SESSIONS_DIR`, never echoed/logged) and
  Telegram Desktop TDATA (optional; honest `NOT AVAILABLE` without a reliable
  converter; source folder never modified/uploaded). API:
  `POST /sessions/import/detect`, `POST /sessions/import/artifact`,
  `GET /sessions/{id}/risk`. `SessionsView.vue` shows the "–¶–µ–Ω—Ç—Ä –∞–∫–∫–∞—É–Ω—Ç–æ–≤
  (–∏–º–ø–æ—Ä—Ç)" panel, format/state, the sensitive-file warning and the "–Ý–∏—Å–∫
  –æ–≥—Ä–∞–Ω–∏—á–µ–Ω–∏–π" column.
- **Network routes (proxies, D-065).** `proxy_profiles` + `user_sessions.proxy_id`,
  `/api/v1/proxies*`; password sealed, honest `ok`/`error`/`timeout` check,
  explicit non-bypass notice everywhere.
- **Donor discovery (D-066).** `donor_candidates` +
  `providers/discovery_base.py` / `telegram_discovery.py` +
  `services/donor_discovery_service.py` + `/api/v1/discovery*` (search /
  candidates / compare / add / clear). Candidates are proposals only; a source is
  added solely by an explicit click. `SourcesView.vue` gained the "–ê–≤—Ç–æ–ø–æ–∏—Å–∫
  –¥–æ–Ω–æ—Ä–æ–≤" panel with comparison.
- **Lightweight encoder (D-067) + ruBERT backend (D-068).** `ai/encoder.py`
  (dependency-free hashing encoder + prototype classifier; `MODE_ENCODER`), the
  `EncoderBackend` protocol, and the optional `cointegrated/rubert-tiny2`
  embedding backend (lazy, CPU-only, unload-when-idle). `services/encoder_service.py`
  + `/api/v1/ai/encoder/{status,install,check,remove}` download only the official
  files, verify SHA-256, store in the gitignored `models/` and report an honest
  status; `AiView.vue` shows the "–ú–∏–Ω–∏-–ò–ò" install card.
- **Bot-only UX (D-069).** Analytics without an account (`account_connected` /
  `account_note`, "–Ý–µ–∂–∏–º –±–µ–∑ –ª–∏—á–Ω–æ–≥–æ –∞–∫–∫–∞—É–Ω—Ç–∞"); adaptive wizard
  (`session_optional_note` / `session_risk_note`); intent ‚Üí reaction narrowing
  (`services/reaction_intent.py`; the planner intersects profile ‚à© intent ‚à©
  channel ‚à© bot-compatible and skips with a reason).
- **Bots UX.** `BotsView.vue` explains the three bot kinds (what/why/can/cannot/
  add-to-channel) and shows an honest binding status (`–ì–æ—Ç–æ–≤`/`–ù—É–∂–Ω—ã –ø—Ä–∞–≤–∞`/
  `–ù–µ –ø–æ–¥–∫–ª—é—á—ë–Ω`/`–û—à–∏–±–∫–∞`/`–ù–µ–¥–æ—Å—Ç—É–ø–µ–Ω`) with "–ü–æ–¥–∫–ª—é—á–∏—Ç—å –∫ –∫–∞–Ω–∞–ª—É" + "–ü—Ä–æ–≤–µ—Ä–∏—Ç—å".
- **Security.** `.gitignore` also excludes `tdata/`, `*.session.json`,
  `*.session_meta.json`; docs/SECURITY.md documents the import scope and proxy
  credential sealing; a cp775 mojibake corruption in `docs/API.md` was fixed.
- Tests: `test_session_import.py`, `test_proxy_api.py`, `test_proxy_service.py`,
  `test_discovery_api.py`, `test_donor_discovery.py`, `test_encoder.py`,
  `test_encoder_service.py`, `test_reaction_planner.py`; extended `test_ai_api.py`,
  `test_ai_classifier.py`, `test_session_service.py`, `test_diagnostics.py`.
  Suite **574 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

## 2h. v1.2.0 ‚Äî Content Studio (2026-10-05, on develop)

Minor release: the **v1.2 content-studio foundation** vertical slice. No new
phase; nothing is published without an explicit owner action and no Telegram
limit is bypassed. Migration: `20261005_1200_c4a1f8b2e6d9` (content tables, all
additive with server defaults).

- **Models + repositories.** `db/models/content.py`: `ContentSource`,
  `ContentItem`, `MediaAsset`, `Publication`, `ButtonSet`, `CommentPlan` (+ enums
  `ContentSourceKind`, `ContentSourceStatus`, `RightsStatus`,
  `ContentItemStatus`, `PublicationStatus`). `db/repositories/content.py`: one
  repository per model with dedup lookups (source hash / source message id /
  content hash / media hash).
- **Content sources (D-071/D-074).** `providers/content_base.py` +
  `providers/content_sources.py`: `ContentSourceProvider` protocol and Telegram /
  RSS / Atom / manual providers. Telegram reads through the existing
  `SessionProvider` (no Telethon import here); a `noforwards` source stores only
  the link and is marked `protected`.
- **Posting (D-071/D-072).** `providers/posting_base.py` (`PostingProvider`:
  publish/delete/send_comment/capabilities) + `providers/posting.py`
  (`BotPostingProvider` over `TelegramBotProvider`; `UserPostingProvider` over
  `SessionProvider`). No direct aiogram/Telethon imports.
- **Services.** `services/content_cleaner.py` (deterministic, explainable,
  cancellable), `services/content_markup.py` (`validate_markup`,
  `validate_buttons`, `render_preview`), `services/content_service.py` (sources,
  grab, items, clean, rights + attribution, rewrite via the generative LLM only,
  moderation: blocked keywords + quiet hours, `release_held`, dashboard),
  `services/posting_service.py` (plan / schedule / calendar / buttons / publish
  with `uncertain` idempotency / retry / auto-delete / first comments / tick).
- **Scheduler (D-075).** `scheduler/handlers.py::_handle_posting` runs one
  bounded pass and re-schedules itself every `POSTING_TICK_SECONDS` (D-008 style);
  `main.py` seeds the first tick with `QueueService.ensure_periodic`.
- **API + UI.** `api/v1/content.py` + `api/schemas/content.py` expose
  `/api/v1/content/*`; `frontend/src/views/ContentStudioView.vue` (`/content`, nav
  ¬´Content Studio¬ª) has four RU-first tabs (–û–±–∑–æ—Ä / –ò—Å—Ç–æ—á–Ω–∏–∫–∏ / –ú–∞—Ç–µ—Ä–∏–∞–ª—ã /
  –ö–∞–ª–µ–Ω–¥–∞—Ä—å). Help topics `content_studio`, `content_source`, `content_rights`.
- Tests: `test_content_posting.py`, `test_content_posting_api.py`; extended
  `test_scheduler.py` (periodic tick + `ensure_periodic`), `test_migrations.py`
  (v1.2 tables added in place), `test_help.py`. Suite **611 passed**; `ruff`
  clean; `vue-tsc` + `npm run build` clean.

## 2i. v1.3.0 ‚Äî Bot Factory + LAN Mesh (2026-10-05, released)

Minor release: the **Bot Factory** and the **optional LAN Mesh / offline control
plane** vertical slice (D-077‚Ä¶D-083). No new phase; Standalone (one computer)
stays the default; nothing registers Telegram accounts or bypasses Telegram
limits. Migration: `20261005_1600_d5b2e9c3f7a1` (bot-factory + mesh tables, all
additive).

- **Bot Factory (D-077/D-078).** `db/models/bot_factory.py` (`BotBatch`,
  `BotCandidate`), `db/repositories/bot_factory.py`, `services/bot_factory.py`
  (`BotFactoryService`: templates, deterministic `generate_name` /
  `generate_username` / `sanitize_prefix` / `validate_username`,
  `check_availability` ‚Äî a real Telegram check per candidate username ‚Äî native
  creation, adopt, bind, write-only tokens, dashboards). `api/v1/bot_factory.py`
  + `api/schemas/bot_factory.py` expose `/api/v1/bot-factory/*`; creation goes
  through the official owner-confirmed @BotFather flow and adoption/binding reuse
  the existing `BotService` + `BindingService` (one manager bot).
- **LAN Mesh / offline control plane (D-079‚Ä¶D-082).** `db/models/mesh.py`
  (`MeshNode`, `MeshPeer` ‚Äî credential stored as a salted hash, `PairingCode`,
  `MeshLease` with a monotonic `fencing_token`), `db/repositories/mesh.py`, and
  the `mesh/` package (`identity`, `discovery`, `pairing`, `election`, `lease`,
  `capability`, `transport` ‚Äî `MeshTransport` protocol + `HttpMeshTransport` +
  in-memory `RecordingTransport` ‚Äî and `service`). `/api/v1/mesh/*`
  (status, discover, peers, pairing-code, pair, unpair, probe, elect, leases);
  the `mesh.tick` durable maintenance job (probe peers, re-elect, reclaim expired
  leases; a cheap no-op while disabled). `main.py` keeps the manager-bot runtime
  off when the node is not the coordinator (no double-polling, D-081).
- **Hardening (D-083).** Pairing never persists or returns anything derived from
  a secret (the peer `note` is a plain status string; the shared secret is never
  stored); `/api/v1/mesh/ping` authenticates the `X-Mesh-Secret` header
  (timing-safe) and rejects unauthenticated requests when a secret is configured.
- **UI + config.** `frontend/src/views/BotFactoryView.vue` (`/bot-factory`) and
  `MeshView.vue` (`/mesh`), RU-first, with help topics `bot_factory` /
  `lan_mesh`; `core/config.py` mesh settings (`mesh_enabled` off by default,
  `mesh_mode=standalone`).
- Tests: `test_bot_factory.py`, `test_bot_factory_api.py`, `test_mesh.py`,
  `test_mesh_api.py` (offline against the deterministic fakes, D-001). Suite
  **664 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.
- **Released:** reviewed PR #9 (`develop ‚Üí main`, merge `7788125`), tag `v1.3.0`;
  the Release workflow created the GitHub Release and attached the Windows
  portable ZIP + `.sha256` (24.7 MB, checksum verified, artifact secret scan
  clean ‚Äî D-060).

## 2j. v2.0 cycle — owner-approved priorities (released in v2.0.0)

The owner approved a v2.0 cycle worked sequentially in separately verifiable
stages (Этапы). Priorities, in order: (1) **Web Wrappers + free multimodal AI
providers** — MAIN; (2) mass connection of created bots to channels; (3) Complete
Content Operations with target-language translation. No release is cut from this
cycle until the owner asks.

### Priority 1 — free-first providers + honest capabilities
Committed on `develop` (`feat(ai-gateway)` stage; `backend/app/ai/gateway/`):

- **`PollinationsProvider`** (`providers/__init__.py`) — a keyless, anonymous
  OpenAI-compatible text endpoint (`POST /openai/chat/completions`,
  `https://text.pollinations.ai/openai`). Text only: an image/file request is
  refused honestly (`CALL_BAD_REQUEST`) so the router fails over to a
  vision-capable provider.
- **`Llm7Provider`** — a second keyless free text path (llm7.io,
  `https://api.llm7.io/v1`, model `gpt-oss:20b`); anonymous chat proven, image
  request refused upstream → declared text only.
- **`PollinationsImageProvider`** (`kind=pollinations_image`) — keyless free
  **image generation** (`https://image.pollinations.ai/prompt/…`, model `flux`);
  probed HTTP 200 / `image/jpeg`, deterministic per prompt+seed. Generation only
  (declares no text/image understanding) and **off by default** (opt-in).
- **Honesty fix** — `ProviderInfo.info` now derives `auth_required` from the auth
  mode (`auth_mode == AUTH_API_KEY and not api_key`), so a keyless or
  browser-session provider never claims it needs a key.
- **`catalog.py`** — per-model capability matrix (operations, auth, cost,
  `verified`/`verified_operations`); backs `GET /models`. Verified entries:
  `pollinations` (text, structured), `llm7` (text), `pollinations_image`
  (image_generation). No keyless entry is verified for vision.
- **`provisioning.py`** — `FREE_PROVIDER_DEFAULTS`; `POST /provision` seeds the
  free-first providers once, idempotently, never re-enabling a disabled row
  (`pollinations` + `llm7` enabled; `pollinations_image` + `ollama` off).
- **`preflight.py`** — `preflight()`/`probe()` browser environment inspection;
  honest per-step progress, never fails. `GET /browser/preflight`,
  `POST /browser/prepare`.
- **`GET /operations`** — per operation (incl. `image_generation`, matched by
  kind), the **configured** providers that can serve it now.
- **Web wrappers** — added disabled, honest definitions for Microsoft Copilot and
  Duck.ai (the latter never bypasses the anti-bot challenge).
- **UI** — `AiGatewayView.vue` model/operation matrix, a free-first provisioning
  button and a browser-preflight panel; typed client methods in `api/client.ts`.
- **Tests** — `tests/test_v2_ai_providers.py` (keyless honesty, text-only vs
  vision routing, image generation, provisioning, preflight, registry kinds).

### Priority 1 — Stage 2 (free multimodal / vision): probed 2026-10-09, none confirmed
Probed keyless endpoints honestly (D-119): `api.llm7.io` keyless models refuse an
image (`400`); `gen.pollinations.ai` vision models need a key (`401`);
`api.airforce` is paid (`402`); DuckDuckGo is an anti-bot challenge (never
bypassed). **No genuinely free, keyless image-understanding endpoint exists**, so
none is claimed. The confirmed free multimodal path is **image generation**
(Stage 1). Vision stays on keyed providers (Google/Anthropic) or the owner's own
logged-in browser session. Re-check only when a real, keyless, non-bypass vision
endpoint is confirmed.

### Priority 3 — Target Language stage
Committed on `develop` (`feat(content): Target Language stage (v2.0 Part 1)`):

- **`services/content_language.py`** — a language stage: a **source language**
  (auto-detected or set per source) and a **target language** resolved by
  precedence (publication → channel → source → global default); translation runs
  only when the languages actually differ.
- **Protected translation** — URLs, `@username`, `t.me` links, hashtags, inline
  code, HTML tags and Telegram-entity spans are masked with private-use
  placeholders before the text is sent to the AI and restored verbatim after, so
  the model never rewrites a link or identifier. Uses the **existing** AI Gateway
  (retries/failover unchanged); a total failure never loses material.
- **Migration** `20261013_0900_d4e5f6a7b8c9_v2_0_target_language.py`; API
  `GET /api/v1/content/languages`, `POST /api/v1/content/items/{id}/language`,
  `POST /api/v1/content/items/{id}/translate`; per-source/channel/item/publication
  language columns; `ChannelsView.vue` / `ContentStudioView.vue` UI.
- **Tests** — `tests/test_target_language.py`.

### Priority 2 — mass bot→channel connection (D-120)
Shipped in v2.0.0 (`feat(...)` bot-onboarding stage):

- **`services/bot_onboarding.py`** — connect many already-created worker bots to
  one channel through Telegram's **official**
  `t.me/<bot>?startchannel&admin=<rights>` deep link (rights joined by **`+`**,
  Bot API 6.0+, never a space). Rights are least-privilege, purpose-named
  profiles (`reactions`/`posting`/`editing`) — never a blanket "all rights". The
  owner confirms each bot in Telegram; the candidate is then re-checked against
  Telegram through the existing **BindingService**, so `ready` means "Telegram
  reports the rights" and insufficient rights is an explicit `needs_permission`.
- **Durable, restart-safe queue** — scheduler job `bot_onboarding.tick` advances
  one bot per tick (the Bot Factory model, D-109); pause/resume/retry/skip; a
  failure never stops the rest and already-connected bots are never rolled back.
- **No secret ever leaves** — the bot token is never part of any request or
  response; only the public username and Telegram's own link are exposed.
- **Migration** `20261014_0900_e5f6a7b8c9d0_v2_0_bot_onboarding.py` (revises
  `d4e5f6a7b8c9`; additive, in-place upgrade); API `/api/v1/bot-onboarding/*`;
  capability `bot_onboarding`, Diagnostics check, help topic and the RU-first
  `BotOnboardingView.vue` (`/bot-onboarding`) UI.
- **Tests** — `tests/test_bot_onboarding.py`; two runtime meta-audit mutations
  (`AA_onboarding_deeplink_separator`, `AB_onboarding_capability_anchor`) and the
  static check `check_telegram_deeplink_contracts`.

## 5. Next action

**v2.0.0 is released** (reviewed `develop → main` PR #23, merge `926a3b3`, tag
`v2.0.0`; GitHub Release with the Windows portable ZIP + `.sha256`, built by CI —
D-060). `main` HEAD = `926a3b3`; `develop` is re-synced to `main`. Version strings
read **2.0.0** everywhere. The v2.0 cycle is complete; no release is cut until the
owner asks (D-060).

`NEXT_TASK` records that there is no active task; the roadmap (PHASE 0–11) is
complete. Optional future work (only if the owner asks): a fully automated
@BotFather Mini App flow (D-054); short-lived signed Mini App tokens if it is ever
exposed beyond the owner (D-035); a reliable, permissively-licensed TDATA
converter adapter (D-070); or any feature the owner requests (record a decision;
keep the vertical-slice workflow).

### RC verification (2026-10-03) ‚Äî done against a live server in offline mode

A full user journey was exercised end-to-end via HTTP (fake providers, real
scheduler, real SQLite): setup-wizard ‚Üí add bots/health ‚Üí session auth wizard ‚Üí
audience source/scan ‚Üí import users/tags ‚Üí reaction profiles/rules/simulate ‚Üí
ingest post + plan + execute ‚Üí invite preview/create/confirm/run ‚Üí **kill server ‚Üí
restart (recovery)** ‚Üí resume invite to completion ‚Üí backup ‚Üí graceful shutdown.
Also verified: SPA deep links and all 15 pages render RU-first with plain-language
help; `vue-tsc` + `npm run build` clean; `ruff` clean; hidden-member/FloodWait
limits surface as statuses (never bypassed); secrets/phone masked; git has no
tracked secrets.

**Bugs found and fixed during the RC pass:** D-044 (reaction policy on
execution), D-045 (invite stuck-task recovery), D-046 (sad-news default rule),
plus a Reactions-page status-text bug and a duplicate `backup_dir` config field.

**Known gaps (documented, not blocking):** Mini App @BotFather registration is a
deployment step (the one-click menu-button helper exists, D-054); the manager-bot
command loop runs only while the app is running (no webhook by default). Both are
intentional, not defects.

## 6. Locked decisions (do not break)

See `agent/DECISIONS.md`. Key ones:

- Provider/adapter abstraction for all Telegram access (D-001).
- SQLite now, PostgreSQL later, without business-logic rewrite (D-002).
- One SPA for Web UI and Mini App; one API (D-003).
- One backend for Windows/Linux/portable/Docker (D-004).
- AI optional and disableable (D-005).
- No bypassing Telegram FloodWait / privacy / admin restrictions (D-006).
- Durable DB-backed queue; recover unfinished jobs on startup (D-008).
- Secrets never committed or displayed; logging redaction mandatory (D-010).
- Frontend builds to static; no Node.js in production (D-012).
- Bot tokens sealed at rest with Fernet; never returned by the API (D-017).
- Managed bots only via the official API + user confirmation (D-018).
- Provider selection via config; `offline_mode`/`fake` for tests (D-019).
- Rules Engine is deterministic; categories/rules are editable data (D-020).
- Reaction planner is pure with an injectable RNG; emoji are deterministic (D-021).
- Reaction profiles are named, one default; preview is forgiving (D-022).
- User accounts use lazy, per-operation MTProto connections (D-023).
- The auth wizard is a durable, resumable state machine (D-024).
- Account secrets are sealed; the API exposes only presence (D-025).
- Audience parsing goes through `AudienceProvider`, a thin adapter over the
  PHASE 4 `SessionProvider`; scans are chunked and restart-safe (D-026).
- Audience scans have a dry-run preview; completeness is reported honestly
  (`complete`/`partial`/`no_access`) and FloodWait pauses rather than loops (D-027).
- Audience dedup key is the unique `telegram_user_id`; membership is a
  many-to-many `source_user_links` table (D-028).
- Audience PII is masked at rest, exports are local-only and PII-off by default
  (D-029).
- Invites require server-side confirmation and run as bounded durable batches;
  limits are never bypassed (D-030).
- The Tiny AI is an optional adapter behind a `Classifier` Protocol; the Rules
  Engine stays the deterministic default (D-031/D-032).
- AI output is strictly validated JSON; the LLM never picks emoji (D-033).
- AI config is UI-editable and DB-overridable with plain-language help; models are
  user-provided `.gguf` assets, never committed/downloaded (D-034).
- AI inference is single-concurrency and bounded, and always degrades gracefully
  (D-035).
- Analytics is a read-only aggregate layer; plain-language summaries are owned by
  the backend, and per-day bucketing is portable (D-036).
- Charts are dependency-free inline SVG; the SPA stays the single frontend
  (D-037).
- Mini App auth verifies Telegram `initData` server-side and issues a signed
  `HttpOnly` cookie; it is the same SPA/API as the Web UI, off by default, and
  never requires a public server for local use (D-038).

## 7. How to run / verify after opening a new chat

```bash
git fetch origin && git checkout develop   # development branch (not main)
git status && git log --oneline -20
cat agent/CURRENT_STATE.md agent/NEXT_TASK.md agent/DECISIONS.md
cat docs/ROADMAP.md

python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest                       # must pass
python -m backend.app.main             # http://127.0.0.1:8000

cd frontend && npm install && npm run build && cd ..
```

## 8. GitHub sync & branching

- Remote: `https://github.com/Surimat/Telegram-Channel-Management-Suite`.
- First sync (2026-10-03): PHASE 0‚Äì3 (commits `0daa91b`‚Ä¶`f06ba53`) pushed to
  `develop`; PR **#1** `develop ‚Üí main` opened but **not merged** (needs explicit
  owner confirmation).
- **Second sync (2026-10-03):** PHASE 4‚Äì6 pushed to `develop` as a fast-forward
  (`92d94e4`‚Ä¶`3ddc299`; no force). PHASE 6's functional commit is `3ddc299`;
  `origin/develop` contains PHASE 4 (`92d94e4`), PHASE 5 (`8197f33`) and PHASE 6
  (`3ddc299`). One or more sync-record doc commits sit above `3ddc299` (e.g.
  `5cb6386`); `develop` is **0 ahead / 0 behind** `origin/develop`.
- PR **#1** (`develop ‚Üí main`) tracks `develop`'s head automatically (currently a
  sync-record doc commit above `3ddc299`); still **open**, `merged: false` ‚Äî
  **not merged** (awaiting owner confirmation).
  URL: https://github.com/Surimat/Telegram-Channel-Management-Suite/pull/1
- **Never push directly to `main`.** All work goes to `develop` (or feature
  branches off it) and lands in `main` only via a reviewed pull request.
- `main` was at the PHASE 3 commit (`f06ba53`) until PR #1 merged; it now points
  at the release merge commit `82c1059` (same as `develop`).
- **RC sync (2026-10-03):** PHASE 7‚Äì11 + polish + RC hardening pushed to
  `develop` (`fd53ad1`‚Ä¶`e65a374`; fast-forward, no force). `origin/develop` is
  now at `e65a374` (RC hardening). PR #1 retitled to **"Full roadmap (PHASE 0‚Äì11)
  + release-candidate hardening"** with a full body; still **open**, `merged:
  false` ‚Äî **not merged** (awaiting owner confirmation).
- **Hardening sync (2026-10-03):** post-1.0 hardening (manager-bot runtime +
  notifications + permission probe) pushed to `develop` as a fast-forward
  (`ba30578`‚Ä¶`727b0f8`; no force). Functional commit `c0174a8`; `origin/develop`
  is now at `727b0f8`. PR #1 retitled to **"Full roadmap (PHASE 0‚Äì11) + RC &
  post-1.0 hardening"** with an updated body.
- **Release v1.0.0 (2026-10-03):** release-prep commits `b442e08` (build fix:
  keep `backend/app/static/.gitkeep` across Vite builds), `f53cadf` (memory/docs
  sync to actual state, new `docs/RELEASE_CHECKLIST.md`) and `6a45e0a`
  (AGENTS release section) pushed to `develop`. PR #1 was marked ready and
  **merged into `main`** with merge commit `82c1059` (no force, no history
  rewrite). `develop` fast-forwarded to `82c1059` (both branches 0 ahead / 0
  behind). Local stale `main` (`f06ba53`) fast-forwarded to `origin/main`.
  Annotated tag **`v1.0.0`** created on `82c1059` and pushed; **GitHub Release
  `v1.0.0`** published:
  https://github.com/Surimat/Telegram-Channel-Management-Suite/releases/tag/v1.0.0
- No history rewrite, no force push.
- Secret audit before push: `.env`, `data/*.db`, session files and portable
  runtimes are git-ignored and confirmed absent from the remote; the mutable
  runtime dirs (`sessions/`, `logs/`, `data/`, `backups/`, `exports/`) contain
  only `.gitkeep` on the remote. The PHASE 5‚Äì6 diff contained no real tokens,
  api_hash values, session strings, passwords or exported PII (only code
  parameter names such as `api_hash`).
- **Release v1.3.0 (2026-10-05):** the v1.3.0 Bot Factory + LAN Mesh work was
  committed on `develop` (`548f309`), pushed (fast-forward, no force), and merged
  into `main` via reviewed **PR #9** (`develop ‚Üí main`, merge `7788125`). Annotated
  tag **`v1.3.0`** created on `7788125` and pushed; the **Release** workflow
  verified the code and built the Windows portable ZIP, then created the **GitHub
  Release `v1.3.0`** and attached the ZIP + `.sha256` (24.7 MB; checksum verified,
  artifact secret scan clean ‚Äî D-060). `develop` fast-forwarded to `7788125`, so
  `main == develop == 7788125`. No history rewrite, no force push; the
  `v1.0.0`‚Äì`v1.2.0` tags are untouched (D-050).
