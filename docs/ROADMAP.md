# Roadmap — Telegram Channel Management Suite

Status legend: ✅ done · 🟡 in progress · ⬜ planned
Each phase must end **runnable**, with tests + docs + updated persistent state + a
git commit. Phases are large vertical slices (backend + DB + UI + tests).

---

## PHASE 0 — Repository audit + architecture + persistent memory 🟡
- [x] Repository audit (repo was empty except a stub README).
- [x] `.gitignore`, `.env.example`, directory skeleton.
- [x] `docs/ARCHITECTURE.md`.
- [x] `docs/ROADMAP.md` (this file).
- [x] Persistent agent state: `agent/CURRENT_STATE.md`, `NEXT_TASK.md`,
      `DECISIONS.md`, `CHANGELOG.md`.
- [x] Remaining docs: SETUP, SECURITY, UI, API, TROUBLESHOOTING.
- [ ] Initial git commit.

## PHASE 1 — Application skeleton ⬜
- [ ] FastAPI app factory, config (pydantic-settings), logging.
- [ ] SQLAlchemy async + SQLite, Base, Alembic scaffold.
- [ ] Health checks (`/health`, `/health/deep`).
- [ ] Settings table + settings service.
- [ ] Events (log/error center) model + service.
- [ ] Job queue model + durable queue skeleton.
- [ ] Vue 3 + Vite + TS frontend foundation, builds to static, served by FastAPI.
- [ ] Windows `run.bat` / `stop.bat` skeleton.
- [ ] Docker foundation (`Dockerfile`, `docker-compose.yml`).
- [ ] Tests: config, db, health, api smoke.
- [ ] Commit.

## PHASE 2 — Telegram foundation ⬜
- [ ] `TelegramBotProvider` interface + aiogram impl + fake impl.
- [ ] Manager bot: commands, admin whitelist, notifications, error forwarding.
- [ ] Channel connection + access/permission checks.
- [ ] Managed bots: list, health, add, disable, remove.
- [ ] Bot inventory API + UI section.
- [ ] Tests (fake provider). Commit.

## PHASE 3 — Reaction Manager ⬜
- [ ] Reaction planner (weights, probability, delays, skip, profiles).
- [ ] Scheduler + durable queue + restart recovery.
- [ ] `reaction_jobs` model + per-job status/attempts/error.
- [ ] Rules Engine (categories, allowed/preferred/forbidden, confidence, priority).
- [ ] Preview/simulation.
- [ ] API + UI (Reactions, Rules, Queue). Tests. Commit.

## PHASE 4 — User Session Manager ⬜
- [ ] `SessionProvider` + Telethon impl + fake.
- [ ] Interactive auth wizard (api id/hash, phone, code, 2FA).
- [ ] Session import, list, revoke, health check, owner labelling.
- [ ] Secure storage (OS store on Windows, env/secrets on VPS).
- [ ] API + UI (Sessions wizard). Tests. Commit.

## PHASE 5 — Audience ⬜
- [ ] Sources CRUD + scan (public channel/group/entity).
- [ ] `audience_users` storage, dedup, filters, tags, search, sort.
- [ ] Import/export, source statistics.
- [ ] Robust Telegram error handling.
- [ ] API + UI (Audience, Sources). Tests. Commit.

## PHASE 6 — Invite Manager ⬜
- [ ] Invite queue, account/source/target selection, filters.
- [ ] Dry-run, manual approval, start/pause/stop.
- [ ] Per-account and per-user status, logs, safe retry.
- [ ] FloodWait / privacy / admin handling (pause + show wait).
- [ ] Mandatory pre-run confirmation summary.
- [ ] API + UI (Invites). Tests. Commit.

## PHASE 7 — Tiny AI ⬜
- [ ] Classifier interface + rules fast path.
- [ ] Optional llama.cpp tiny GGUF backend, strict JSON output.
- [ ] Confidence routing, AI enable/disable, model path config.
- [ ] API + UI (AI). Tests. Commit.

## PHASE 8 — Analytics ⬜
- [ ] Content analytics (posts, time, reactions, type, category).
- [ ] Audience analytics (sources, growth, engagement available via API).
- [ ] Charts + plain-language explanations on Dashboard.
- [ ] API + UI (Analytics, Dashboard). Tests. Commit.

## PHASE 9 — Mini App ⬜
- [ ] Reuse the same SPA for Mini App.
- [ ] Telegram WebApp authentication (initData validation).
- [ ] Responsive mobile UI; Dashboard/Bots/Reactions/Queue/Audience/Health/Settings.
- [ ] Tests. Commit.

## PHASE 10 — Portable Windows ⬜
- [ ] Self-contained packaging (embedded Python, no Node/Docker).
- [ ] `run.bat` (start + open browser), `stop.bat` (graceful shutdown).
- [ ] Backup/restore (DB, config, rules, profiles, state; sessions separately).
- [ ] Portable startup smoke test.
- [ ] `README.txt`. Commit.

## PHASE 11 — VPS / Docker ⬜
- [ ] Production `Dockerfile` + `docker-compose.yml` + `.env.example`.
- [ ] HTTPS / reverse-proxy documentation.
- [ ] Backup + restore docs for VPS.
- [ ] Same codebase as local — no separate "server version". Commit.

---

## Cross-cutting (do continuously)
- Persistent memory files updated every phase.
- Tests for every module (unit, db, api, scheduler, providers, portable smoke).
- Security review against `docs/SECURITY.md` before each commit.
- Keep the app runnable after every phase.
