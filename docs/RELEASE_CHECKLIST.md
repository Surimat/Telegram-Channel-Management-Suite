# RELEASE CHECKLIST — Telegram Channel Management Suite

Use this checklist before tagging a release. All commands run from the
repository root unless stated otherwise.

## 1. Code quality gates (must pass)

```bash
python -m pytest                 # full suite — must be green (no failures/errors)
ruff check backend tests         # must be clean
cd frontend && npx vue-tsc --noEmit && npm run build   # typecheck + SPA build
PYTHONPATH=. python tests/meta_audit/engine.py         # regenerate META_AUDIT_RESULT.json (D-102)
```

- [ ] `pytest` green, no failures/errors.
- [ ] `ruff check backend tests` clean.
- [ ] `vue-tsc --noEmit` clean.
- [ ] `npm run build` succeeds (outputs to `backend/app/static/`).
- [ ] Working tree is clean after the build (no untracked build artifacts;
      `backend/app/static/.gitkeep` still present — see the `public/.gitkeep`
      note below).
- [ ] GitHub Actions **CI** (`.github/workflows/ci.yml`) is green on the PR head
      (backend: ruff + pytest; frontend: `npm ci` + `npm run build`).

## 2. Packaging / deployment gates

- [ ] **Portable**: `scripts/build_portable.sh` (cross-platform) stages an
      embedded Windows CPython via `scripts/build_win_runtime.py` from the pinned
      `scripts/win-requirements.lock`, and writes a versioned ZIP + `.sha256`.
      Smoke tests: `tests/test_portable_smoke.py` (startup, offline tree, ZIP
      layout, builder dry-runs).
- [ ] **Docker**: `docker build -f docker/Dockerfile -t tcms .` succeeds;
      `docker compose -f docker/docker-compose.yml up` serves `/health` and the
      SPA. (Skip honestly if Docker is unavailable in the environment.)

## 3. Security gates

- [ ] `git status` shows no `.env`, `*.session`, `data/*.db`, or token files.
- [ ] Secret scan of the diff/staged changes finds no real tokens, api_hash
      values, session strings, passwords or exported PII.
- [ ] The Diagnostics report passes the redaction scan (tests in
      `tests/test_diagnostics.py`); the exported JSON/TXT/ZIP contains no secret
      or database content.
- [ ] Logging redaction verified (secrets never reach console/logs/UI/API).
- [ ] Backup/export config excludes `bots` and `user_sessions`.
- [ ] Telegram FloodWait / privacy / admin limits are never bypassed.

## 4. Persistent memory (must match reality)

- [ ] `agent/CURRENT_STATE.md` reflects the release commit and phase.
- [ ] `agent/NEXT_TASK.md` points at the next real task.
- [ ] `agent/DECISIONS.md` includes any new locked decisions.
- [ ] `agent/CHANGELOG.md` has an entry for the release.
- [ ] `docs/ROADMAP.md`, `README.md`, `docs/*` describe the shipped features.

## 5. Git / GitHub gates

- [ ] `develop` is pushed and in sync with `origin/develop` (no force, no
      history rewrite).
- [ ] PR `develop → main` is `mergeable` and merged.
- [ ] `main` is synced back into `develop` (`git fetch --all --prune`).
- [ ] Tag `vX.Y.Z` created on the merged `main` commit.
- [ ] GitHub Release `vX.Y.Z` published with notes; the **Release** workflow
      (`.github/workflows/release.yml`) attaches the Windows portable ZIP +
      `.sha256` to it — no manual step (D-060).

## 6. Release verification (fill in per release)

### v1.6.0 (Owner Auth + Config Sync, 2026-10-07)

| Gate | v1.6.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.6.0` everywhere) | ✅ | app / pyproject / frontend / lock (guarded by `test_repo_version_is_consistent`) |
| Owner Auth | ✅ | local profile, PBKDF2 verifier, signed token, default-on middleware, local-first (D-105) |
| Config Sync | ✅ | versioned AES-256-GCM bundle, secret denylist, conflict detection, local + Google Drive app-data (D-106) |
| No secret in bundle | ✅ | `FORBIDDEN_KEY_MARKERS` + `scan_for_secrets`; sessions/TDATA/DB never synced |
| Consistency Auditor | ✅ | section `5b-2` guards providers + bundle anchors |
| Meta-audit engine (runtime) | ✅ | 25 total, 25 detected, 0 missed, **100.0%**, 0 false positives, 0 critical/high |
| Tests (`pytest` / `ruff`) | ✅ | 822 passed; ruff clean |
| Frontend build | ✅ | `vue-tsc` + `npm run build` clean |
| Artifact scan | ✅ | no `.session`/TDATA/DB/model in the ZIP; runtime dirs empty |

### v1.5.4 (auditor gaps N + O + P closed, 2026-10-06)

| Gate | v1.5.4 | Notes |
| --- | --- | --- |
| Version consistency (`1.5.4` everywhere) | ✅ | app / pyproject / frontend / lock (guarded by `test_repo_version_is_consistent`) |
| Meta-audit engine (runtime) | ✅ | kill rate **computed from executions** — 25 total, 25 detected, 0 missed, **100.0%**, 0 false positives, 0 critical/high (D-102/D-104) |
| Gap N closed | ✅ | `check_unused_model_columns` — an ORM column no module reads/writes is `db.unused_column.<module>.<Class>.<name>` (info) |
| Gap O closed | ✅ | `check_orphan_service_classes` — a public service class no module references is `dead.service.<module>.<Class>` (info) |
| Gap P closed | ✅ | `check_frontend_unwired_controls` — a Vue handler with no defined function is `frontend.control_unwired.<name>` (warning) |
| Precision controls | ✅ | `NC6_used_db_column`, `NC7_referenced_service`, `NC8_wired_frontend_control` (no false positives) |
| `KNOWN_GAP_IDS` empty | ✅ | every recorded auditor gap is closed and detected at runtime |
| Tests (`pytest` / `ruff`) | ✅ | 800 passed; ruff clean |
| Frontend build | ✅ | `vue-tsc` + `npm run build` clean |
| CI job `meta-audit` | ✅ | engine + tests + leak assertion; uploads `agent/META_AUDIT_RESULT.json` (no hardcoded percentage) |
| Git merge (`develop → main`) | ✅ | reviewed PR (`develop → main`) |
| Automated Release workflow + ZIP/`.sha256` | ✅ | tag `v1.5.4` → Release workflow (D-060) |
| Artifact scan | ✅ | no `.session`/TDATA/DB/model in the ZIP; runtime dirs empty |

### v1.5.3 (auditor gaps M + Q closed, 2026-10-06)

| Gate | v1.5.3 | Notes |
| --- | --- | --- |
| Version consistency (`1.5.3` everywhere) | ✅ | app / pyproject / frontend / lock (guarded by `test_repo_version_is_consistent`) |
| Meta-audit engine (runtime) | ✅ | kill rate **computed from executions** — 25 total, 22 detected, 3 missed, **88.0%**, 0 false positives, 0 critical/high (D-102/D-103) |
| Gap M closed | ✅ | `check_write_only_settings` — a setting written with no reader is `settings.write_only.<key>` |
| Gap Q closed | ✅ | `check_channel_registry_usage` — a channel-aware module without a canonical link is `channel-aware.module.<module>` |
| Precision controls | ✅ | `NC4_setting_with_reader`, `NC5_channel_aware_with_registry` (no false positives) |
| Runtime allow-list honest | ✅ | `_known_setting_keys()` drops `sync_enabled`/`owner_*` (no module consumes them) |
| Tests (`pytest` / `ruff`) | ✅ | 787 passed; ruff clean |
| Frontend build | ✅ | `vue-tsc` + `npm run build` clean |
| Docker smoke | ✅ | `/health` → `1.5.3`, SPA `200`, `/api/v1/consistency` → `pass` (0 error, 0 warning, 6 info); image runtime dirs empty, no `.session`/DB/model |
| CI job `meta-audit` | ✅ | engine + tests + leak assertion; uploads `agent/META_AUDIT_RESULT.json` (no hardcoded percentage) |
| Git merge (`develop → main`) | ✅ | reviewed PR (`develop → main`) |
| Automated Release workflow + ZIP/`.sha256` | ✅ | tag `v1.5.3` → Release workflow (D-060) |
| Artifact scan | ✅ | no `.session`/TDATA/DB/model in the ZIP; runtime dirs empty |

### v1.5.2 (audit-the-auditor meta-audit, 2026-10-06)

| Gate | v1.5.2 | Notes |
| --- | --- | --- |
| Version consistency (`1.5.2` everywhere) | ✅ | app / pyproject / frontend / lock (guarded by `test_repo_version_is_consistent`) |
| Meta-audit engine (runtime) | ✅ | `tests/meta_audit/engine.py` + `mutations.py`; kill rate **computed from executions** — 25 total, 20 detected, 5 missed, **80.0%**, 0 false positives, 0 critical (D-102) |
| Silent-failure guard | ✅ | raising check → `audit.check_failed.<name>` error; missing source → `audit.source_unavailable.<name>` info |
| New static checks | ✅ | router registration, backup-destination provider, notification routing, hardcoded UI strings |
| Capability anchors + dependency | ✅ | strong `CAPABILITY_SERVICE_ANCHORS`; `evaluate()` blocks an unimplemented dependency |
| Real defect fixed | ✅ | `_check_channel_aware` column mismatch (`ContentSource.channel_id`) |
| README release line | ✅ | updated to `v1.5.2` (guarded by `test_readme_states_the_current_release`) |
| Tests (`pytest` / `ruff`) | ✅ | green; ruff clean |
| Frontend build | ✅ | `vue-tsc` + `npm run build` clean |
| Docker smoke | ✅ | `/health` → `1.5.2`, SPA `200`, `/api/v1/consistency` → `pass` (0 error, 0 warning, 6 info) |
| CI job `meta-audit` | ✅ | runs the engine + tests + leak assertion, uploads `agent/META_AUDIT_RESULT.json` (no hardcoded percentage) |
| Git merge (`develop → main`) | ✅ | reviewed PR #13 (`develop → main`, merge `523c089`) |
| CI green on `develop` head | ✅ | run `37463801697` (push) + `37463867108` (PR) — backend/frontend/meta-audit |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.5.2` tag → run `37464579513` (D-060) |
| GitHub Release `v1.5.2` published | ✅ | tag matches (`523c089`) |
| ZIP attached | ✅ | `…-1.5.2.zip` (24 799 763 bytes) |
| `.sha256` attached | ✅ | `ee8562ef…9ed03`, local checksum matches |
| Artifact scan | ✅ | ZIP has no `.session`/TDATA/DB/model (only public `certifi/cacert.pem`); runtime dirs (`sessions/`, `data/`, `backups/`, `logs/`, `exports/`, `models/`, `updates/`) empty; only placeholder `.env.example` |

### v1.5.1 (forensic-audit fixes, 2026-10-06)

| Gate | v1.5.1 | Notes |
| --- | --- | --- |
| Version consistency (`1.5.1` everywhere) | ✅ | app / pyproject / frontend / lock |
| Capability honesty | ✅ | `config_sync` + `media_conversion` → `not_implemented`; `implemented` flag through the API; `check_capability_implementation` |
| Auditor no-silent-failure | ✅ | a raising check → `audit.check_failed.<name>` error finding (static + runtime) |
| Runtime-image source checks | ✅ | missing `frontend/`/`docs/` → `audit.source_unavailable.<name>` **info** (not error); Docker report `pass` |
| i18n preference consumed | ✅ | capability graph honours the saved `language`; Settings RU/EN selector |
| Doc drift | ✅ | `README.md` release line updated |
| Tests (`pytest` / `ruff`) | ✅ | 731 passed; ruff clean |
| Frontend build | ✅ | `vue-tsc` + `npm run build` clean |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/TDATA/DB/models in tree |
| Docker (`/health` + SPA + routes) | ✅ | `/health` → `1.5.1`, SPA `200`, `/api/v1/capability-graph` → `not_implemented`, `/api/v1/consistency` → `pass` |
| Git merge (`develop → main`) | ✅ | reviewed PR #12 (`develop → main`, merge `f41ebc8`) |
| CI green on `develop` head | ✅ | runs `37453055448` + `37453075808` (backend + frontend) |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.5.1` tag → CI release, run `37453582161` (D-060) |
| GitHub Release `v1.5.1` published | ✅ | tag matches (`f41ebc8`) |
| ZIP attached | ✅ | `…-1.5.1.zip` (24 796 203 bytes) |
| `.sha256` attached | ✅ | `b46f9333…68dee`, local checksum matches |
| Docker smoke | ✅ | `/health` → `1.5.1`, SPA `200`, `/api/v1/capability-graph` → `not_implemented`, `/api/v1/consistency` → `pass` |
| Artifact scan | ✅ | ZIP has no `.session`/TDATA/DB/model (only the public `certifi/cacert.pem`); runtime dirs (`sessions/`, `data/`, `backups/`, `logs/`, `exports/`, `models/`, `updates/`) empty; only placeholder `.env.example` |

### v1.5.0 (released 2026-10-05)

| Gate | v1.5.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.5.0` everywhere) | ✅ | app / pyproject / frontend / lock |
| Capability graph tests | ✅ | `test_consistency.py`; `GET /api/v1/capability-graph`; wizard `capabilities` asserted in `test_product_api.py` |
| Consistency Auditor tests | ✅ | `test_consistency.py`, `test_architecture_consistency.py` (static drift checks run in pytest) |
| i18n tests | ✅ | `test_i18n.py` (catalog complete, `translate`, `normalize_language`) |
| Migration test | ✅ | no new migration (additive, no schema change); existing up/down clean |
| Help topics | ✅ | no new help topics; `help/prefs` now carries `language` + `available_languages` |
| Frontend build | ✅ | `vue-tsc` + `npm run build` (Dashboard "Что уже доступно" + Diagnostics "Проверка целостности") |
| Tests (`pytest` / `ruff`) | ✅ | 726 passed; ruff clean |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/TDATA/DB/models in tree; consistency report secret-free |
| Docker (`/health` + SPA + v1.5 routes) | ✅ | `/health` → `1.5.0`, SPA `200`, `/api/v1/capability-graph` + `/api/v1/consistency` + `/api/v1/help/prefs` → `200` |
| Git merge (`develop → main`) | ✅ | reviewed PR #11 (`develop → main`, merge `ad24bc6`) |
| CI green on `develop` head | ✅ | run `37440895107` (backend + frontend) |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.5.0` tag → release created by CI, run `37442056281` (D-060) |
| GitHub Release `v1.5.0` published | ✅ | tag matches (`ad24bc6`) |
| ZIP attached | ✅ | Windows portable ZIP (24.8 MB) |
| `.sha256` attached | ✅ | `…-1.5.0.zip.sha256` (`a35484fd…b1f35`), local checksum matches |
| Docker smoke | ✅ | build + run: `/health` → `1.5.0`, SPA `200`, v1.5 routes `200` |
| Artifact scan | ✅ | ZIP has no `.session`/TDATA/DB/model; runtime dirs (`sessions/`, `data/`, `backups/`, `logs/`, `exports/`, `models/`, `updates/`) empty; only placeholder `.env.example` |

### v1.4.0 (released 2026-10-05)

| Gate | v1.4.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.4.0` everywhere) | ✅ | app / pyproject / frontend |
| Notification Center tests | ✅ | `test_notifications.py` (settings, quiet hours, aggregation, dashboard, delivery, toast-unavailable) |
| Editorial Workspace tests | ✅ | `test_editorial.py` (roles, rights, board, move + optimistic version, callback, audit) |
| Tray Agent tests | ✅ | `test_tray_agent.py` (supervisor backoff, snapshot, autostart, headless) |
| Migration upgrade test | ✅ | `e7a1c9d2f4b8`; `up`/`down` clean, additive with server defaults; model↔migration parity checked |
| Help topics | ✅ | `notification_center`, `editorial_workspace` in the catalog |
| Frontend build | ✅ | `vue-tsc` + `npm run build` (Editorial + Notifications pages bundled) |
| Tests (`pytest` / `ruff`) | ✅ | 702 passed; ruff clean |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/TDATA/DB/models in tree; tray snapshot secret-free; notification history secret-free |
| Docker (`/health` + SPA + v1.4 routes) | ✅ | v1.4 routes served by the same SPA/API |
| Git merge (`develop → main`) | ✅ | reviewed PR #10 (`develop → main`, merge `306672e`) |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.4.0` tag → release created by CI, run `37432367573` (D-060) |
| GitHub Release `v1.4.0` published | ✅ | tag matches (`306672e`) |
| ZIP attached | ✅ | Windows portable ZIP (24.8 MB), checksum verified |
| `.sha256` attached | ✅ | `Telegram-Channel-Management-Suite-Windows-Portable-1.4.0.zip.sha256` (`81d7fa35…08ee230`) |
| Docker smoke | ✅ | build + run: `/health` → `1.4.0`, SPA `200`, `/api/v1/notifications/settings` + `/api/v1/editorial/rooms` → `200` |
| Artifact scan | ✅ | ZIP has no `.session`/TDATA/DB/model; runtime dirs empty; only placeholder `.env.example` |

### v1.3.0 (released 2026-10-05)

| Gate | v1.3.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.3.0` everywhere) | ✅ | app / pyproject / frontend (+ lock) |
| Bot Factory tests | ✅ | `test_bot_factory.py`, `test_bot_factory_api.py` |
| LAN Mesh tests | ✅ | `test_mesh.py` (algorithms + service), `test_mesh_api.py` (API) |
| Mesh secret hardening | ✅ | pairing note leaks no secret; `/mesh/ping` authenticates `X-Mesh-Secret` (D-083) |
| Help topics | ✅ | `bot_factory`, `lan_mesh` required by `test_help.py` |
| Migration upgrade test | ✅ | `d5b2e9c3f7a1`; `up`/`down` clean, additive with server defaults |
| Frontend build | ✅ | `vue-tsc` + `npm run build` (Bot Factory + Mesh pages bundled) |
| Tests (`pytest` / `ruff`) | ✅ | 664 passed; ruff clean |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/DB/models in tree; runtime dirs empty |
| Docker (`/health` + SPA + v1.3 routes) | ✅ | v1.3 routes served by the same SPA/API |
| Git merge (`develop → main`) | ✅ | reviewed PR #9 (`develop → main`, merge `7788125`) |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.3.0` tag → release created by CI, run `37373384249` (D-060) |
| GitHub Release `v1.3.0` published | ✅ | tag matches |
| ZIP attached | ✅ | Windows portable ZIP (24.7 MB), checksum verified |
| `.sha256` attached | ✅ | `Telegram-Channel-Management-Suite-Windows-Portable-1.3.0.zip.sha256` |

### v1.2.0 (released 2026-10-05)

| Gate | v1.2.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.2.0` everywhere) | ✅ | app / pyproject / frontend (+ lock) |
| Content Studio tests | ✅ | `test_content_posting.py`, `test_content_posting_api.py`; extended `test_content_service.py`, `test_content_api.py` |
| Posting tick tests | ✅ | `test_scheduler.py`: periodic re-schedule + `ensure_periodic` idempotency |
| Migration upgrade test | ✅ | `test_migrations.py`: v1.2 tables added in place with server defaults |
| Help topics | ✅ | `content_studio`, `content_source`, `content_rights` required by `test_help.py` |
| Frontend build | ✅ | `vue-tsc` + `npm run build` (Content Studio page bundled) |
| Tests (`pytest` / `ruff`) | ✅ | 611 passed; ruff clean |
| Git merge (`develop → main`) | ✅ | merge commit `ea6c161` (PR #8) |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` (run `37349699248`) |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.2.0` tag → release created by CI (run `37350246513`) |
| GitHub Release `v1.2.0` published | ✅ | tag matches |
| ZIP attached | ✅ | Windows portable ZIP (~24.7 MB) |
| `.sha256` attached | ✅ | `Telegram-Channel-Management-Suite-Windows-Portable-1.2.0.zip.sha256` |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/DB/models in tree; runtime dirs empty |
| Docker (`/health` + SPA + v1.2 routes) | ✅ | build + run verified locally in prior releases; v1.2 routes served by the same SPA/API |

### v1.1.0 (released 2026-10-05)

| Gate | v1.1.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.1.0` everywhere) | ✅ | app / pyproject / frontend (+ lock) |
| New API tests | ✅ | `test_proxy_api.py`, `test_proxy_service.py`, `test_discovery_api.py`, `test_donor_discovery.py`, `test_encoder.py`, `test_encoder_service.py`, `test_session_import.py`, `test_reaction_planner.py` |
| Session-import security tests | ✅ | StringSession never returned/logged; companion-JSON whitelist; TDATA `NOT AVAILABLE` |
| Diagnostics tests (`test_diagnostics.py`) | ✅ | new `proxies`/`donor_candidates` rows + report sections + redaction |
| Migration drift check | ✅ | `20261004_2047_76d92fe3e70b` (+ `9a1c2f4b7d30`, `b3d7e1a5c9f2`); `compare_metadata` = none |
| Frontend build | ✅ | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | ✅ | 574 passed; ruff clean |
| Git merge (`develop → main`) | ✅ | merge commit `3438305` (PR #7) |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` |
| Automated Release workflow + ZIP/`.sha256` | ✅ | `v1.1.0` tag → release created by CI |
| GitHub Release `v1.1.0` published | ✅ | tag matches |
| ZIP attached | ✅ | Windows portable ZIP (~24.6 MB) |
| `.sha256` attached + matches ZIP | ✅ | `sha256sum -c` |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/DB/models in ZIP; empty runtime dirs |
| Docker (`/health` + SPA + v1.1 routes) | ✅ | build + run + restart verified |

### v1.0.5 (released 2026-10-04)

| Gate | v1.0.5 | Notes |
| --- | --- | --- |
| Git merge (`develop → main`) | ✅ | merge commit `496598f` (PR #6) |
| Version consistency (`1.0.5` everywhere) | ✅ | app / pyproject / frontend (+ lock) |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` |
| Diagnostics tests (`test_diagnostics.py`) | ✅ | redaction + report + new sections + degradation |
| New API tests | ✅ | `test_bindings_api.py`, `test_campaigns_api.py`, `test_product_api.py` |
| Migration drift check | ✅ | `7cb72d22d35b`; `compare_metadata` = none |
| Automated Release workflow | ✅ | `v1.0.5` tag → release created by CI |
| GitHub Release `v1.0.5` published | ✅ | tag matches |
| ZIP attached | ✅ | Windows portable ZIP |
| `.sha256` attached + matches ZIP | ✅ | `sha256sum -c` |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/DB; empty runtime dirs |
| Docker (`/health` + SPA) | ✅ | build + run + restart verified |
| Frontend build | ✅ | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | ✅ | 491 passed |

### Prior release — v1.0.4

| Gate | v1.0.4 | Notes |
| --- | --- | --- |
| Git merge (`develop → main`) | ✅ | merge commit `3f42c3d` (PR #5) |
| Version consistency (`1.0.4` everywhere) | ✅ | app / pyproject / frontend (+ lock) |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` |
| Diagnostics tests (`test_diagnostics.py`) | ✅ | redaction + report + API + degradation |
| Automated Release workflow | ✅ | `v1.0.4` tag → release created by CI |
| GitHub Release `v1.0.4` published | ✅ | tag matches |
| ZIP attached | ✅ | ~24 MB Windows portable ZIP |
| `.sha256` attached + matches ZIP | ✅ | `sha256sum -c` OK |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/DB; empty runtime dirs |
| Docker (`/health` + SPA) | ✅ | build + run + restart verified |
| Frontend build | ✅ | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | ✅ | 462 passed |

### Prior release — v1.0.3

| Gate | v1.0.3 | Notes |
| --- | --- | --- |
| Git merge (`develop → main`) | ✅ | merge commit `f18f53a` (PR #4) |
| Version consistency (`1.0.3` everywhere) | ✅ | app / pyproject / frontend |
| CI green on `develop` head | ✅ | `.github/workflows/ci.yml` |
| Diagnostics tests (`test_diagnostics.py`) | ✅ | redaction + report + API |
| Automated Release workflow | ✅ | `v1.0.3` tag → release created by CI |
| GitHub Release `v1.0.3` published | ✅ | tag matches |
| ZIP attached | ✅ | ~24 MB Windows portable ZIP |
| `.sha256` attached + matches ZIP | ✅ | `sha256sum -c` |
| Security (artifact + git tree clean) | ✅ | no secrets/sessions/DB; empty runtime dirs |
| Docker (`/health` + SPA) | ✅ | verified post-release on `develop` |
| Frontend build | ✅ | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | ✅ | 447 passed at release; 462 after maintenance |

## Known non-blocking items (documented, do not block a release)

- Manager-bot runtime polls only while the app is running (no webhook by
  default) — acceptable for local/portable use.
- Mini App BotFather registration + public HTTPS URL are the owner's deployment
  steps (documented in `docs/SETUP.md`); the Mini App is off by default.
- If the Release workflow's portable job fails (e.g. a packaging path bug), the
  tag stays immutable (D-050): fix forward on `develop` for the next release and,
  if the current release needs the artifact, build it from the tag
  (`git worktree add --detach <dir> vX.Y.Z` -> `scripts/build_portable.sh`) and
  attach the ZIP + `.sha256` to the Release manually. Do **not** move the tag.
- `PytestUnhandledThreadExceptionWarning` can appear from the aiosqlite worker
  thread on teardown in `test_hardening_api.py`; the run still passes.
