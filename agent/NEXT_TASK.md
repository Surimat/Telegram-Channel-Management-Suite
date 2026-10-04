# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-04
**Status:** **v1.0.2 released.** `main == origin/main == develop == 61d39fa`
(tag `v1.0.2`; PR #3 merged). GitHub Actions **created the GitHub Release itself**
and attached the Windows portable ZIP + `.sha256` (D-060) — the manual fallback
used for `v1.0.1` is gone. CI green on `main` and `develop`. Suite green at
**428 passed**; `ruff` clean; SPA builds; portable build works.

---

## Active task: none required — v1.0.2 is released

The roadmap (PHASE 0–11) is complete and shipped through `v1.0.2`. There is no
required next task. Do **not** invent a new phase or re-open PHASE 8–11.

Optional work (only if the owner asks):

1. A fully automated @BotFather Mini App flow (the one-click menu-button
   registration already exists, D-054).
2. Short-lived signed Mini App session tokens if the panel is exposed beyond the
   owner (see D-035 for the current decision).
3. Any owner-requested feature — record a decision, keep the vertical-slice
   workflow (backend + DB + UI + tests + docs + memory + commit).

Before any future release: follow `docs/RELEASE_CHECKLIST.md`. Do **not** push
directly to `main`; land via a reviewed PR. Do **not** move/rewrite
`v1.0.0`/`v1.0.1`/`v1.0.2` tags (D-050).

Done recently (do not rebuild):
- **v1.0.2** (D-060): the Release workflow **creates the GitHub Release** when
  missing (`gh release create --verify-tag`) and attaches the ZIP + `.sha256`, so
  a `v*` tag is a complete release with no manual step. Verified: tag `v1.0.2` →
  run `37192670044` → both jobs success → release assets attached, checksum
  matches the ZIP digest (`b6e343fa…`).
- **Portable ZIP relative-path fix** (D-059): `build_portable.sh` normalises `OUT`
  to an absolute path; regression test added.
- **GitHub Actions CI** (D-053): ruff + pytest and the frontend build on
  `main`/`develop`.
- **Mini App setup helper** (D-054): `POST /api/v1/miniapp/setup` registers the
  bot's Web App menu button.
- **Per-channel analytics** (D-055): `/api/v1/analytics/*` accept `channel_id`.
- **Reproducible portable packaging + Release workflow** (D-056):
  `scripts/build_win_runtime.py`, `scripts/win-requirements.lock`,
  `scripts/build_portable.sh`.
- **Async test-harness flake fixed** (D-058): deterministic 428-pass suite.

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
