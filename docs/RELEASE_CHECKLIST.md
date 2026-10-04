# RELEASE CHECKLIST — Telegram Channel Management Suite

Use this checklist before tagging a release. All commands run from the
repository root unless stated otherwise.

## 1. Code quality gates (must pass)

```bash
python -m pytest                 # full suite — currently 491 passed
ruff check backend tests         # must be clean
cd frontend && npx vue-tsc --noEmit && npm run build   # typecheck + SPA build
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
