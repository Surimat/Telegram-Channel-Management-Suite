# CHANGELOG — Telegram Channel Management Suite

All notable changes, newest first. Format loosely follows Keep a Changelog.
Dates are ISO-8601.

---

## [1.7.0] — 2026-10-08

**v1.7.0 — Bot Factory becomes a durable creation queue (additive minor).**
Released via a reviewed `develop → main` PR #18 (merge `48eecdc`), tag `v1.7.0`;
the Release workflow (run `37634439503`) attached the Windows portable ZIP
(24 853 898 bytes, sha256 `a444bb55…e5af`) + `.sha256`. Version strings read
**1.7.0**; no account registration and no Telegram-limit bypass.

### Added
- **Bot Factory creation queue (D-109).** A batch now marks its free candidates
  and lets the durable scheduler job `bot_factory.create` create them **one at a
  time**, so the batch is restart-resumable and can be closed safely. New service
  methods `enqueue_candidates`, `run_queue_once`, `queue_progress`,
  `retry_candidate`, `skip_candidate`, `cancel_queue`, `resume_queue`; a
  `QueueState` state machine and `queue_cancelled`.
- **API queue endpoints.** `POST /api/v1/bot-factory/batches/{id}/enqueue|cancel|resume`
  and `POST /api/v1/bot-factory/candidates/{cid}/retry|skip`; per-candidate queue
  state in the batch payload; a `queue` block on the dashboard.
- **Non-reversible `token_mask` (D-110).** A display-only `1234…xyz` shape derived
  from the non-secret numeric bot id — never by decrypting the sealed token.
- Queue controls in `BotFactoryView.vue` (start/stop/resume, per-row retry/skip,
  queue progress), a `bot_factory` capability requirement, a Diagnostics check, a
  Promotion Wizard step and a "Фабрика ботов" help topic.
- Migration `20261008_0900_a1b2c3d4e5f6_v1_7_bot_factory_queue.py`
  (`bot_batches.queue_cancelled`, `bot_candidates.queue_state`/`attempts`/
  `token_mask`).

### Notes
- Deep-link batches are **not** background-ticked: the owner finishes them by hand
  in Telegram, so the queue settles instead of looping.
- Tests: `tests/test_bot_factory.py` (queue lifecycle, retry/skip, cancel/resume,
  mask), `tests/test_bot_factory_api.py` (queue over HTTP), `tests/test_scheduler.py`
  (one op per tick, no deep-link loop).

---

## [Unreleased] (historical)

**Clean-checkout verification of v1.6.1 + documentation reconcile.** No code
change, no new feature, no release.

### Fixed
- **Documentation drift after the v1.6.1 release.** `agent/CURRENT_STATE.md`
  still stated `Version string is **1.6.0**` and `main HEAD = 39efc37`, and
  `agent/NEXT_TASK.md` still announced `v1.6.0 is released` with `822 passed`;
  `docs/RELEASE_CHECKLIST.md` had no v1.6.1 verification section. All three now
  name v1.6.1 (`a38823d` / `b8ee5ca`) with the 843-test result and the v1.6.1
  gate table.

### Added
- `tests/test_meta_audit.py::test_memory_files_state_the_current_release` and
  `::test_release_checklist_covers_the_current_release` — guard the memory files'
  current-version anchor and the release-checklist section, so this drift cannot
  recur unnoticed.

### Notes
- Verified the released tag on a **clean checkout** (`git clone` →
  `git checkout v1.6.1` → fresh venv): `pytest` **843 passed**, `ruff` clean,
  `vue-tsc` + `npm run build` clean, Docker build + smoke (`/health` → `1.6.1`),
  portable build/smoke (ZIP 1.6.1, app copy imports), meta-audit **25/25, 100%**,
  artifact scan clean (2799 entries, no session/TDATA/DB/model).

---

## [1.6.1] — 2026-10-07

**Patch: independent verification of v1.6.0 Owner Auth + Config Sync.** Fixes a
path-normalisation weakness in the owner guard and a capability-state
overstatement; wires the Google Drive token step in the `/owner` UI. Additive and
behaviour-preserving for the local-first default.

### Fixed
- **Owner guard path normalisation (security hardening, D-107).** `is_protected`
  compared the raw request path with a prefix test, so a leading doubled slash
  (`//api/v1/...`) was treated as a non-API path and skipped the guard while the
  router still matched it. The guard now collapses redundant slashes, resolves dot
  segments, and matches the allowlist by exact path or segment boundary
  (`/health` but not `/healthcheck`). Verified on a real uvicorn server with
  `curl --path-as-is`: `//api/v1/settings` etc. now return **401**, while
  allowlisted paths and valid-token access are unchanged.
- **`config_sync` capability state (D-107).** The capability declared
  `minimal=(owner_auth,)`, so "owner ready but no provider connected" reported
  `partial`. Per D-106 the states are `needs_setup` / `available` / `error`; the
  `minimal` set was removed so it now reports `needs_setup` (never a false
  `partial`). `docs/UI.md` updated accordingly.
- **Google Drive connect flow (`/owner` UI).** `showAdvanced` was set but never
  used and no token input existed, so `syncGoogleConnect` could never be called.
  Added a token field and a "Сохранить токен Google" button wired to the existing
  endpoint (no new API).

### Added
- `tests/test_v16_verification.py` — independent negative/security tests for
  Owner Auth (no-token 401, foreign-token 401, no alternative-endpoint bypass,
  middleware-level leading-`//` rejection), the encrypted bundle (wrong-key,
  tamper, truncation, schema-version, secret exclusion), the Google Drive
  app-data scope, conflict detection/refusal, the local provider, capability
  states, diagnostics secret-freedom, and RU/EN translation. No network, no real
  accounts, no real secrets.

### Notes
- No new features; no schema change; no new dependency. `pytest` **843 passed**,
  `ruff` clean, `vue-tsc` + `npm run build` clean, meta-audit **25/25, 100%,
  0 false positives**.

---

## [1.6.0] — 2026-10-07

**Owner Auth + Config Sync vertical slice.** A local owner profile protects the
panel, and an encrypted, versioned configuration bundle moves the owner's settings
to a new computer — never the database, sessions or TDATA. Additive only; no
account registration and no Telegram-limit bypass.

### Added
- **Owner Auth (D-105).** A single local identity (password or PIN) that protects
  the Web UI/API. A slow **PBKDF2-HMAC-SHA256 verifier** (200k iterations) is
  stored; the password is never. A successful login issues an **HMAC-signed opaque
  session token** (`X-Owner-Token`). `OwnerGuardMiddleware` is default-on for every
  `/api/` path outside a small allowlist, so a new router cannot be added unguarded.
  It is **local-first**: while no profile exists (or protection is off) the API is
  open exactly as before. Wrong attempts are rate-limited (5 → 15-minute lock).
  New `/api/v1/owner/*` endpoints, the `/owner` RU-first UI page, an `owner_auth`
  help topic, a capability requirement and a Diagnostics check.
- **Config Sync (D-106).** A **versioned, encrypted configuration bundle**
  (canonical JSON → AES-256-GCM, schema version authenticated as associated data).
  Providers store ciphertext only: a **local folder** (default) or the owner's
  **Google Drive app-data scope** (least privilege; no bundled OAuth secret). A
  **denylist + `scan_for_secrets`** excludes anything that looks secret before an
  export; sync **detects conflicts** and never overwrites silently; restore is
  preview-first. `/api/v1/owner/sync/*`, a `config_sync` help topic, capability and
  Promotion Wizard step.
- **Consistency Auditor section `5b-2` (config-sync providers).** Fails CI if a
  provider kind has no module, the registry is incomplete, or the bundle's secret
  anchors (`FORBIDDEN_KEY_MARKERS`, `scan_for_secrets`, `serialize`, `deserialize`)
  disappear.
- Migration `20261007_1000_f8b2d3e5a7c9` (`owner_identities`, `config_sync_state`),
  models `OwnerIdentity` / `ConfigSyncState`, repositories `OwnerRepository` /
  `ConfigSyncRepository`, services `owner_auth_service` / `config_sync_service` /
  `config_bundle`, providers `config_sync_base` / `config_sync_local` /
  `config_sync_gdrive`.
- Tests: `tests/test_owner_auth.py`, `tests/test_config_sync.py`,
  `tests/test_owner_api.py`.
- Decisions D-105, D-106.

### Changed
- The `config_sync` capability is now **implemented** (`requires` owner auth +
  Google Drive, `minimal` owner auth) instead of `not_implemented`.
- Diagnostics gained `owner_auth` and `config_sync` checks and non-secret payloads;
  the Setup Wizard gained `owner_auth_check` / `config_sync_check`.
- `frontend/package-lock.json` version synced to `1.6.0`.
- `ruff` clean; full suite green; `vue-tsc` + `npm run build` clean; meta-audit
  **25/25, 100%, 0 false positives**.

---

## [1.5.4] — 2026-10-06

**The last three Consistency Auditor gaps N, O and P are closed (D-104).** No new
product features; a patch release. The auditor now detects **every** seeded defect:
the runtime mutation engine reaches **100% (25/25) with 0 false positives**, and
`KNOWN_GAP_IDS` is empty.

### Added
- **`check_unused_model_columns` (gap N).** Static check: an ORM column derived from
  `mapped_column` whose name never appears as an attribute, keyword argument or
  string literal outside the model files is flagged
  `db.unused_column.<module>.<Class>.<name>` (`info`, confidence `medium`). Reports
  12 genuinely dead columns on the real tree; extension points can be allow-listed
  in `INTENTIONAL_UNUSED_COLUMNS`.
- **`check_orphan_service_classes` (gap O).** Static check: a public service class
  that no module references (a plain `import` does not count) is flagged
  `dead.service.<module>.<Class>` (`info`). Exempt list:
  `INTENTIONAL_ORPHAN_CLASSES`.
- **`check_frontend_unwired_controls` (gap P).** Static check: a Vue
  `@click`/`@change`/`@submit`/`@input` handler that names a function the component
  never defines, or a function with an empty body, is flagged
  `frontend.control_unwired.<name>` (`warning`). Inline expressions are out of
  scope. Clean on the real tree.
- Three negative controls — `NC6_used_db_column`, `NC7_referenced_service` and
  `NC8_wired_frontend_control` — prove precision (an added-and-read column, an
  added-and-instantiated class, and a control with its defined handler are not
  flagged).
- Decision D-104.

### Changed
- `N_unused_db_field`, `O_service_without_caller` and `P_control_without_behavior`
  moved out of `KNOWN_GAP_IDS` and are now **detected** at runtime;
  `KNOWN_GAP_IDS` is empty.
- Detector-removal dynamism is now proven for all five gaps by a single
  parametrised test (`test_removing_a_gap_detector_turns_it_into_a_miss`, M/N/O/P/Q).
- `agent/META_AUDIT_RESULT.json` regenerated: **25 total, 25 detected, 0 missed,
  kill rate 100.0%, 0 false positives, 0 critical misses, 0 high misses**
  (`status: clean`).
- Full suite: **800 passed, 0 xfailed**; `ruff` clean; `vue-tsc` + `npm run build`
  clean.
- Version strings bumped to **1.5.4** across `backend/app/__init__.py`,
  `pyproject.toml`, `frontend/package.json` + lock.

---

## [1.5.3] — 2026-10-06

**Consistency Auditor gaps M and Q closed (D-103).** No new product features; a
patch release. The two remaining **high**-impact coverage gaps are now detected by
pure static checks, and the kill rate rises to **88.0% with 0 high misses**.

### Added
- **`check_write_only_settings` (gap M).** Static AST check: a setting key written
  via `SettingsService.set(<literal>)` (including a local alias, `self.settings`,
  `self.repo`) with no literal reader (`.get_typed`/`.get_raw` or a declared
  `*_SETTING_SPECS` map) is flagged `settings.write_only.<key>`. Env-backed keys are
  skipped. Clean on the real tree (no false positives).
- **`check_channel_registry_usage` (gap Q).** Static check: a service module that is
  channel-aware (class/function named `*channel*`, or a `channel_id` /
  `registry_channel_id` parameter) but never uses a canonical channel identity (no
  `Channel*` import, no canonical parameter) is flagged
  `channel-aware.module.<module>`. Clean on the real tree.
- Two negative controls — `NC4_setting_with_reader` and
  `NC5_channel_aware_with_registry` — prove precision (a written-and-read setting
  and a channel-aware module using `ChannelRepository` are not flagged).
- Decision D-103.

### Changed
- `M_write_only_setting` and `Q_channel_aware_module` moved out of
  `KNOWN_GAP_IDS` and are now **detected** at runtime (remaining gaps: N, O, P).
- Runtime `_known_setting_keys()` is honest: it no longer allow-lists setting keys
  that no module consumes (`sync_enabled`, `owner_*`), so the runtime orphan check
  agrees with the static one.
- `agent/META_AUDIT_RESULT.json` regenerated: **25 total, 22 detected, 3 missed,
  kill rate 88.0%, 0 false positives, 0 critical misses, 0 high misses**
  (`status: gaps_found`).
- Full suite: **787 passed, 0 xfailed**; `ruff` clean; `vue-tsc` + `npm run build`
  clean; Docker smoke clean (`/health` → `1.5.2`, SPA `200`, `/api/v1/consistency`
  → `pass`, 0 error / 0 warning / 6 info).

### Runtime mutation engine for the Consistency Auditor (D-102)

**No new product features; no release.** The v1.5.2 kill rate was *declarative*
(hand-maintained `_DETECTABLE` / `_MISSED` lists). It is now **computed from real
executions**.

### Changed
- **Meta-audit is now measured, not declared.** New package `tests/meta_audit/`
  (`engine.py`, `mutations.py`): `MutationSandbox` copies `backend/app`,
  `frontend/src`, `migrations/versions`, `docs` into a temp dir (or a fresh temp DB
  for runtime checks), injects one seeded defect, runs the **real** auditor, and
  semantically matches the finding it actually produced. `SuiteResult` derives
  `detected`/`missed`/`kill_rate`/`false_positives`/`critical_misses`/`high_misses`
  from those records; `verify()` asserts the arithmetic.
- `agent/META_AUDIT_RESULT.json` is now a **generated** artifact with
  `result_source: "computed from runtime mutation executions"`, `generated_at`,
  `baseline_sha`, and per-mutation `{id, detected, expected, actual_findings,
  severity}`. At D-102 the run was **25 total, 20 detected, 5 missed, kill rate
  80.0%, 0 false positives, 0 critical misses, 2 high misses**; D-103 raised it to
  22/25 / 88.0% / 0 high misses.
- `tests/test_consistency_mutations.py` rewritten: per-mutation runtime
  classification, negative controls (0 false positives), a **detector-removal
  proof** (disabling a check flips its mutation to missed and lowers the rate), a
  **new-mutation proof** (adding a mutation changes `total`), and working-tree
  isolation assertions.
- `tests/test_meta_audit.py` rewritten: the declarative `_DETECTABLE`/`_MISSED`
  kill-rate summary is **deleted**; kept the silent-failure guard, the runtime
  drift checks, and added generated-report provenance + arithmetic checks.
- `.github/workflows/ci.yml` job `meta-audit` now runs the engine, the tests, and
  a working-tree leak assertion. It no longer relies on a hardcoded percentage.
- **CI verified:** run `37479210076` (push, commit `f007c0b`) — Backend, Frontend and
  `Meta-audit (auditor kill-rate)` all **success**; the uploaded
  `meta-audit-result` artifact has `result_source = "computed from runtime mutation
  executions"`, 25 mutations with boolean `detected`, negative controls, kill rate
  computed dynamically. `vue-tsc` + `npm run build` clean locally.
- **Docker smoke (unchanged, re-verified):** `/health` → `1.5.2`, SPA `200`,
  `/api/v1/consistency` → `pass` (0 error, 0 warning, 6 info); image artifact scan
  clean (no `.session`/TDATA/DB/model/`.env`; runtime dirs empty).

### Added
- One extra mutation `U_help_reference` (25 total) and `KNOWN_GAP_IDS` — documented
  gaps are still **executed**, never hardcoded as misses.
- Decisions D-101 (default language is Russian) and D-102 (kill rate is computed
  from runtime executions).

### Removed
- The `strict=True` xfail gap tests and the declarative kill-rate constants.

---

## [1.5.2] — 2026-10-06 — released

Patch release: the **Consistency Auditor is now proven against deliberately seeded
defects** ("Проверка проверяющего", D-099/D-100). No new product features; no
account registration; no Telegram-limit bypass.

Released via a reviewed `develop → main` PR #13 (merge `523c089`), tag `v1.5.2`;
the Release workflow (run `37464579513`) created the GitHub Release and attached
the Windows portable ZIP (24 799 763 bytes, sha256 `ee8562ef…9ed03`) + `.sha256`
(D-060). Gates: `pytest` **761 passed, 4 xfailed**, `ruff` clean, `vue-tsc` +
`npm run build` clean, static consistency suite `pass` (0 error, 0 warning, 2
info), CI job `meta-audit` green (kill rate 75%), artifact/secret scan clean.

### Added
- **Meta-audit harness** (`tests/test_consistency_mutations.py`,
  `tests/test_meta_audit.py`): each test builds an isolated copy of the source
  tree, injects one synthetic defect, and asserts the auditor reports it. Nothing
  is written to the working tree. A machine-readable kill-rate summary is written
  to `agent/META_AUDIT_RESULT.json` and uploaded by a new CI job `meta-audit`.
- **New static checks** in `services/consistency_checks.py`:
  `check_router_registration` (`api.router_unregistered.<module>`),
  `check_backup_destination_registry` (`backup.destination_no_module` /
  `backup.destination_missing`), `check_notification_routing`
  (`notifications.no_routing.<category>`), and `check_hardcoded_ui_strings`
  (`ux.hardcoded_string.<file>:<line>`, warning).
- **Release-hygiene guards**: `test_repo_version_is_consistent` and
  `test_readme_states_the_current_release`.

### Fixed
- **Capability false-positive / stray-string mask.** `check_capability_implementation`
  now requires a strong anchor (a real service class) via
  `CAPABILITY_SERVICE_ANCHORS`; a capability claiming `implemented=True` with no
  anchor is an error (`capabilities.no_anchor.<key>`), and a missing/renamed
  service is `capabilities.unimplemented.<key>`.
- **Provider registry drift.** `check_provider_registry` now verifies every
  provider module imported by `registry.py` exists
  (`providers.registry_missing.<module>`).
- **Capability dependency not enforced.** `capability_graph.evaluate()` now treats
  a requirement naming an unimplemented capability as missing, so a dependent
  capability can never report `available`/`partial` on that basis.
- **Runtime `_check_channel_aware` silent failure.** It queried
  `ContentItem.channel_id` (a non-existent column), always raised, and was
  swallowed by `except Exception: return findings` — the check had never detected
  anything. It now queries `ContentSource.channel_id` and emits
  `channel-aware.content_source`.
- **README version drift.** README claimed `v1.5.0` while the code shipped
  `v1.5.1`.

### Known gaps (recorded, not hidden)
The auditor's measured kill rate is **75%** (18 of 24 seeded defects detected, 6
missed, 0 critical, 2 high). The 6 misses are documented in
`agent/META_AUDIT_RESULT.json` and pinned by `strict=True` `xfail` tests.

---

## [1.5.1] — 2026-10-06 — released

Patch release: an independent forensic audit of v1.5.0 verified the claimed state
against the code and fixed five confirmed discrepancies (D-095…D-098). No new
features; no account registration; no Telegram-limit bypass.

Released via a reviewed `develop → main` PR #12 (merge `f41ebc8`), tag `v1.5.1`;
the Release workflow (run `37453582161`) created the GitHub Release and attached
the Windows portable ZIP (24 796 203 bytes, sha256 `b46f9333…68dee`) + `.sha256`
(D-060). Gates: `pytest` **731 passed**, `ruff` clean, `vue-tsc` + `npm run build`
clean, Docker smoke clean (`/api/v1/consistency` → `pass`), artifact/secret scan
clean.

### Fixed
- **False capability.** `config_sync` reported `available` on an empty install
  although no sync implementation existed; `media_conversion` was listed with no
  ffmpeg/media tooling. A `Capability` now carries `implemented`; when `False`,
  `evaluate()` returns the new `not_implemented` state ("Не реализовано" / "Not
  implemented") regardless of context, and the flag travels through the API. The
  static auditor gained `check_capability_implementation()`, which fails CI if a
  capability claims `implemented=True` without a matching code signal (D-095).
- **Silent consistency failure.** `ConsistencyAuditor._runtime_findings()` and
  `run_static_checks()` used `except Exception: continue`, so a check that never
  ran looked like a pass. A raising check now produces an `error` finding
  `audit.check_failed.<name>` (D-096).
- **Write-only language preference.** The stored `language` setting and the i18n
  catalog were never consumed by the UI. `GET /api/v1/capability-graph` now
  resolves the saved preference (an explicit `language` query parameter still
  wins), and Settings gained a real RU/EN selector; the help store exposes
  `language` / `availableLanguages` (D-097).
- **Source-comparison checks on the runtime image.** The Docker smoke surfaced
  that the no-silent-failure runner (D-096) reported `overall: fail` in the
  runtime image because it ships no `frontend/`/`docs/` source. Those checks now
  report `audit.source_unavailable.<name>` as **info** and are skipped, so the
  Docker `/api/v1/consistency` report is `pass`; the dev checkout and CI still run
  every check fully (D-098).
- **Documentation drift.** `README.md` still said "Current stable release:
  `v1.4.0`"; updated to `v1.5.0`/`v1.5.1`.

### Tests
- `test_unimplemented_capabilities_are_never_available`,
  `test_capability_graph_language_follows_ui_preference` (`test_consistency.py`),
  `test_capabilities_have_implementations`,
  `test_auditor_never_swallows_a_failed_check`,
  `test_missing_source_tree_is_info_not_error`
  (`test_architecture_consistency.py`). Suite **731 passed**; `ruff` clean;
  `vue-tsc` + `npm run build` clean.

---

## [1.5.0] — 2026-10-05 — released

Minor release: a **capability graph**, a bilingual **i18n catalog** and a
**Consistency Auditor** (D-092…D-094). Three small, additive cross-cutting layers
that make the product explain itself honestly and catch cross-module drift in CI.
No new phases; no account registration; no Telegram-limit bypass.

Released via a reviewed `develop → main` PR #11 (merge `ad24bc6`), tag `v1.5.0`;
the Release workflow (run `37442056281`) created the GitHub Release and attached
the Windows portable ZIP + `.sha256` (D-060). Gates: `pytest` **726 passed**,
`ruff` clean, `vue-tsc` + `npm run build` clean, Docker smoke clean, artifact/secret
scan clean.

### Added — capability graph
- `services/capability_graph.py`: a machine-readable registry of every capability
  and its requirements; `context_from_db(session)` reads the real database state;
  `evaluate_all()` returns `available` / `partial` / `needs_setup` / `unavailable`
  with `satisfied`, `missing` and `missing_fixes`.
- `api/v1/capability_graph.py` + `api/schemas/capability.py`:
  `GET /api/v1/capability-graph`.
- The Promotion Wizard now embeds the evaluated graph (`WizardState.capabilities`),
  and the Dashboard shows a **"Что уже доступно"** overview — one source of truth
  for "is this ready?".

### Added — i18n
- `core/i18n.py`: one RU/EN catalog with `translate()`, `normalize_language()` and
  `missing_keys()`. Backend-produced user strings are single-sourced here.
- `services/ui_prefs.py`: a stored, non-secret `language` preference (default
  `ru`), exposed with `available_languages` on `/api/v1/help/prefs`.

### Added — Consistency Auditor
- `services/consistency_types.py`, `services/consistency_checks.py` (static
  checks: models↔migrations, frontend calls↔routes, job kinds↔handlers,
  routes↔views, real/fake providers, capability registry, i18n completeness, help
  topics, documented prefixes), `services/consistency.py` (runtime DB checks).
- `api/v1/consistency.py` + `api/schemas/consistency.py`: `GET /api/v1/consistency`.
- Diagnostics page gains a **"Проверка целостности"** panel (errors/warnings shown;
  low-confidence info behind a toggle). The report never contains secrets,
  sessions, phones or database rows.
- The static checks also run in `pytest`, so cross-module drift fails a pull
  request.

### Tests
- `tests/test_consistency.py`, `tests/test_architecture_consistency.py`,
  `tests/test_i18n.py`, plus capability assertions in `tests/test_product_api.py`.

---

## [1.4.0] — 2026-10-05 — released

Minor release: the **Notification Center**, the **TCMS Tray Agent** and the
**Editorial Workspace** (D-084…D-091). A durable, queryable history of important
events with per-category routing, quiet hours and anti-spam aggregation; a light
Windows tray supervisor so the portable app runs with no console window; and a
Telegram forum-supergroup editorial room where the owner, editors and moderators
work the same publication queue the Web UI shows. None of these features register
Telegram accounts or bypass Telegram limits.

Released via a reviewed `develop → main` PR #10 (merge `306672e`), tag `v1.4.0`; the Release workflow
created the GitHub Release and attached the Windows portable ZIP + `.sha256`
(D-060). Gates: `pytest` 702 passed, `ruff` clean, `vue-tsc` + `npm run build`
clean, migration up/down clean, artifact/secret scan clean.

### Added — Notification Center
- `db/models/notification.py`: `NotificationRecord` (category, priority,
  destination, event key, dedup key, message, how-to-fix, status, aggregate count,
  read flag) and `NotificationDelivery` (one attempt per destination). Additive
  migration `20261006_1000_e7a1c9d2f4b8` — an existing v1.3 database upgrades in
  place.
- `db/repositories/notifications.py`: record + delivery repositories (recent-by-
  dedup lookup, filtered history, status/category counts).
- `services/notification_service.py`: `NotificationCenterService` — category
  toggles, quiet hours (only non-urgent messages are postponed), anti-spam
  aggregation, per-category routing, delivery, history and a dashboard. A delivery
  problem never raises into the caller.
- `services/notification_destinations.py`: `TelegramDestination`,
  `WindowsToastDestination` (honest `unavailable`) and `RecordingDestination`.
- `api/v1/notifications.py` + `api/schemas/notification.py`: the
  `/api/v1/notifications/*` router; `api/deps.py::get_notification_service` reuses
  the manager bot (or a dedicated `notification_bot_id`).
- `manager/bus.py`: the new categories (`accounts`, `channels`, `content`,
  `media`, `updates`, `workers`), priorities and `category_for_module()`.
- `frontend/src/views/NotificationsView.vue` (`/notifications`) + nav link.

### Added — TCMS Tray Agent
- `tray/supervisor.py`: `BackendSupervisor` — hidden start, `/health` readiness,
  bounded restart backoff (5/hour), stop/status.
- `tray/agent.py`: `run_tray` (a `pystray` icon) and `_run_headless` (graceful
  fallback); `main(argv)` understands `--tray`/`--headless`/`--no-browser`.
- `tray/autostart.py`: a Startup-folder `.cmd` launcher (no admin).
- `tray/state.py`: a secret-free `data/tray.json` snapshot the backend reads.
- `portable/run.bat` starts the agent hidden and opens the browser only once
  `/health` answers; `services/diagnostics_service.py::_tray_item` surfaces the
  snapshot as a Diagnostics row.

### Added — Editorial Workspace
- `db/models/editorial.py`: `EditorialRoom`, `EditorialMember`, `EditorialItem`,
  `EditorialAuditEntry` (+ `DEFAULT_TOPICS`, `OPTIONAL_TOPICS`, `ROLE_ACTIONS`).
- `db/repositories/editorial.py`: room/member/item/audit repositories.
- `services/editorial_service.py`: `EditorialService` — rooms, an honest
  `check_room` (ready only after Telegram confirms the bot can send messages),
  topic creation, role-based permissions, the queue (`enqueue_item`, `move` with
  optimistic version, `reorder`, `assign`), card mirroring and `handle_callback`.
- `api/v1/editorial.py` + `api/schemas/editorial.py`: the `/api/v1/editorial/*`
  router; `api/deps.py::get_editorial_service` reuses the Content Studio
  `PostingService` as the publish handler (D-091).
- `providers/base.py` + `aiogram_bot.py` + `fake_bot.py`: forum-topic and inline
  callback methods; `manager/runtime.py` routes card callbacks into the service.
- `frontend/src/views/EditorialView.vue` (`/editorial`) + nav link.

### Tests
- `tests/test_notifications.py` (settings, quiet hours, aggregation, dashboard,
  delivery, toast-unavailable), `tests/test_editorial.py` (roles, honest rights,
  board, move + optimistic version, callback, audit), `tests/test_tray_agent.py`
  (supervisor backoff, snapshot, autostart, headless). Help topics
  `notification_center` / `editorial_workspace`.

### Docs / memory
- `docs/ARCHITECTURE.md` §19–§21, `docs/API.md`, `docs/UI.md` §11d/§11e,
  `docs/SETUP.md`, `docs/SECURITY.md` §7f–§7h, `docs/TROUBLESHOOTING.md`,
  `docs/ROADMAP.md`, `docs/RELEASE_CHECKLIST.md`, `README.md`;
  `agent/DECISIONS.md` D-084…D-091.

---

## [1.3.0] — 2026-10-05 — released

Minor release: the **Bot Factory** and the **LAN Mesh / offline control plane**
(D-077…D-082). Create a set of worker bots for the owner's own channels through
the official owner-confirmed @BotFather flow, and optionally join several of the
owner's computers on one local network with no cloud control plane. Neither
feature registers Telegram accounts or bypasses Telegram limits; Standalone (one
computer) stays the default.

Released via reviewed PR #9 (`develop → main`, merge `7788125`), tag `v1.3.0`;
the Release workflow created the GitHub Release and attached the Windows portable
ZIP + `.sha256` (D-060). Gates: `pytest` 664 passed, `ruff` clean, `vue-tsc` +
`npm run build` clean, migration up/down clean, Docker smoke and portable smoke
green, artifact/secret scan clean.

### Added — Bot Factory
- `db/models/bot_factory.py`: `BotBatch` (a named creation run) and
  `BotCandidate` (one planned bot). Additive migration
  `20261005_1600_d5b2e9c3f7a1` — an existing v1.2 database upgrades in place.
- `db/repositories/bot_factory.py`: batch + candidate repositories.
- `services/bot_factory.py`: `BotFactoryService` — templates, deterministic
  `generate_name` / `generate_username` / `sanitize_prefix` / `validate_username`,
  `check_availability` (a real Telegram check per candidate username), native
  creation, adopt, bind, write-only tokens and dashboards.
- `api/v1/bot_factory.py` + `api/schemas/bot_factory.py`: the
  `/api/v1/bot-factory/*` router; `api/deps.py::get_bot_factory_service` composes
  the existing `BotService` + `BindingService` (one manager bot; D-078).
- `providers/fake_session.py::FakeBotFactoryScenario`: deterministic, offline
  test double (D-001).
- `frontend/src/views/BotFactoryView.vue` (`/bot-factory`) + nav link.

### Added — LAN Mesh / offline control plane
- `db/models/mesh.py`: `MeshNode`, `MeshPeer` (credential stored as a salted
  hash), `PairingCode`, `MeshLease` (monotonic `fencing_token`).
- `db/repositories/mesh.py`: node / peer / pairing-code / lease repositories.
- `mesh/`: `identity`, `discovery`, `pairing`, `election`, `lease`, `capability`,
  `transport` (`MeshTransport` protocol + `HttpMeshTransport` + in-memory
  `RecordingTransport`) and `service` (`MeshService`).
- `api/v1/mesh.py` + `api/schemas/mesh.py`: the `/api/v1/mesh/*` router;
  `api/deps.py::get_mesh_service`.
- `scheduler/handlers.py`: the `mesh.tick` handler (probe peers, re-elect,
  reclaim expired leases) — a cheap no-op while the mesh is disabled.
- `main.py`: when the mesh is enabled and this node is not the coordinator, the
  manager-bot runtime does not start (no double-polling; D-081).
- `frontend/src/views/MeshView.vue` (`/mesh`) + nav link; `core/config.py` mesh
  settings (`mesh_enabled` off by default, `mesh_mode=standalone`).

### Security
- Mesh pairing never persists or returns anything derived from a secret: the peer
  `note` is now a plain status string and the shared secret is never stored
  (D-083).
- `/api/v1/mesh/ping` now authenticates the `X-Mesh-Secret` header (timing-safe)
  and rejects an unauthenticated request when a secret is configured (D-083).

### Changed
- Version strings bumped to `1.3.0` (`backend/app/__init__.py`, `pyproject.toml`,
  `frontend/package.json`, `frontend/package-lock.json`).
- Help topics `bot_factory` and `lan_mesh` added; `BotFactoryView` / `MeshView`
  now use them.

### Tests
- `tests/test_bot_factory.py` (service), `tests/test_bot_factory_api.py` (API),
  `tests/test_mesh.py` (algorithms + service), `tests/test_mesh_api.py` (API).
  All offline against the deterministic fakes (D-001).

---

## [1.2.0] — 2026-10-05 — released

Minor release: the **Content Studio** vertical slice (v1.2 content-studio
foundation). Collect material from sources, prepare it, and publish it to the
owner's own channels. Nothing is published without an explicit action; the AI
narrows, it never picks the emoji. No new phase; the roadmap (PHASE 0–11) stays
complete.

### Added — Content Studio backend
- `db/models/content.py`: `ContentSource`, `ContentItem`, `MediaAsset`,
  `Publication`, `ButtonSet`, `CommentPlan` (+ enums for source kind/status,
  rights status, item status, publication status). Additive migration
  `20261005_1200_c4a1f8b2e6d9` — an existing v1.1 database upgrades in place.
- `db/repositories/content.py`: one repository per model, with dedup lookups by
  source hash, source message id, content hash and media hash.
- `providers/content_base.py` + `providers/content_sources.py`:
  `ContentSourceProvider` protocol and Telegram / RSS / Atom / manual providers.
  Telegram reads through the existing `SessionProvider` and respects content
  protection (`noforwards` → keep only the link, D-006/D-074).
- `providers/posting_base.py` + `providers/posting.py`: `PostingProvider`
  protocol and the bot (`BotPostingProvider` over `TelegramBotProvider`) and user
  (`UserPostingProvider` over `SessionProvider`) implementations (D-071).
- `services/content_cleaner.py`: deterministic, explainable, cancellable cleaner.
- `services/content_markup.py`: `validate_markup`, `validate_buttons`,
  `render_preview` (Telegram-like preview).
- `services/content_service.py`: sources CRUD, `grab` (dedup + moderation),
  items, cleaner preview/apply/revert, rights + attribution, rewrite through the
  generative LLM backend only, moderation (blocked keywords + quiet hours),
  `release_held`, dashboard.
- `services/posting_service.py`: plan / schedule / calendar / buttons / publish
  (`uncertain` idempotency) / retry / auto-delete / first comments;
  `tick()` + `due_count()`.
- `scheduler/handlers.py`: the `content.posting` handler runs a bounded pass and
  re-schedules itself every `POSTING_TICK_SECONDS` (D-008 style, D-075);
  `main.py` seeds the first tick; `QueueService.ensure_periodic` added.
- `api/v1/content.py` + `api/schemas/content.py`: `/api/v1/content/*` router;
  `api/deps.py::get_posting_service` / `get_content_service`.

### Added — Content Studio UI
- `frontend/src/views/ContentStudioView.vue` (`/content`, nav «Content Studio»):
  four tabs — Обзор, Источники, Материалы, Календарь. RU-first; adds sources,
  grabs material, cleans, checks markup, previews, plans/schedules/publishes.
- `frontend/src/api/client.ts`: Content Studio types + methods.
- Help topics `content_studio`, `content_source`, `content_rights`.

### Changed
- Version strings read `1.2.0` (`backend/app/__init__.py`, `pyproject.toml`,
  `frontend/package.json` + lock).
- Docs (`ARCHITECTURE`, `API`, `UI`, `ROADMAP`) and agent memory updated.

### Tests
- `tests/test_content_posting.py`, `tests/test_content_posting_api.py` (posting
  engine, moderation, buttons, calendar, publishing API).
- Extended `tests/test_scheduler.py` (periodic tick + `ensure_periodic`),
  `tests/test_migrations.py` (v1.2 tables added in place), `tests/test_help.py`.
- Suite **611 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

---

## [1.1.0] — 2026-10-05 — released

Maintenance/minor release: optional per-account **network routes**, **donor
discovery**, a **lightweight local encoder**, the multi-format **Account Hub**
importer and the bot-only/risk UX. No new phase; every addition is opt-in and
never bypasses Telegram limits. Released from `develop` via reviewed PR #7
(`develop → main`, merge `3438305`), tag `v1.1.0`; the Release workflow attached
the Windows portable ZIP + `.sha256` (D-060).

### Added — Account Hub (local session import)
- `services/session_import.py`: one `SessionImportProvider` protocol covering
  Telethon `.session`, `.session` + companion JSON (whitelisted keys only),
  StringSession and (optional) Telegram Desktop TDATA. Local-only and
  owner-scoped; no search, download or bulk registration; never bypasses
  verification/FloodWait/privacy (D-070).
- `api/v1/sessions.py`: `POST /sessions/import/detect`,
  `POST /sessions/import/artifact`, `GET /sessions/{id}/risk`; schemas in
  `api/schemas/sessions.py`. `SessionsView.vue` gained the "Центр аккаунтов
  (импорт)" panel, format/state display, the sensitive-file warning and the
  "Риск ограничений" column.
- `.gitignore` also excludes `tdata/`, `*.session.json`, `*.session_meta.json`.

### Added — network routes (proxies)
- `db/models/proxy.py` (`ProxyProfile`, `ProxyKind`, `ProxyStatus`),
  `db/repositories/proxies.py`, `services/proxy_service.py`
  (`ProxyView`/`ProxyCheck` with `to_dict()`), `api/v1/proxies.py` +
  `api/schemas/proxies.py`: `/api/v1/proxies*` CRUD, honest reachability check
  and account binding. Passwords are sealed at rest and never returned; every
  response states that a route is not a limit bypass (D-065).
- `user_sessions.proxy_id`; `SessionsView.vue` gained a "Маршрут" column and a
  "Сетевые маршруты (прокси)" management card.

### Added — donor discovery
- `db/models/donor_candidate.py` (`DonorCandidate`),
  `db/repositories/proxies.py::DonorCandidateRepository`,
  `providers/discovery_base.py` + `providers/telegram_discovery.py`,
  `services/donor_discovery_service.py`, `api/v1/discovery.py` +
  `api/schemas/discovery.py`: search stores candidates only; adding a source is
  always an explicit click (D-066). `SourcesView.vue` gained an "Автопоиск
  доноров" panel with comparison.

### Added — lightweight local encoder
- `ai/encoder.py`; `MODE_ENCODER` in `ai/types.py`; the `auto` routing uses the
  encoder before the LLM; `source` can be `encoder`. No model file, no download
  (D-067). `AiView.vue` exposes the mode; `docs/API.md` documents it.
- `ai/backends/encoder_base.py` (`EncoderBackend` protocol) and
  `ai/backends/rubert.py` (optional `cointegrated/rubert-tiny2` embeddings;
  lazy, CPU-only, unload-when-idle, D-068). `services/encoder_service.py` +
  `/api/v1/ai/encoder/{status,install,check,remove}` provide the honest install
  experience (official files only, SHA-256 verified, gitignored `models/`).

### Added — reactions, analytics and wizard (bot-only UX)
- `services/reaction_intent.py`: intent → permitted emoji (narrowing only, never
  a choice); the planner intersects profile ∩ intent ∩ channel ∩ bot-compatible
  and skips with a reason (D-069).
- Analytics works without a user account and reports the missing-history note
  (`account_connected`/`account_note`); `AnalyticsView.vue` shows the "Режим без
  личного аккаунта" note.
- Promotion wizard is adaptive: `session_optional_note` without an account and
  `session_risk_note` with one; the invite-restriction warning is shown in the
  account card and the wizard (D-069).

### Changed
- Diagnostics: new `proxies` and `donor_candidates` subsystem rows; the redacted
  report gained `proxies` (host/kind/status only — never the password) and
  `donor_candidates` sections.
- `docs/API.md`, `docs/UI.md`, `docs/SETUP.md`, `docs/SECURITY.md`,
  `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `README.md`, `agent/*` updated to
  the factual v1.1.0 state. Version strings read `1.1.0` everywhere.
- Migration `20261004_2047_76d92fe3e70b_v1_1_account_hub_proxies_and_donor_`
  adds `proxy_profiles`, `donor_candidates` and `user_sessions.proxy_id`.
- Fixed a mojibake (cp775) corruption in `docs/API.md`.

### Tests
- New: `test_proxy_api.py`, `test_proxy_service.py`, `test_discovery_api.py`,
  `test_donor_discovery.py`, `test_encoder.py`, `test_encoder_service.py`,
  `test_session_import.py`, `test_reaction_planner.py`; extended
  `test_ai_api.py`, `test_ai_classifier.py`, `test_session_service.py` and
  `test_diagnostics.py` (including a proxy/candidate redaction test).
- Suite: **574 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

---

## [1.0.5] — 2026-10-04

Product-slice release: the suite becomes useful **without a user (MTProto)
account**, gains a first-run guide and a conservative updater. No new phase.

### Added — bot-only bindings & reaction capabilities
- `db/models/binding.py` (`BotChannelBinding`) + `db/repositories/bindings.py`;
  `services/binding_service.py` verifies real admin rights via the bot provider.
- `db/models/capability.py` (`ChannelCapabilities`) + `db/repositories/capabilities.py`;
  `services/capability_service.py` probes the channel's available reactions.
- `api/v1/bindings.py` + `api/schemas/bindings.py`: `/api/v1/bindings*` and
  `/api/v1/capabilities/*` (tokens never returned).
- `services/reaction_policy.py::intersect_reactions` + `reaction_planner` now
  honour the channel's confirmed emoji set, so a profile can never schedule an
  unsupported reaction.

### Added — invite campaigns (session-free)
- `db/models/campaign.py` (`InviteCampaign`, `InviteLink`, `JoinRequest`) +
  `db/repositories/campaigns.py`; `services/campaign_service.py` with conservative
  risk modes, invite-link create/revoke and join-request counters.
- `api/v1/campaigns.py` + `api/schemas/campaigns.py`: `/api/v1/campaigns*`.

### Added — donor quality
- `db/models/donor.py` (`DonorMetrics`) + `db/repositories/donors.py`;
  `services/donor_heuristics.py` + `services/donor_service.py` produce explainable
  quality bands; the bot-share estimate stays `null` when member data is missing.
- `GET/POST /api/v1/donors*`.

### Added — backup delivery destinations
- `db/models/backup_destination.py` + `db/repositories/destinations.py`;
  `services/destination_service.py` + `services/backup_backends/*` (local,
  Telegram, Google Drive, Яндекс.Диск). Credentials are sealed; a local
  destination is auto-created and cannot be deleted. Fixes backup delivery so the
  archive bytes (not raw DB bytes) reach every enabled destination.
- `POST /api/v1/backup/destinations*`.

### Added — first-run wizard & conservative auto-update
- `db/models/onboarding.py` + `services/promotion_service.py`: `/api/v1/promotion*`
  reflects real system state; session-gated steps become `optional` without a
  session.
- `db/models/update_state.py` + `services/update_service.py` + `core/versioning.py`:
  `/api/v1/update*` — off by default, checks GitHub releases and stages a
  SHA-256-verified file; never auto-installs.

### Added — Diagnostics
- New subsystem rows (`bindings`, `capabilities`, `backup_destinations`) and
  redacted-report sections (`queue`, `bindings`, `capabilities`, `campaigns`,
  `donors`, `backup_destinations`, `update`).

### Added — Frontend (RU-first)
- New `CampaignsView.vue` (`/campaigns`); a "Бот и реакции" column in
  `ChannelsView.vue`; backup **destinations** in `BackupView.vue`; the Setup
  Wizard + Update cards in `SystemView.vue`. New API types/methods in
  `api/client.ts`, routes + sidebar link in `App.vue`/`router.ts`.

### Added — Database
- One Alembic migration `7cb72d22d35b` ("product slice") for all new tables;
  autogenerate drift check is clean.

### Changed
- Version bumped to `1.0.5` (`backend/app/__init__.py`, `pyproject.toml`,
  `frontend/package.json` + lock). `updates/` is git-ignored and created by
  `scripts/build_portable.sh`.

### Tests
- `tests/test_bindings_api.py`, `tests/test_campaigns_api.py`,
  `tests/test_product_api.py`; `tests/test_diagnostics.py` extended for the new
  sections. Suite: **491 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

---

## [Unreleased] — documentation consistency pass

Maintenance only (no new features, no new phase). Documentation and persistent
memory brought back in line with the shipped v1.0.4 code after a factual audit.

### Documentation
- `docs/API.md` — the **Setup / System** table listed obsolete
  `/api/v1/system/backups*` and `/api/v1/system/config/*` paths that do not exist
  in the code; replaced with the real `/api/v1/system/database` and
  `/api/v1/system/database/upgrade` endpoints and a pointer to the
  `/api/v1/backup` section. Added the missing **Help / UI preferences**
  (`/api/v1/help/*`) section. Removed a stale duplicate **Invites** table that
  documented a non-existent `/api/v1/invites/{id}/start` endpoint.
- `docs/UI.md` — the "Built views" inventory was missing the `/diagnostics` and
  `/backup` routes; added them.
- `docs/SETUP.md` — the Setup Wizard check list named items that do not exist
  (Bot API, channel access, required permissions, frontend, scheduler) and
  omitted real ones; corrected to the actual checks returned by
  `GET /api/v1/system/setup`.
- `agent/CURRENT_STATE.md` — the `DECISIONS.md` range said D-001…D-037; corrected
  to D-001…D-062.

### Verified (no change needed)
- README, ROADMAP, RELEASE_CHECKLIST, SECURITY, TROUBLESHOOTING and ARCHITECTURE
  already match the code (version `1.0.4`, Diagnostics, Channel Registry, Alembic
  migrations, portable/Docker flows).
- Gates re-run green: `pytest` **462 passed**, `ruff` clean, `vue-tsc` +
  `npm run build` clean.

### Tests
- `tests/test_diagnostics.py::test_report_payload_contains_no_secrets_or_db_contents`
  — strengthened to seed an audience user record and assert the redacted report
  leaks no audience names, ids or full phone numbers (only status/aggregates).

---

## [1.0.4] — 2026-10-04

Released 2026-10-04 (merge `3f42c3d`, PR #5; tag `v1.0.4`; the Release workflow
built the Windows portable ZIP + `.sha256` and attached them — D-060).

Patch release: startup robustness and Diagnostics polish (no new phases, no new
large features).

### Fixed
- **A corrupt/unreadable database no longer crashes the app or the Diagnostics
  page.** The Diagnostics page is exactly where a user is sent when something is
  wrong, but it returned HTTP 500 when `data/app.db` was damaged — the very case
  it exists to explain. Every DB-backed check is now guarded and degrades to a
  friendly row, and the report falls back to safe empty sections; the database
  row reports «Файл базы данных повреждён или не является базой данных» with a
  concrete recovery step. Scheduler recovery is also guarded so a DB problem
  cannot abort application startup.
- **Queue page showed raw job values** (`invite.batch`, `reaction.job`, English
  statuses). It now shows plain Russian labels for kinds and statuses.

### Documentation
- `docs/TROUBLESHOOTING.md` — added a "database file is damaged" recovery entry
  (symptom / cause / what to do).
- `docs/ROADMAP.md` — corrected stale claims (Alembic is implemented, not
  deferred; PHASE 2 is complete).

### Tests
- `tests/test_diagnostics.py` — graceful degradation when a check or report
  section fails (corrupt DB).
- `tests/test_scheduler.py` — scheduler startup survives a failing recovery.
- Suite: **462 passed**; `ruff` clean; `vue-tsc` + `npm run build` clean.

---

## [1.0.3] — 2026-10-04

Released 2026-10-04 (merge `f18f53a`, tag `v1.0.3`; the Release workflow
built the Windows portable ZIP + `.sha256` and attached them — D-060).

Product polish: a **Diagnostics** page so a non-technical owner can understand the
system state and hand a developer a **redacted** report without reading logs.
No new phases, no new large features.

### Added
- **Diagnostics page** (Web UI → «Диагностика», `/diagnostics`) with one row per
  subsystem — application, database (migration state/revision), Telegram Bot API,
  manager bot, managed bots, user sessions, channels, audience, reactions,
  invites, AI, scheduler/queue, storage, portable runtime — each showing a plain
  status (`Готово` / `Внимание` / `Ошибка` / `Не настроено`), "что это значит"
  and "что делать". API: `GET /api/v1/diagnostics`.
- **Redacted diagnostic report** — `GET /api/v1/diagnostics/report?format=json|txt|zip`
  (+ `formats`). Contains version, OS/runtime, DB/migration state, enabled
  modules, Telegram/bot/session/channel statuses (status only, no contents), queue,
  AI, dependency versions, last errors and safe path names. It is redacted and
  re-scanned server-side (`core/redaction.py`); if the scan is not clean no file
  is produced. Response header `X-Diagnostics-Redacted: true`; the UI states
  "Отчёт безопасно очищен от секретов."
- **Safe maintenance actions** — `POST /api/v1/diagnostics/actions/{key}`:
  restart scheduler, recheck Telegram, recheck channels, clean up stuck local
  jobs. Never deletes user data; `cleanup_jobs` requires confirmation and is
  hidden while the scheduler runs.
- `backend/app/core/redaction.py` — reusable secret redaction + verification
  (tokens, api_hash/api_id, session strings, phones, key/value secrets, long
  hex/base64), with a safety `scan` that refuses to export a dirty payload.
- `backend/app/scheduler/handlers.py` — shared durable-queue handler registration
  (`register_handlers`) so the scheduler restart reuses identical wiring.
- Tests: `tests/test_diagnostics.py` (redaction, report generation in all three
  formats, absence of secrets/database contents, status aggregation, API, and
  non-destructive cleanup).

### Changed
- **Version string `1.0.3`** across `backend/app/__init__.py`, `pyproject.toml`,
  `frontend/package.json` + `package-lock.json`.
- **UI wording consistency**: the audience page title is now «Аудитория» (was
  «База участников»); the invites task list is «Задания» (was «Задачи»). One term
  per entity (see `docs/UI.md` §11).
- Docs updated to match reality: `README.md` (current stable release + feature
  list + status), `docs/API.md` (Diagnostics endpoints), `docs/UI.md`
  (Diagnostics + terminology), `docs/SETUP.md` (Diagnostics section),
  `docs/TROUBLESHOOTING.md` (start-here + symptom→cause→fix table),
  `docs/ROADMAP.md`, `docs/RELEASE_CHECKLIST.md`, and the `agent/` memory.

### Fixed
- `_KV_RE` in `core/redaction.py` no longer flags an already-redacted
  `key=***REDACTED***` value, so the safety scan does not reject its own output.

---

## [1.0.2] — 2026-10-04

Release-engineering patch: makes the **Windows portable release fully
automated**. No product/functional changes.

### Fixed
- **The Release workflow could not create a GitHub Release by itself.** It only
  ran `gh release upload`, which fails unless the Release already exists — so a
  fresh tag produced a green *build* but no published Release/artifact, requiring
  a manual fallback (as happened for `v1.0.1`). `.github/workflows/release.yml`
  now **creates the Release when missing** (`gh release create --verify-tag`,
  with generated notes) and otherwise updates the existing one, then attaches the
  ZIP + `.sha256`. A `v*` tag now yields a complete, reproducible release with no
  manual step.
- **Portable ZIP build for a relative output dir** (carried from `develop`,
  D-059): `scripts/build_portable.sh` resolves `OUT` to an absolute path against
  the caller's cwd, so the ZIP is written correctly when CI passes `dist/TCMS`.
  Covered by `test_build_portable_zip_with_relative_output`.

### Changed
- **Version string `1.0.2`** across `backend/app/__init__.py`, `pyproject.toml`,
  and `frontend/package.json` + `package-lock.json`. `v1.0.0`/`v1.0.1` and their
  tags stay immutable (D-050).

---

## [1.0.1] — 2026-10-04

Post-1.0 hardening release: versioned migrations, the shared Channel Registry,
per-channel analytics, CI, the Mini App setup helper, and reproducible
installable packaging. Published from `develop` via a reviewed `develop → main`
PR, tagged `v1.0.1`; the Windows portable ZIP is attached to the GitHub Release.

### Fixed
- **Portable ZIP build failed for a relative output dir (CI).** `build_portable.sh`
  built `ZIP_PATH` from the (possibly relative) output dir and then wrote it after
  `cd "$OUT"`, so `zip` targeted a non-existent `dist/TCMS/dist/...`. `OUT` is now
  resolved to an absolute path against the caller's cwd before use. Covered by
  `test_build_portable_zip_with_relative_output`.
- **Flaky `test_setup_requires_manager_bot` / "Event loop is closed".** Tests
  that iterated the FastAPI `get_session()` dependency with `break` leaked the
  async-generator session; SQLAlchemy/aiosqlite garbage-collected it on a later
  test's closed loop, intermittently failing `GeneratorExit`. `tests/conftest.py`
  now disposes the engine *before* `_isolated_env` resets it (teardown order),
  and the Mini App tests use the `session_scope()` context manager. Full suite
  is now stable: 427 passed across repeated runs, no event-loop-closed noise.

### Added
- **Reproducible, cross-platform portable packaging.** `scripts/build_win_runtime.py`
  stages a self-contained Windows CPython (official *embeddable* package + pinned
  `win_amd64` wheels from `scripts/win-requirements.lock`) extracted flat into
  `runtime/site-packages`; `pyaes` (sdist-only, pure Python) comes from its sdist,
  so no compiler is needed. `scripts/build_portable.sh` is now cross-platform,
  emits a versioned ZIP (`…-Windows-Portable-<version>.zip`) plus `.sha256`, and
  gained `--no-runtime` / `--no-zip` / `--no-frontend`. `scripts/fetch_embedded_python.sh`
  gained `--no-deps`. Tests: `tests/test_portable_smoke.py` (offline tree, ZIP
  layout, builder dry-runs).
- **Release workflow** (`.github/workflows/release.yml`): on a `v*` tag (or manual
  dispatch) it verifies (ruff + pytest + SPA build), builds the portable ZIP and
  attaches it (+ checksum) to the GitHub Release.
- **Versioned Alembic migrations** replace `create_all` at startup. Guarded runner
  (`backend/app/db/migrate.py`) handles fresh installs, existing `create_all`
  databases (adopt + stamp) and normal upgrades, with a pre-migration backup and
  transaction-per-migration. `alembic.ini` + `migrations/` (baseline autogenerated
  from the models); `docker/Dockerfile` and `scripts/build_portable.sh` ship them.
  DB check is migration-aware and `/api/v1/system/database` exposes status/upgrade.
  Docs: `docs/database-migrations.md`. Tests: `tests/test_migrations.py`.
- **Channel Registry** — one shared channel identity (`channels` table +
  `/api/v1/channels` + RU-first "Каналы" page). `Channel`/`ChannelKind`/
  `ChannelStatus`, repository, service (`normalize_reference`, verify, module
  toggles, default promotion) and API; verification reuses the permission probe
  and never bypasses Telegram limits. Invite jobs gained `channel_id` and resolve
  their target from the chosen registry channel. Tests: `tests/test_channels.py`.
- **Channel Registry wired into post ingestion and audience sources.** Ingesting a
  post (`POST /api/v1/reactions/posts`) accepts an optional `registry_channel_id`
  that fills the channel username (and numeric id when known) from the registry,
  and `posts` now stores `registry_channel_id`. Audience sources accept an
  optional `channel_id` that resolves the source reference from the registry, and
  `audience_sources` now stores `channel_id`. Both reject an unknown registry id
  with a friendly 404. Web UI: the audience source form and the reactions
  simulation/ingest panel gained a "channel from registry" picker. Migration
  `e3b5890e407e`; tests in `tests/test_channels.py`.
- **Channel Registry wired into the permission probe.** `POST /api/v1/permissions/check`
  accepts an optional `channel_id`; the target is resolved from the registry and
  `permission_checks.registry_channel_id` records the link, so a channel's probe
  history is retrievable per registry channel. `ChannelService.verify` links its
  probe to the channel. Web UI: the Sessions permission panel gained a registry
  channel picker. Migration `6816b29afc76`; tests in `tests/test_permission_service.py`.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): two jobs run on pushes and
  PRs to `main`/`develop` — backend (`ruff check backend tests` + `pytest`) and
  frontend (`npm ci` + `npm run build`). Added to the release checklist.
- **Mini App setup helper.** `POST /api/v1/miniapp/setup` validates a public
  HTTPS URL, registers it as the manager bot's Web App menu button (new
  `TelegramBotProvider.set_menu_button`, implemented by the aiogram and fake
  providers) and persists `miniapp_public_url` + `miniapp_enabled`. Settings has
  a "Мини-приложение Telegram" card with the URL field and a one-click button;
  invalid URLs and provider errors are reported in plain RU. Tests:
  `tests/test_miniapp_setup.py`.

- **Per-channel analytics.** Every analytics view (`/api/v1/analytics/*`) now
  accepts an optional `channel_id` that scopes posts, reactions, audience and
  invite metrics to one Channel Registry channel (posts by
  `registry_channel_id`, reactions/audience/invites via their existing links).
  Omitting it keeps the previous global aggregates. The Analytics page gained a
  channel selector defaulting to the registry's default channel. Tests:
  `tests/test_analytics_channels.py`.

### Changed
- **Release version `1.0.1`** (`backend/app/__init__.py`, `pyproject.toml`,
  `frontend/package.json` + lock) — already set on `develop`; documentation now
  matches (the changelog previously still read `1.0.0`). Health/system endpoints
  report `1.0.1`. `v1.0.0` and its tag stay immutable (D-050/D-057).
- **Runtime dependency is base `uvicorn`** (not `uvicorn[standard]`): the app uses
  no WebSockets and the default asyncio loop, so uvloop/httptools/watchfiles/
  websockets are dropped — smaller portable runtime, cross-buildable (D-056).
  `--reload` now needs `watchfiles` (documented).
- Invite preview/create accept an optional `channel_id` (target is derived from it).

### Fixed
- Vite `emptyOutDir` no longer deletes the tracked `backend/app/static/.gitkeep`
  on every build (a `frontend/public/.gitkeep` is re-emitted into the output).

---

## [1.0.0] — 2026-10-03

First production release: the complete PHASE 0–11 suite plus the RC and post-1.0
hardening passes. See `docs/RELEASE_CHECKLIST.md`.

### Added — Post-1.0 hardening: manager-bot runtime, notifications, permission probe
- **Manager-bot runtime** (`backend/app/manager/`): a single asyncio task
  (`ManagerBotRuntime`) short-polls the manager bot, dispatches an admin-only
  whitelist of plain-language RU commands (`/start`, `/status`, `/bots`,
  `/accounts`, `/queue`, `/reactions`, `/audience`, `/invites`, `/backup`), and
  forwards queued notifications. Off by default in tests
  (`MANAGER_RUNTIME_ENABLED`); backs off when Telegram is unreachable; never
  blocks the durable scheduler.
- **Notification bus** (`backend/app/manager/bus.py`): bounded, non-blocking,
  never-raising in-process queue. Six owner-toggleable categories
  (`system`, `telegram`, `reactions`, `audience`, `invites`, `ai`) mapped from
  event modules. `EventsService` forwards ERROR/CRITICAL automatically; lifecycle
  events (app start/stop, backup created, AI warnings) publish explicitly.
  Toggles reuse the existing `settings` table (no new table).
- **Permission probe** (`PermissionService` + `PermissionCheck` model/repo):
  checks channel resolvability, member visibility and invite rights for an
  account, returning an honest plain-language status (`ok`, `partial`,
  `no_access`, `auth_required`, `admin_required`, `privacy_restricted`,
  `flood_wait`, `error`). Never bypasses Telegram limits (D-006).
- **Provider extensions**: `TelegramBotProvider.get_managed_bots` /
  update+command support; `SessionProvider.invite_to_channel` / permission-probe
  stubs — implemented for the aiogram, Telethon and fake providers.
- **API**: `/api/v1/manager/status|notifications`, `/api/v1/permissions/*`.
- **Frontend**: permission-probe panel in `SessionsView.vue`; notification toggle
  panel in `SettingsView.vue`; manager-bot card in `SystemView.vue`; new types and
  methods in `api/client.ts`.
- **Tests**: `test_manager_bot.py` (26), `test_permission_service.py` (13),
  `test_hardening_api.py` (9); `conftest.py` gained `permission_client` /
  `manager_client` fixtures and disables the manager runtime in tests. Suite is
  now **413 passed**.

### Fixed — RC hardening
- **Reactions**: executed posts now use the same category reaction policy as
  simulation, so a real post can never get a forbidden emoji (e.g. 😍/🔥 on a
  donation post). `ReactionService.plan_post` rebuilt the plan match through
  `_result_to_match`/`_policy_for_category` (D-044).
- **Invites**: restart recovery now resets invite tasks that were claimed
  `RUNNING` when the process crashed back to `PENDING`, so an explicit resume can
  actually finish the run instead of hanging (`recover_stuck_running`, D-045).
- **Rules**: the default `news` rule excludes sad vocabulary, so a sad "новость"
  classifies as `sad` (😢/😭/❤️) instead of `news` (🎉/🔥) (D-046).
- **Frontend**: the Reactions page no longer shows the "system is off" help text
  while reactions are enabled; it now explains that reactions run automatically.
- **Config**: removed a duplicated `backup_dir` field in `Settings`.

### Tests
- Added regression tests for the reaction policy (execution), invite stuck-task
  recovery, and the sad-news default rule. Suite is now **336 passed**.

### Added — Frontend (post-roadmap polish)
- `frontend/src/views/SourcesView.vue` — audience source management: list,
  add, check, scan confirmation (preview) + live progress, pause/resume/cancel,
  enable/disable, delete, headline stats.
- `frontend/src/views/AudienceView.vue` — paginated audience base: search,
  source/tag/status filters, filter presets, sort + page size, bulk tag/status
  actions, tag manager, user detail, export/import.
- `frontend/src/api/client.ts` — audience/source types and methods.
- Router routes `/sources`, `/audience`; sidebar and Mini App bottom-nav entries.

### Added — Packaging (post-roadmap polish)
- `scripts/fetch_embedded_python.sh` — stages the official Windows embeddable
  Python into `runtime/`, writes the `pythonXY._pth`, bootstraps pip and installs
  dependencies into `runtime/site-packages`. Offline-friendly: `--dry-run` plans
  without network, `SKIP_RUNTIME=1` opts out, and clear manual steps are printed
  on failure.
- `scripts/build_portable.sh` — now fetches/stages the runtime by default
  (`--no-runtime` / `SKIP_RUNTIME=1` to opt out) and fixed the requirements path.
- `tests/test_portable_smoke.py` — added tests for the runtime fetcher (dry run,
  missing arg, skip env) that need no network.

### Changed — Docs
- `docs/UI.md` — audience/sources page documentation + running inventory.
- `docs/SETUP.md` — zero-setup portable build steps + manual fallback.
- `docs/ARCHITECTURE.md` — portable build stages the embedded runtime.
- `docs/ROADMAP.md` — post-roadmap polish section.

---

## [0.11.0] — 2026-10-03 — PHASE 11: VPS / Docker production configuration

### Added — Deployment
- `docker/docker-compose.proxy.yml` — optional TLS overlay running Caddy in front
  of the app (publishes 80/443, proxies to `app:8000`).
- `docker/Caddyfile` — Caddy site config with automatic Let's Encrypt
  certificates, gzip/zstd, security headers.

### Changed — Deployment
- `docker/docker-compose.yml` — `.env` is now optional (`required: false`), so
  `docker compose up` works with safe defaults; added notes on production env.
- `docs/SETUP.md` — full VPS/Docker walkthrough (prepare → run → HTTPS via Caddy
  or nginx → operations/backups), no separate "server version" (D-004).
- `docs/SECURITY.md` — VPS/Docker secret-handling specifics (root-only `.env`,
  non-root container, localhost-only binding, off-server backups).
- `docs/TROUBLESHOOTING.md` — Docker/VPS troubleshooting table.
- `docs/ARCHITECTURE.md` — §11 Docker/VPS subsection.

### Verified
- Multi-stage image builds; container serves `/health`, the SPA (`/` → 200), the
  deep health check, and creates a backup via `POST /api/v1/backup` on a mounted
  volume. Compose config (base and proxy overlay) validates.

---

## [0.10.0] — 2026-10-03 — PHASE 10: Portable Windows packaging + backup/restore

### Added — Backend
- `backend/app/services/backup_service.py` — `BackupService`:
  - `create_backup()` writes a single `.tcmsbak` zip (SQLite DB + `manifest.json`)
    with a unique filename; `backup_retention` prunes older files.
  - `list_backups()` / `delete_backup()` / `restore_backup()` — restore always
    writes a safety backup of the current state first.
  - `export_config()` / `import_config()` — JSON transfer of user-owned rows
    (`settings`, `reaction_profiles`, `reaction_rules`) only.
  - Path-traversal protection; sessions excluded unless explicitly requested.
- `backend/app/api/v1/backup.py` + `backend/app/api/schemas/backup.py` —
  `/api/v1/backup` (info, list, create, download, restore, delete) and
  `/api/v1/backup/config/{export,import}`. Friendly RU errors, no secrets.
- `backend/app/api/deps.py` — `get_backup_service`; router registered.
- `backend/app/core/config.py` — `backup_dir`, `backup_retention`,
  `backup_include_sessions`.
- `backend/app/core/paths.py` — `static_dir()` now resolved package-relative so
  code can live under `app/` in a portable build.

### Added — Frontend
- `frontend/src/views/BackupView.vue` (Резервные копии): plain-language help,
  create (with session opt-in + confirmation), list/download/restore/delete,
  configuration export/import. Route + sidebar link + API client methods/types.

### Added — Portable / tooling
- `portable/run.bat` (sets `TCMS_ROOT` + `PYTHONPATH`, creates `.env`, opens the
  browser), `portable/stop.bat` (graceful shutdown), `portable/README.txt`.
- `scripts/build_portable.sh` — assembles the portable tree.
- `tests/test_portable_smoke.py` — spawns the real app with `TCMS_ROOT` in a temp
  dir, asserts `/health`, runtime dirs, and a clean graceful shutdown.

### Tests
- `tests/test_backup_service.py` (9) and `tests/test_backup_api.py` (7). Full
  suite: **330 passed**. `ruff` clean. Frontend builds.

---

## [0.9.0] — 2026-10-03 — PHASE 9: Telegram Mini App (same SPA, one API)

### Added — Backend
- `backend/app/miniapp/` package:
  - `auth.py` — `verify_init_data()` verifies the Telegram `initData`
    HMAC-SHA256 signature (`HMAC_SHA256(bot_token, "WebAppData")`), rejects
    stale/future `auth_date`, and parses the Telegram user. Pure and
    unit-testable (no FastAPI/Telegram imports).
  - `sessions.py` — signed session tokens (`issue_session`/`verify_session`)
    using a key derived from `APP_SECRET_KEY` (`derive_key`); no JWT dependency.
  - `service.py` — `MiniAppService`: reads the sealed manager-bot token, applies
    the owner allow-list, issues sessions, and reports plain-language
    availability (`enabled`/`available`/`reason`/`how_to_fix`).
- `backend/app/api/schemas/miniapp.py` + `api/v1/miniapp.py`:
  `GET /api/v1/miniapp/config`, `POST /api/v1/miniapp/auth` (sets an `HttpOnly`
  session cookie), `GET /api/v1/miniapp/me`, `POST /api/v1/miniapp/logout`.
- Setup Wizard `miniapp` check (`SystemService.miniapp_check`) and
  `get_miniapp_service` dependency.
- Settings: `miniapp_enabled` (off by default), `miniapp_initdata_max_age`,
  `miniapp_session_ttl`, `miniapp_public_url` (env + `.env.example`).
  `miniapp_enabled` and `miniapp_public_url` are DB-overridable.

### Added — Frontend
- `src/telegram.ts` — typed wrapper over the Telegram WebApp SDK (`isTelegramMiniApp`,
  `initTelegramWebApp`).
- `src/stores/miniapp.ts` — Pinia store that bootstraps auth only when
  `initData` is present; inert in a normal browser.
- `App.vue` — friendly loading/error gate inside Telegram; mobile bottom
  navigation (Панель, Боты, Реакции, Очередь, Аналитика, Система, Настройки);
  shows the signed-in user.
- `index.html` — loads the official Telegram WebApp SDK (inert outside Telegram);
  `viewport-fit=cover` for safe areas.
- Mini App types + client methods in `api/client.ts`; responsive + Telegram dark
  theme styles in `styles.css`.

### Tests
- `tests/test_miniapp_auth.py` — valid/tampered/wrong-token/expired/missing
  `initData`, and session issue/verify/expiry/tamper.
- `tests/test_miniapp_api.py` — config/auth/me/logout round-trip, non-owner
  rejection, and a no-secret/no-`initData`-leak assertion. 313 passed total;
  `ruff` clean; SPA builds.

---

## [0.8.0] — 2026-10-03 — PHASE 8: Analytics (content, reactions, audience)

### Added — Backend
- `backend/app/db/repositories/analytics.py` (`AnalyticsRepository`): read-only
  aggregate queries over posts, reaction jobs, audience sources/users/links and
  invite tasks, with portable Python-side per-day bucketing.
- `backend/app/services/analytics_service.py` (`AnalyticsService`): `content()`,
  `reactions()`, `audience()` and `overview()`; RU plain-language summaries,
  percent-change vs. the previous window, titled category/source/status counts.
- `backend/app/api/schemas/analytics.py` + `api/v1/analytics.py`:
  `GET /api/v1/analytics/overview|content|reactions|audience?days=1..365`.
- Registered the analytics router; added `get_analytics_service` dependency.

### Added — Frontend
- `AnalyticsView.vue` (period switch, headline metrics, charts, category/emoji
  bars, audience status, source effectiveness) + `/analytics` route and nav link.
- Dependency-free `Sparkline.vue` and `BarList.vue` inline-SVG chart components.
- Dashboard now shows a "Что показывают цифры" block with the backend summary and
  two sparklines, linking to the full Analytics page.
- Analytics types + client methods in `api/client.ts`; analytics UI styles.

### Tests
- `tests/test_analytics_service.py` (content/reactions/audience/overview, empty
  DB, day clamping, percent-change helpers) and `tests/test_analytics_api.py`
  (all four endpoints, `days` validation, no secret/PII leak). 294 passed total;
  `ruff` clean; SPA builds.

### Decisions
- D-036 (read-only aggregate analytics + backend-owned plain-language summaries),
  D-037 (dependency-free inline-SVG charts).

---

## [0.7.0] — 2026-10-03 — PHASE 7: Tiny AI classifier (rules-first, optional)

### Added — Backend
- `backend/app/ai/` package: `types.py` (`Classifier` Protocol,
  `ClassificationResult`, `ClassificationContext`, `Tone`, source/mode
  vocabularies), `errors.py` (friendly, non-leaking AI errors), `schema.py`
  (strict JSON contract parsing), `classifiers.py` (`RulesClassifier`,
  `LlmClassifier`, `FakeClassifier`), `router.py` (`RoutingClassifier`,
  `RoutingOutcome`, `category_title`), `inference.py` (single-worker bounded
  executor, `run_bounded`), `backends/` (`base.py`, `fake.py`, `llama_cpp.py`,
  registry `build_backend`).
- `backend/app/db/models/ai.py` (`AiMetric`, `AiRecord`) + `repositories/ai.py`
  (`AiRepository`: metrics counters, recent records, trim).
- `backend/app/services/ai_service.py` (`AiService`: effective config, status,
  model list/check/load/unload, routing, metrics/history, events) and
  `ai_help.py` (plain-language setting help, `human_size`).
- `backend/app/api/schemas/ai.py` + `api/v1/ai.py` (status, overview, settings
  GET/PUT, classify, test, models, model check/load/unload, metrics, history),
  registered in `v1/router.py`.
- `Settings` — full AI block (enabled, backend, model path, models dir, threads,
  context, temperature, max tokens, timeout, keep-loaded, both thresholds,
  history limit); `resolve_models_dir()`; `paths.models_dir()`.
- `ReactionService` now classifies through the AI router; `simulate`/`ingest_post`
  accept a mode; Setup Wizard reports an `ai` check.
- `main.py` lifespan now shuts down the AI inference executor on exit.

### Added — Frontend
- `frontend/src/views/AiView.vue` (Обзор / Модель / Настройки / Проверка /
  Диагностика) + AI types/methods in `api/client.ts`, `/ai` route, sidebar link
  «Мини-ИИ». Simulation result types extended with AI fields.

### Added — Tests
- `tests/test_ai_classifier.py` (schema, classifiers, routing policy, inference
  bounds) and `tests/test_ai_api.py` (status/overview/settings/classify/models/
  metrics/history, reaction simulation AI fields, setup check). **281 tests pass;
  `ruff check backend tests` clean.**

### Notes
- The Rules Engine remains the deterministic default. AI is opt-in, consulted only
  when rules are unsure, never picks emoji, and always degrades gracefully
  (D-031…D-035). Models are user-provided `.gguf` assets (gitignored, never
  auto-downloaded).

---

## [0.6.1] — 2026-10-03 — Second GitHub sync (PHASE 4–6 to `develop`)

### Changed
- Pushed PHASE 4–6 to `origin/develop` (`92d94e4`…`3ddc299`) as a fast-forward;
  no force push, no history rewrite.
- `origin/develop` HEAD is now `3ddc299`; `develop` is 0 ahead / 0 behind.
- PR **#1** (`develop → main`) auto-updated to head `3ddc299`; left **open** and
  **unmerged**.

### Verified
- Pre-push secret audit: no `.env`, real tokens, `api_hash` values, `.session`
  files, database files, audience exports or private-data logs are tracked or
  present in the pushed diff; mutable runtime dirs carry only `.gitkeep`.
- `main` was not touched.

_No functional changes in this sync._

---

## [0.6.0] — 2026-10-03 — PHASE 6: Invite Manager

### Added — DB
- `backend/app/db/models/invite.py` — `InviteJob` (target, account/source
  selection, filter snapshot, status, counters, confirmation, `wait_until`) and
  `InviteTask` (per-user status, attempts, scheduled/completed, `wait_until`,
  error); `InviteJobStatus`, `InviteStatus`, `TERMINAL_INVITE_STATUSES`.
- `backend/app/db/repositories/invites.py` — `InviteJobRepository` (CRUD, list,
  active, count_by_status), `InviteTaskRepository` (listing, status counts,
  `claim_batch`, `pending_count`, `unfinished_count`, `next_due`, `retry_failed`).

### Added — service
- `backend/app/services/invite_service.py` — `InviteService`: `preview` (dry-run
  summary), `create_job` (draft + task planning, per-account randomized spacing),
  `confirm_and_start`, `start/pause/resume/stop`, `retry_failed`, `run_tick`
  (bounded durable batch, returns `done`/`more`/`paused`), `recover`, `summary`,
  `explain_job`. FloodWait pauses the run + records the wait; privacy/admin become
  per-user statuses; transient network errors stay pending.

### Added — API + setup
- `backend/app/api/schemas/invites.py`, `backend/app/api/v1/invites.py` —
  preview, summary, list, create, detail, confirm, pause/resume/stop, retry,
  tasks. Friendly envelope; no secret leaks.
- `api/deps.py::get_invite_service`; router registered in `v1/router.py`.
- `main.py` lifespan — `InviteService.recover()` (pauses interrupted runs) and the
  `invite.batch` durable job handler (re-schedules while work remains).
- `services/system_service.py` — new Setup-Wizard `invites` check (plain language).
- `providers/errors.py` / `fake_session.py` / `telethon_session.py` — invite error
  coverage (`ChatAdminRequiredError`, `AlreadyParticipantError` mapping, fake
  `FakeInviteScenario`).
- `core/config.py` — invite settings (`invite_delay_min/max`, `invite_batch_size`,
  `invite_max_total`, `invite_max_per_account`).

### Added — frontend
- `frontend/src/views/InvitesView.vue` — build a run (target, accounts, filters,
  limits, dry-run) → preview summary → create draft → confirm/start → monitor with
  per-status counters and task table; pause/resume/stop/retry. Invite types +
  methods in `api/client.ts`; `/invites` route; sidebar «Приглашения».

### Tests
- `tests/test_invite_service.py`, `tests/test_invite_api.py`; `conftest.py` gained
  an `invite_client` fixture. Suite: **238 passed**; `ruff check backend tests`
  clean.

---

## [0.5.0] — 2026-10-03 — PHASE 5: Audience (sources, parsing, database, export)

### Added — provider abstraction (Telethon stays isolated)
- `backend/app/providers/audience_base.py` — `AudienceProvider` protocol
  (`resolve_entity`, `iter_participant_pages`).
- `backend/app/providers/session_audience.py` — `SessionAudienceProvider`, a thin
  adapter over the PHASE 4 `SessionProvider` (no Telethon import here).
- `backend/app/providers/fake_audience.py` — pure `FakeAudienceProvider` +
  `FakeAudienceScenario` (deterministic paging, hidden participants, injectable
  FloodWait/privacy errors). `fake_session.py` gained `FakeAudienceScenario` +
  `make_fake_users` and participant-page support.
- `providers/registry.py` — `build_audience_provider(...)`; new audience errors
  (`EntityNotFoundError`, `PrivacyRestrictedError`, `ChatAdminRequiredError`) and
  extended DTOs (`EntityRef.participants_count/hidden`, `ParticipantPage`).

### Added — DB
- `backend/app/db/models/audience.py` — `AudienceSource`, `AudienceUser`,
  `SourceUserLink` (+ `SourceType`, `ScanStatus`, `Completeness`, `MemberStatus`);
  dedup via unique `telegram_user_id`, membership via unique `(source_id, user_id)`.
- `backend/app/db/repositories/audience.py` — source/user/link repositories
  (filters, search, sort, pagination, batch streaming, counts, bulk tag ops).
- `backend/app/db/session.py` — Unicode-aware SQLite `lower`/`upper` so
  case-insensitive Cyrillic search works.

### Added — service & API
- `backend/app/services/audience_service.py` — `AudienceService`: sources CRUD,
  `check_source`, `preview_scan` (dry-run), chunked durable scanning with per-chunk
  commits, honest completeness, pause/resume/cancel, `recover()`, tags, explainable
  scoring, dashboard/statistics, streaming CSV/JSON export, CSV/JSON import.
- `backend/app/api/schemas/audience.py`, `backend/app/api/v1/audience.py`,
  `api/deps.py`, router registration. Responses never leak secrets/raw phones; PII
  export is off by default and gated by the `AUDIENCE_STORE_PII` setting.
- `backend/app/services/system_service.py` — Setup-Wizard `audience` check.
- `backend/app/main.py` — registered the `audience.scan` durable job handler and
  best-effort `AudienceService.recover()` (interrupted scans → paused).

### Added — tests
- `tests/test_audience_models.py`, `test_audience_service.py`,
  `test_audience_api.py`, `test_audience_providers.py`,
  `test_audience_security.py`; `conftest.py` gained an `audience_client` fixture.

### Fixed
- Empty final scan page no longer misreported as `NO_ACCESS`.
- Enum-name normalization in repository counts so status tallies are correct.

### Notes
- Suite: **212 passed**; `ruff check backend tests` clean.
- Dedicated Audience/Sources frontend views deferred to the frontend rollout.

---

## [0.4.0] — 2026-10-03 — PHASE 4: User Session Manager (MTProto accounts)

### Added — provider abstraction (Telethon isolated)
- `backend/app/providers/session_base.py` — `SessionProvider` protocol (send_code,
  sign_in, sign_in_password, get_me, health, export_session, resolve_entity,
  get_participants, invite_to_channel, aclose) mirroring `TelegramBotProvider`.
- `backend/app/providers/telethon_session.py` — the **only** module that imports
  Telethon; lazy per-operation connect/disconnect; friendly translation of
  Telethon errors (FloodWait, code/password invalid/expired, api credentials,
  phone banned/invalid, session invalid).
- `backend/app/providers/fake_session.py` — deterministic `FakeSessionProvider` +
  `FakeAuthScenario` for tests and offline mode (no network).
- `providers/registry.py` — `build_session_provider(...)`; new user-account
  errors/DTOs in `providers/errors.py` and `providers/types.py`.

### Added — DB & service
- `db/models/session.py` — `UserSession` + `SessionStatus` enum (online,
  auth_required, disconnected, flood_wait, error, disabled); registered in
  `db/models/__init__.py`.
- `db/repositories/sessions.py` — `SessionRepository` (list/count/by-status/
  by-telegram-id/delete).
- `services/session_service.py` — `SessionService`: durable guided auth wizard
  (api_id/hash + phone → code → optional 2FA), `.session` import with rollback,
  health checks, enable/disable, delete (+ file removal), logout/re-auth,
  `recover()` for interrupted flows. Secrets sealed via `core.security`; full
  phone stored sealed, only masked form in plaintext.

### Added — API & Setup Wizard
- `api/schemas/sessions.py` + `api/v1/sessions.py`:
  `GET /sessions`, `/sessions/summary`, `/sessions/{id}`,
  `POST /sessions/auth/start`, `/sessions/{id}/code`, `/sessions/{id}/password`,
  `/sessions/import`, `/sessions/{id}/health`, `/enable`, `/disable`, `/logout`,
  `DELETE /sessions/{id}`. Responses never contain api_hash, session contents or
  the full phone number (only `phone_masked` + `has_*` booleans).
- `system_service.py` — new Setup-Wizard checks `telethon`, `sessions_dir`,
  `accounts` (plain-language, with "what to do").
- `main.py` lifespan — best-effort `SessionService.recover()` on startup.

### Added — Frontend
- `SessionsView.vue` — guided wizard (API ID/Hash → phone → code → 2FA),
  `.session` import, account list with owner/health/last-check, check/enable/
  disable/re-auth/delete actions, plain-language hints.
- Route `/sessions`, sidebar link «Аккаунты», Dashboard accounts card; new API
  types/methods in `api/client.ts`.

### Added — Tests
- `test_fake_session_provider.py`, `test_session_service.py`,
  `test_sessions_api.py`, `test_session_security.py` (auth flows incl. 2FA,
  import + rollback, health, enable/disable, delete, logout, restart recovery,
  secret redaction, secret-never-leaked-in-API). Total suite: **153 passed**.

### Notes
- `requirements.txt` adds `telethon` (installed 1.45.0).
- No functional change to PHASE 1–3 behaviour; all prior tests stay green.

---

## [0.3.1] — 2026-10-03 — First GitHub sync (develop branch + PR)

### Added / Changed
- Pushed the full local history (PHASE 0–3, commits `0daa91b`…`f06ba53`) to the
  remote branch **`develop`** — the first sync with
  `github.com/Surimat/Telegram-Channel-Management-Suite`.
- Opened PR **#1** (`develop → main`); **not merged** (requires owner confirmation).
- `main` was intentionally left untouched (no direct push, no history rewrite, no
  force push).
- Fixed the local `origin` fetch refspec (`+refs/heads/*:refs/remotes/origin/*`)
  so all remote branches are tracked.
- Pre-push secret audit confirmed: `.env`, `data/*.db`, session files, tokens and
  portable runtimes are git-ignored and absent from the remote; mutable runtime
  dirs contain only `.gitkeep`.
- Documentation/persistent memory updated: development now proceeds on `develop`;
  `agent/CURRENT_STATE.md` gained a "GitHub sync & branching" section.

_No functional changes in this sync._

---

## [0.3.0] — 2026-10-03 — PHASE 3: Reaction Manager (rules, planner, scheduling, UI)

### Added — Rules Engine (deterministic, editable)
- `backend/app/rules/engine.py` — `RulesEngine`, `Category` (9 categories),
  `RuleSpec`, `RuleMatch`; keyword/phrase/regex matching with exclusions,
  `min_confidence`, priority, language gate, and `manual_override` (always wins).
  Confidence is a transparent matched-terms score; unknown text → `neutral`.
- `backend/app/rules/delays.py` — `DelayPreset` (`early`/`normal`/`spread`),
  `scaled_window`, `distribution_for`, `UniformDelay`.
- `backend/app/rules/defaults.py` — `default_rule_specs()`: the seed RU+EN rule
  set (donation/news/funny/sad/angry/cute/support/announcement) with
  allowed/preferred/forbidden reactions.

### Added — Data model & repositories
- `db/models/post.py` — `Post` (`text`, `category`, `confidence`,
  `classification_source`, `status`, `channel_id`, `telegram_message_id`, …).
- `db/models/reaction.py` — `ReactionProfile`, `ReactionRule`, `ReactionJob`
  (+ `ReactionJobStatus`); job stores `post_id`, `bot_id`, `reaction`,
  `scheduled_at`, `status`, `attempts`, `error`, `completed_at`, `queue_job_id`.
- `db/repositories/posts.py`, `db/repositories/reactions.py` (profiles, rules
  incl. `clear_defaults`, jobs incl. `for_post`).

### Added — Planner & service (vertical slice)
- `services/reaction_planner.py` — pure `ReactionPlanner` with injectable RNG:
  participation gate, skip gate, weighted emoji choice, per-bot delay from the
  profile window/preset, `max_bots_per_post` cap, one reaction per bot/message.
- `services/reaction_service.py` — `ReactionService`: profile CRUD + validation,
  rule CRUD + seeding, `resolve_profile`, `_classify` (DB rules w/ default
  fallback), `simulate` (no Telegram), `ingest_post`/`plan_post` (durable jobs),
  `execute_reaction_job` (via provider; FloodWait never bypassed), `recover`,
  global enable/disable, `stats`.
- `providers/types.py`/`base.py`/`fake_bot.py`/`aiogram_bot.py` — added
  `set_reaction`; the fake records `(chat_id, message_id, emoji)` deterministically
  and can be told to fail per emoji.

### Added — Scheduling
- `scheduler/scheduler.py` — handlers now receive `(session, job)` so a handler
  runs in the scheduler's own transaction (fixes a nested-session SQLite deadlock
  on slow/weak machines).
- `main.py` — registers the `reaction.job` handler; seeds default rules and a
  default profile; recovers interrupted reaction jobs on startup.

### Added — API
- `api/schemas/reactions.py`, `api/v1/reactions.py` — profiles/rules/posts/jobs,
  `simulate`, `status`, `enable`/`disable`, `categories`; `api/deps.py` gained
  `get_reaction_service`; router registered in `v1/router.py`.
- `services/system_service.py` — new `reactions` Setup-Wizard check with
  plain-language meaning + hint.

### Added — Frontend
- `views/ReactionsView.vue` — tabs: Обзор (global switch + counters), Профили
  (editor with sliders/tooltips), Правила (full editor incl. allowed/forbidden
  reactions), Симуляция (preview table + "ingest & plan"), Очередь (status
  filter). Reaction types/methods in `api/client.ts`, `/reactions` route, nav
  link, and a Reactions card on the Dashboard.

### Added — Tests (48 new; suite 60 → 108)
- `tests/test_rules_engine.py`, `tests/test_delays.py`,
  `tests/test_reaction_planner.py`, `tests/test_reaction_service.py`,
  `tests/test_reactions_api.py` — including fake-provider execution, FloodWait
  handling, restart recovery, determinism, and an end-to-end scheduler→provider
  test. `ruff check backend tests` clean.

### Changed
- `tests/test_scheduler.py` updated for the `(session, job)` handler signature.

---

## [0.2.0] — 2026-10-03 — PHASE 2: Telegram foundation (manager/managed bots)

### Added — Telegram provider layer (D-001, D-019)
- `providers/base.py` — `TelegramBotProvider` Protocol: `get_me`, `get_bot`,
  `send_message`, `get_managed_bots`, `get_managed_bot_token`,
  `replace_managed_bot_token`, `get/set_managed_bot_access_settings`, `close`.
- `providers/fake_bot.py` — `FakeTelegramBotProvider` (deterministic, no network).
- `providers/aiogram_bot.py` — `AiogramBotProvider` (the only aiogram importer;
  wraps the official managed-bot methods; translates exceptions).
- `providers/errors.py` / `types.py` — friendly, library-agnostic error types and
  DTOs; `providers/registry.py` — `build_bot_provider` from config.

### Added — Bots vertical slice (DB → service → API → UI)
- `db/models/bot.py` (`Bot`, `BotKind`, `BotHealth`), `db/repositories/bots.py`.
- `services/bot_service.py` — add/validate/seal, enable/disable/remove,
  `health_check`, `ensure_manager_bot`, managed-bot register/token/replace,
  `manager_link`, `summary`.
- `api/deps.py`, `api/schemas/bots.py`, `api/v1/bots.py` — bot inventory +
  managed-bot endpoints; tokens are never returned (only `has_token`).
- `ApiError` (message + actionable hint) in `api/errors.py`.
- Setup Wizard: DB-backed `manager_bot` + `managed_bots` checks in
  `/api/v1/system/{status,setup}` and `/health/deep`.
- `main.py` lifespan registers the manager bot from settings (best-effort).

### Added — Security
- Bot tokens **sealed at rest** with Fernet keyed from `APP_SECRET_KEY`
  (`core/security.py::seal_secret/open_secret`) — D-017.

### Added — Frontend
- `views/BotsView.vue` (inventory, health, enable/disable, add, managed-bot
  workflow), bot types/methods in `api/client.ts`, `/bots` route + nav link, and
  a Telegram summary card on the Dashboard.

### Added — Tests
- `tests/test_providers.py`, `tests/test_bot_service.py`, `tests/test_bots_api.py`
  and a `bot_client` fixture overriding the provider factory with the fake.
- Suite: **60 passed**; `ruff check backend tests` clean.

---

## [0.1.0] — 2026-10-03 — PHASE 1: application skeleton (runnable)

### Added — Backend
- `backend/app/main.py` FastAPI app factory + lifespan (starts/stops the
  scheduler, initialises the DB, mounts the built SPA); `/health`, `/health/deep`.
- `core/`: `paths.py` (predictable runtime dirs via `TCMS_ROOT`), `config.py`
  (pydantic-settings + `SecretStr`), `logging.py` (structured logging + secret
  redaction filter), `security.py` (secret-key validation, key derivation, HMAC).
- `db/`: declarative base + naming convention, async engine/session, models
  (`Setting`, `Event`, `Job`), repositories (`settings`, `events`, `jobs`).
- `services/`: `settings_service`, `events_service` (log/error center),
  `queue_service`, `system_service` (Setup Wizard checks with plain-language
  "what it means / how to fix").
- `api/`: uniform error envelope + handlers (no stack traces to clients),
  schemas, and v1 routers `system`, `settings`, `events`, `queue`.
- `scheduler/`: durable asyncio scheduler that recovers unfinished jobs on start,
  claims due jobs, runs registered handlers, and records failures as events.
- `providers/`: package + contracts placeholder (implementations in PHASE 2).

### Added — Frontend
- Vue 3 + Vite + TypeScript SPA: app shell with sidebar, router, typed API
  client, Pinia store, RU-first styles; views Dashboard, System (Setup Wizard
  table), Settings, Logs, Queue, NotFound.
- Build outputs to `backend/app/static/` (served by FastAPI; no Node in prod).

### Added — Ops / packaging
- `backend/requirements.txt`, `backend/requirements-dev.txt`.
- `scripts/run_dev.sh`, `scripts/build_frontend.sh`.
- `portable/run.bat`, `portable/stop.bat` (skeleton; full packaging PHASE 10).
- `docker/Dockerfile` (multi-stage Node→Python, non-root),
  `docker/docker-compose.yml`, root `.dockerignore`.
- `pyproject.toml` (ruff), `pytest.ini`.

### Added — Tests
- config, logging-redaction, database/queue/events, scheduler, and API tests
  with isolated temporary SQLite databases. **31 tests pass; ruff clean.**

### Changed
- Dropped APScheduler from runtime requirements in favour of the minimal asyncio
  scheduler (see D-015). Anchored the AI-models `.gitignore` rule to `/models/`
  so backend source packages are no longer accidentally ignored.

### Security
- Secret redaction filter masks registered secrets in all log output.
- Settings API returns masked values for secrets; errors never expose internals.

---

## [0.0.1] — 2026-10-03 — PHASE 0: audit, architecture, persistent memory

### Added
- Repository audit (repo was empty except a stub README).
- `docs/ARCHITECTURE.md` — architecture, stack, provider abstraction, data model,
  reliability principles, deployment targets, security model.
- `docs/ROADMAP.md` — PHASE 0–11 plan.
- `docs/SETUP.md` — local / Windows portable / VPS-Docker setup.
- `docs/SECURITY.md` — secret & limits policy, checklists.
- `docs/UI.md` — UI/UX principles, section map, Setup Wizard UX.
- `docs/API.md` — REST API contract.
- `docs/TROUBLESHOOTING.md` — plain-language fixes + recovery guide.
- `agent/CURRENT_STATE.md`, `agent/NEXT_TASK.md`, `agent/DECISIONS.md` (D-001…D-014),
  `agent/CHANGELOG.md`.
- `.gitignore` protecting secrets, session files, data, logs, backups, models.
- `.env.example` — annotated configuration template.
- Directory skeleton: `backend/`, `frontend/`, `tests/`, `scripts/`, `docker/`,
  `portable/`, `data/`, `sessions/`, `backups/`, `logs/`, `exports/`.

### Notes
- No application code yet; repository intentionally starts with architecture and
  memory first, per the project brief.
