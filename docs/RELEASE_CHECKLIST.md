# RELEASE CHECKLIST ÔÇö Telegram Channel Management Suite

Use this checklist before tagging a release. All commands run from the
repository root unless stated otherwise.

## 1. Code quality gates (must pass)

```bash
python -m pytest                 # full suite ÔÇö currently 611 passed
ruff check backend tests         # must be clean
cd frontend && npx vue-tsc --noEmit && npm run build   # typecheck + SPA build
```

- [ ] `pytest` green, no failures/errors.
- [ ] `ruff check backend tests` clean.
- [ ] `vue-tsc --noEmit` clean.
- [ ] `npm run build` succeeds (outputs to `backend/app/static/`).
- [ ] Working tree is clean after the build (no untracked build artifacts;
      `backend/app/static/.gitkeep` still present ÔÇö see the `public/.gitkeep`
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
- [ ] PR `develop Ôćĺ main` is `mergeable` and merged.
- [ ] `main` is synced back into `develop` (`git fetch --all --prune`).
- [ ] Tag `vX.Y.Z` created on the merged `main` commit.
- [ ] GitHub Release `vX.Y.Z` published with notes; the **Release** workflow
      (`.github/workflows/release.yml`) attaches the Windows portable ZIP +
      `.sha256` to it ÔÇö no manual step (D-060).

## 6. Release verification (fill in per release)

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
| Version consistency (`1.2.0` everywhere) | Ôťů | app / pyproject / frontend (+ lock) |
| Content Studio tests | Ôťů | `test_content_posting.py`, `test_content_posting_api.py`; extended `test_content_service.py`, `test_content_api.py` |
| Posting tick tests | Ôťů | `test_scheduler.py`: periodic re-schedule + `ensure_periodic` idempotency |
| Migration upgrade test | Ôťů | `test_migrations.py`: v1.2 tables added in place with server defaults |
| Help topics | Ôťů | `content_studio`, `content_source`, `content_rights` required by `test_help.py` |
| Frontend build | Ôťů | `vue-tsc` + `npm run build` (Content Studio page bundled) |
| Tests (`pytest` / `ruff`) | Ôťů | 611 passed; ruff clean |
| Git merge (`develop Ôćĺ main`) | Ôťů | merge commit `ea6c161` (PR #8) |
| CI green on `develop` head | Ôťů | `.github/workflows/ci.yml` (run `37349699248`) |
| Automated Release workflow + ZIP/`.sha256` | Ôťů | `v1.2.0` tag Ôćĺ release created by CI (run `37350246513`) |
| GitHub Release `v1.2.0` published | Ôťů | tag matches |
| ZIP attached | Ôťů | Windows portable ZIP (~24.7 MB) |
| `.sha256` attached | Ôťů | `Telegram-Channel-Management-Suite-Windows-Portable-1.2.0.zip.sha256` |
| Security (artifact + git tree clean) | Ôťů | no secrets/sessions/DB/models in tree; runtime dirs empty |
| Docker (`/health` + SPA + v1.2 routes) | Ôťů | build + run verified locally in prior releases; v1.2 routes served by the same SPA/API |

### v1.1.0 (released 2026-10-05)

| Gate | v1.1.0 | Notes |
| --- | --- | --- |
| Version consistency (`1.1.0` everywhere) | Ôťů | app / pyproject / frontend (+ lock) |
| New API tests | Ôťů | `test_proxy_api.py`, `test_proxy_service.py`, `test_discovery_api.py`, `test_donor_discovery.py`, `test_encoder.py`, `test_encoder_service.py`, `test_session_import.py`, `test_reaction_planner.py` |
| Session-import security tests | Ôťů | StringSession never returned/logged; companion-JSON whitelist; TDATA `NOT AVAILABLE` |
| Diagnostics tests (`test_diagnostics.py`) | Ôťů | new `proxies`/`donor_candidates` rows + report sections + redaction |
| Migration drift check | Ôťů | `20261004_2047_76d92fe3e70b` (+ `9a1c2f4b7d30`, `b3d7e1a5c9f2`); `compare_metadata` = none |
| Frontend build | Ôťů | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | Ôťů | 574 passed; ruff clean |
| Git merge (`develop Ôćĺ main`) | Ôťů | merge commit `3438305` (PR #7) |
| CI green on `develop` head | Ôťů | `.github/workflows/ci.yml` |
| Automated Release workflow + ZIP/`.sha256` | Ôťů | `v1.1.0` tag Ôćĺ release created by CI |
| GitHub Release `v1.1.0` published | Ôťů | tag matches |
| ZIP attached | Ôťů | Windows portable ZIP (~24.6 MB) |
| `.sha256` attached + matches ZIP | Ôťů | `sha256sum -c` |
| Security (artifact + git tree clean) | Ôťů | no secrets/sessions/DB/models in ZIP; empty runtime dirs |
| Docker (`/health` + SPA + v1.1 routes) | Ôťů | build + run + restart verified |

### v1.0.5 (released 2026-10-04)

| Gate | v1.0.5 | Notes |
| --- | --- | --- |
| Git merge (`develop Ôćĺ main`) | Ôťů | merge commit `496598f` (PR #6) |
| Version consistency (`1.0.5` everywhere) | Ôťů | app / pyproject / frontend (+ lock) |
| CI green on `develop` head | Ôťů | `.github/workflows/ci.yml` |
| Diagnostics tests (`test_diagnostics.py`) | Ôťů | redaction + report + new sections + degradation |
| New API tests | Ôťů | `test_bindings_api.py`, `test_campaigns_api.py`, `test_product_api.py` |
| Migration drift check | Ôťů | `7cb72d22d35b`; `compare_metadata` = none |
| Automated Release workflow | Ôťů | `v1.0.5` tag Ôćĺ release created by CI |
| GitHub Release `v1.0.5` published | Ôťů | tag matches |
| ZIP attached | Ôťů | Windows portable ZIP |
| `.sha256` attached + matches ZIP | Ôťů | `sha256sum -c` |
| Security (artifact + git tree clean) | Ôťů | no secrets/sessions/DB; empty runtime dirs |
| Docker (`/health` + SPA) | Ôťů | build + run + restart verified |
| Frontend build | Ôťů | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | Ôťů | 491 passed |

### Prior release ÔÇö v1.0.4

| Gate | v1.0.4 | Notes |
| --- | --- | --- |
| Git merge (`develop Ôćĺ main`) | Ôťů | merge commit `3f42c3d` (PR #5) |
| Version consistency (`1.0.4` everywhere) | Ôťů | app / pyproject / frontend (+ lock) |
| CI green on `develop` head | Ôťů | `.github/workflows/ci.yml` |
| Diagnostics tests (`test_diagnostics.py`) | Ôťů | redaction + report + API + degradation |
| Automated Release workflow | Ôťů | `v1.0.4` tag Ôćĺ release created by CI |
| GitHub Release `v1.0.4` published | Ôťů | tag matches |
| ZIP attached | Ôťů | ~24 MB Windows portable ZIP |
| `.sha256` attached + matches ZIP | Ôťů | `sha256sum -c` OK |
| Security (artifact + git tree clean) | Ôťů | no secrets/sessions/DB; empty runtime dirs |
| Docker (`/health` + SPA) | Ôťů | build + run + restart verified |
| Frontend build | Ôťů | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | Ôťů | 462 passed |

### Prior release ÔÇö v1.0.3

| Gate | v1.0.3 | Notes |
| --- | --- | --- |
| Git merge (`develop Ôćĺ main`) | Ôťů | merge commit `f18f53a` (PR #4) |
| Version consistency (`1.0.3` everywhere) | Ôťů | app / pyproject / frontend |
| CI green on `develop` head | Ôťů | `.github/workflows/ci.yml` |
| Diagnostics tests (`test_diagnostics.py`) | Ôťů | redaction + report + API |
| Automated Release workflow | Ôťů | `v1.0.3` tag Ôćĺ release created by CI |
| GitHub Release `v1.0.3` published | Ôťů | tag matches |
| ZIP attached | Ôťů | ~24 MB Windows portable ZIP |
| `.sha256` attached + matches ZIP | Ôťů | `sha256sum -c` |
| Security (artifact + git tree clean) | Ôťů | no secrets/sessions/DB; empty runtime dirs |
| Docker (`/health` + SPA) | Ôťů | verified post-release on `develop` |
| Frontend build | Ôťů | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | Ôťů | 447 passed at release; 462 after maintenance |

## Known non-blocking items (documented, do not block a release)

- Manager-bot runtime polls only while the app is running (no webhook by
  default) ÔÇö acceptable for local/portable use.
- Mini App BotFather registration + public HTTPS URL are the owner's deployment
  steps (documented in `docs/SETUP.md`); the Mini App is off by default.
- If the Release workflow's portable job fails (e.g. a packaging path bug), the
  tag stays immutable (D-050): fix forward on `develop` for the next release and,
  if the current release needs the artifact, build it from the tag
  (`git worktree add --detach <dir> vX.Y.Z` -> `scripts/build_portable.sh`) and
  attach the ZIP + `.sha256` to the Release manually. Do **not** move the tag.
- `PytestUnhandledThreadExceptionWarning` can appear from the aiosqlite worker
  thread on teardown in `test_hardening_api.py`; the run still passes.
