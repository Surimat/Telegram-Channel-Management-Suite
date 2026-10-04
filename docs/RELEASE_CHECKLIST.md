# RELEASE CHECKLIST — Telegram Channel Management Suite

Use this checklist before tagging a release. All commands run from the
repository root unless stated otherwise.

## 1. Code quality gates (must pass)

```bash
python -m pytest                 # full suite — currently 428 passed
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

| Gate | v1.0.2 | Notes |
| --- | --- | --- |
| Git merge (`develop → main`) | | merge commit SHA |
| Version consistency (`1.0.2` everywhere) | | app / pyproject / frontend |
| CI green on `develop` head | | `.github/workflows/ci.yml` |
| Portable build (`build_portable.sh`) | | ZIP name + size |
| Automated Release workflow | | `v*` tag → release created by CI |
| GitHub Release `v1.0.2` published | | tag matches |
| ZIP attached | | asset present, non-empty |
| `.sha256` attached + matches ZIP | | `sha256sum -c` |
| Security (artifact + git tree clean) | | no secrets/sessions/DB/exports |
| Docker (`/health` + SPA) | | build + run |
| Frontend build | | `vue-tsc` + `npm run build` |
| Tests (`pytest` / `ruff`) | | counts |

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
