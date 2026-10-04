# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-04
**Status:** **v1.0.1 released.** `main == origin/main == develop == d267cf6`
(tag `v1.0.1`; PR #2 merged; GitHub Release published with the Windows portable
ZIP + `.sha256`). Post-1.0 hardening is on `main`: versioned Alembic migrations,
the Channel Registry, CI, the Mini App setup helper, per-channel analytics,
reproducible cross-platform portable packaging, and a Release workflow. Version
is **1.0.1**. Suite is green at **428 passed**; `ruff` clean; SPA builds; Docker
image builds; portable tree starts end-to-end.

---

## Active task: next release (v1.0.2) — release-engineering follow-up

`v1.0.1` is out. There is **no open PR** and no immediate feature work required.
The remaining release-engineering item:

1. The Release workflow's portable job failed on `v1.0.1` (path bug now fixed on
   `develop`, D-059). The next `develop → main` PR carries the fix; a `v1.0.2` tag
   will then exercise the fixed workflow end-to-end.
2. Before tagging, run the workflow via **Actions → Release → Run workflow**
   (`workflow_dispatch`) to confirm the portable job is green without consuming a
   tag. Follow `docs/RELEASE_CHECKLIST.md`.
3. Do **not** move or re-tag `v1.0.1` (D-050); the ZIP for it was built from
   `d267cf6` and is attached to the existing Release.

Follow `docs/RELEASE_CHECKLIST.md`. Do **not** push directly to `main`; land via
a reviewed PR.

Done recently (do not rebuild):
- GitHub Actions CI (D-053, `.github/workflows/ci.yml`) runs ruff + pytest and the
  frontend build on `main`/`develop`.
- **Mini App setup helper** (D-054, `POST /api/v1/miniapp/setup` + the Settings
  card) registers the bot's Web App menu button — no manual @BotFather step.
- **Per-channel analytics** (D-055): `/api/v1/analytics/*` accept `channel_id`;
  the Analytics page has a channel selector.
- **Reproducible portable packaging + Release workflow** (D-056):
  `scripts/build_win_runtime.py`, `scripts/win-requirements.lock`,
  `scripts/build_portable.sh` (versioned ZIP + checksum).
- **Version is `1.0.1`** across the app package, `pyproject.toml` and the frontend (D-057).
- **Async test-harness flake fixed** (D-058): engine is disposed before reset;
  Mini App tests use `session_scope()`. Suite is deterministic.
- **Portable ZIP relative-path bug fixed** (D-059): `build_portable.sh` resolves
  `OUT` to an absolute path; regression test added (428 passed).

Do **not** create artificial new phases and do **not** re-open PHASE 8–11.

### What exists (do not rebuild)

- PHASE 0–11 complete; `agent/CURRENT_STATE.md` §2a/§2b/§4 lists what is done and the
  remaining gaps.
- Manager bot: `backend/app/manager/{bus,service,runtime}.py`, `/api/v1/manager/*`,
  RU commands, admin whitelist, notification toggles in Settings UI.
- Permission probe: `PermissionService`, `PermissionCheck`, `/api/v1/permissions/*`,
  panel in the Sessions page.
- Portable build is zero-setup: `scripts/fetch_embedded_python.sh` +
  `scripts/build_portable.sh` (D-043).
- Release process: `docs/RELEASE_CHECKLIST.md`.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 427 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
