# Roadmap — Telegram Channel Management Suite

Status legend: ✅ done · 🟡 in progress · ⬜ planned
Each phase must end **runnable**, with tests + docs + updated persistent state + a
git commit. Phases are large vertical slices (backend + DB + UI + tests).

---

## PHASE 0 — Repository audit + architecture + persistent memory ✅
- [x] Repository audit (repo was empty except a stub README).
- [x] `.gitignore`, `.env.example`, directory skeleton.
- [x] `docs/ARCHITECTURE.md`.
- [x] `docs/ROADMAP.md` (this file).
- [x] Persistent agent state: `agent/CURRENT_STATE.md`, `NEXT_TASK.md`,
      `DECISIONS.md`, `CHANGELOG.md`.
- [x] Remaining docs: SETUP, SECURITY, UI, API, TROUBLESHOOTING.
- [x] Initial git commit.

## PHASE 1 — Application skeleton ✅
- [x] FastAPI app factory, config (pydantic-settings), logging.
- [x] SQLAlchemy async + SQLite, Base (Alembic deferred; `create_all` for now).
- [x] Health checks (`/health`, `/health/deep`).
- [x] Settings table + settings service.
- [x] Events (log/error center) model + service.
- [x] Job queue model + durable queue skeleton + scheduler.
- [x] Vue 3 + Vite + TS frontend foundation, builds to static, served by FastAPI.
- [x] Windows `run.bat` / `stop.bat` skeleton.
- [x] Docker foundation (`Dockerfile`, `docker-compose.yml`).
- [x] Tests: config, db, health, api smoke. Commit.

## PHASE 2 — Telegram foundation 🟡
- [x] `TelegramBotProvider` interface + aiogram impl + fake impl + registry.
- [x] Bot inventory: `Bot` model + repository + `BotService`.
- [x] Managed bots: list/register, health, add, disable, remove, get/replace
      token (official API).
- [x] Bot inventory API + UI section (`BotsView`) + Dashboard card.
- [x] Tokens sealed at rest; never returned by the API.
- [x] Setup Wizard `manager_bot` + `managed_bots` checks.
- [x] Tests (fake provider): 60 passed; ruff clean. Commit.
- [ ] Manager-bot runtime (command loop, admin whitelist, notifications, error
      forwarding, `managed_bot` update ingestion) — deferred into PHASE 3+/manager
      runtime work.

## PHASE 3 — Reaction Manager ✅
- [x] Reaction planner (weights, probability, delays, skip, profiles).
- [x] Scheduler + durable queue + restart recovery.
- [x] `reaction_jobs` model + per-job status/attempts/error.
- [x] Rules Engine (categories, allowed/preferred/forbidden, confidence, priority).
- [x] Preview/simulation.
- [x] API + UI (Reactions: profiles, rules, simulation, queue). Tests. Commit.

## PHASE 4 — User Session Manager ✅
- [x] `SessionProvider` + Telethon impl + fake.
- [x] Interactive auth wizard (api id/hash, phone, code, 2FA).
- [x] Session import, list, re-auth (logout), health check, owner labelling.
- [x] Secure storage: api_hash + full phone sealed (Fernet); session files in
      git-ignored `sessions/` (out of the Docker image); never in logs/UI/errors.
- [x] API `/api/v1/sessions/*` + UI (`SessionsView` wizard). Tests. Commit.

## PHASE 5 — Audience ✅
- [x] Sources CRUD (`/api/v1/audience/sources`) + scan of public channel/group/
      entity; source `check` (resolve + reachability) and scan `preview` (dry-run).
- [x] `audience_sources` + `audience_users` + `source_user_links` (many-to-many);
      dedup is enforced by a unique `telegram_user_id`.
- [x] Bounded, restart-safe streaming scan (durable job, per-chunk commits,
      `scanned_offset` progress, recover→pause on restart).
- [x] Honest completeness: `complete` / `partial` / `no_access` / `failed`,
      explained in plain language; FloodWait pauses, never bypassed.
- [x] Filters, tags (assign/remove/rename/delete), search, sort, pagination.
- [x] CSV/JSON export (streaming; PII off by default, gated by setting) and
      CSV/JSON import with dedup + invalid-row counting.
- [x] Audience dashboard + per-source statistics.
- [x] API `/api/v1/audience/*` + Setup Wizard `audience` check. Tests. Commit.
- [ ] Dedicated Audience/Sources UI views — deferred to the frontend rollout.

## PHASE 6 — Invite Manager ✅
- [x] Invite queue, account/source/target selection, filters.
- [x] Dry-run preview + mandatory pre-run confirmation summary.
- [x] Start/pause/resume/stop, per-account and per-user status, logs,
      safe retry (only technically retryable failures).
- [x] FloodWait / privacy / admin handling (pause + show wait; never bypassed).
- [x] Durable queue: one bounded batch per tick, restart-safe; recover→pause.
- [x] API `/api/v1/invites/*` + Setup Wizard `invites` check + `InvitesView.vue`.
- [x] Tests. Commit.

## PHASE 7 — Tiny AI ✅
- [x] Classifier interface (`Classifier` Protocol) + rules fast path
      (`RulesClassifier`); rules-first routing (`RoutingClassifier`).
- [x] Optional llama.cpp tiny GGUF backend (`LlamaCppBackend`, lazy, optional),
      strict JSON contract validation, deterministic fake backend for offline/tests.
- [x] Confidence routing (rules threshold → AI → threshold → graceful fallback),
      AI enable/disable, DB-overridable model path + settings with UI help.
- [x] API `/api/v1/ai/*` + Setup Wizard `ai` check + `AiView.vue`. Tests. Commit.
      Models are user-provided `.gguf` assets in gitignored `/models/`.
- [ ] Commit pending on `develop`.

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
