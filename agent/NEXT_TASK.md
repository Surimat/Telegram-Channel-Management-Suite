# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-04
**Status:** `v1.0.1` is published. `develop` carries the **v1.0.2 release prep**
(version `1.0.2`; the Release workflow now creates the GitHub Release itself,
D-060). No product/functional changes. Suite is green at **428 passed**; `ruff`
clean; SPA builds; portable build works.

---

## Active task: publish v1.0.2 (fully automated portable release)

Everything for `v1.0.2` is implemented, tested and documented on `develop`. The
remaining work is publication (no new features):

1. Push `develop`; confirm CI green.
2. Open/merge the `develop → main` PR (reviewed; no force).
3. Tag the merged `main` commit `v1.0.2` (annotated) and push it.
4. The **Release** workflow (`.github/workflows/release.yml`) now **creates the
   GitHub Release** (`gh release create --verify-tag`) and attaches the Windows
   portable ZIP + `.sha256` — the whole chain is automated, no manual fallback.
5. Verify the release, assets and checksum; sync `main` back into `develop`.
6. Update memory and set the next task to MAINTENANCE / OPTIONAL EXTENSIONS.

Follow `docs/RELEASE_CHECKLIST.md`. Do **not** push directly to `main`; land via
a reviewed PR. Do **not** move/rewrite `v1.0.0`/`v1.0.1` tags (D-050).

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
- **Async test-harness flake fixed** (D-058): engine is disposed before reset;
  Mini App tests use `session_scope()`. Suite is deterministic (428 passed).
- **Portable ZIP relative-path bug fixed** (D-059): `build_portable.sh` resolves
  `OUT` to an absolute path; regression test added.
- **Release workflow creates the Release** (D-060): fixes the manual fallback that
  `v1.0.1` needed (the old workflow only ran `gh release upload`).

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
