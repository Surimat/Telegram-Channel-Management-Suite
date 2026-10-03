# NEXT TASK — Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-03
**Status:** PHASE 0–11 **and** the Audience/Sources frontend polish are complete.
Start the next polish task below.

---

## Active task: Fully self-contained Windows binary (post-roadmap polish)

**Goal:** make the portable package truly zero-setup. Today `scripts/build_portable.sh`
stages the code + built SPA and the user must drop a Python embeddable package into
`runtime/` by hand (D-040). Automate that staging.

### What exists (do not rebuild)

- `scripts/build_portable.sh` — stages the portable tree.
- `portable/run.bat`, `portable/stop.bat`, `portable/README.txt` — launchers.
- `backend/app/core/paths.py` — `TCMS_ROOT` resolution (D-040).
- `tests/test_portable_smoke.py` — startup + graceful-shutdown smoke test.
- Docs: `docs/SETUP.md` (Windows portable section B), `docs/ARCHITECTURE.md` §11.

### Deliverable (one vertical slice)

1. Extend `scripts/build_portable.sh` (or add a small helper) to download the
   official Windows **embeddable** Python and unpack it into `runtime/`, then
   `pip install -r backend/requirements.txt` into it (`--target` / get-pip flow),
   so `run.bat` needs no manual step.
2. Keep it optional/offline-friendly: if the download is unavailable, fall back to
   the current manual staging and print a clear message.
3. Verify: run the portable smoke test; document the exact steps and the expected
   folder layout in `docs/SETUP.md`.
4. Update `agent/CURRENT_STATE.md`, `agent/CHANGELOG.md`, `docs/ROADMAP.md`; commit.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `.env`, or secrets into the portable package.
- Do not commit downloaded runtimes/binaries to git.

### Verification checklist for any change

```bash
python -m pytest                 # must stay green (currently 330 passed)
ruff check backend tests         # must stay clean
cd frontend && npm run build     # must succeed (outputs to backend/app/static)
```
