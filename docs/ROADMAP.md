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
- [x] Committed on `develop` (`4b42fcb`).

## PHASE 8 — Analytics ✅
- [x] Content analytics (posts, time, reactions, type, category) —
      `AnalyticsRepository` + `AnalyticsService.content()`.
- [x] Audience analytics (sources, growth, source effectiveness, invite outcomes).
- [x] Reaction analytics (status mix, success rate, emoji, per-bot, per-category).
- [x] Charts (`Sparkline.vue`, `BarList.vue`, dependency-free SVG) + plain-language
      explanations on the Dashboard and the new `AnalyticsView.vue`.
- [x] API `/api/v1/analytics/{overview,content,reactions,audience}`. Tests. Commit.
- [x] Committed on `develop` (`f295111`).

## PHASE 9 — Mini App ✅
- [x] Reuse the same SPA for Mini App (no second interface; D-003).
- [x] Telegram WebApp authentication: server-side `initData` HMAC-SHA256
      verification, freshness check, owner allow-list, signed session cookie.
- [x] API `/api/v1/miniapp/{config,auth,me,logout}` + Setup Wizard `miniapp` check.
- [x] Responsive mobile UI (bottom nav) + Telegram dark theme; the same views
      cover Dashboard/Bots/Reactions/Queue/Analytics/Health/Settings.
- [x] Tests (auth unit + API). Commit.

## PHASE 10 — Portable Windows ✅
- [x] `run.bat` (start + open browser, sets `TCMS_ROOT`/`PYTHONPATH`) and
      `stop.bat` (graceful shutdown via the local endpoint).
- [x] `scripts/build_portable.sh` assembles the portable tree (`app/`, `runtime/`,
      data dirs, launcher files); `portable/README.txt` for the owner.
- [x] Backup/restore service + API: `.tcmsbak` zip (DB + manifest); sessions
      excluded by default; safety backup before restore; config export/import
      (`settings`/`reaction_profiles`/`reaction_rules` only).
- [x] `BackupView.vue` (Резервные копии) with plain-language help + confirmations.
- [x] `static_dir()` resolved package-relative so code can live under `app/`.
- [x] Portable startup smoke test (`tests/test_portable_smoke.py`).
- [x] Tests (backup service + API + smoke) green; docs + memory updated. Commit.

## PHASE 11 — VPS / Docker ✅
- [x] Production `Dockerfile` (multi-stage: Node SPA build → Python runtime,
      non-root uid 10001) — **built and smoke-tested** (health + SPA + backup).
- [x] `docker/docker-compose.yml` (optional `.env`, bind-mounted mutable state,
      healthcheck, `restart: unless-stopped`, `127.0.0.1` binding).
- [x] HTTPS: `docker/docker-compose.proxy.yml` + `docker/Caddyfile` (automatic
      Let's Encrypt) with an nginx alternative documented in `docs/SETUP.md`.
- [x] Backup/restore docs for VPS; secrets policy in `docs/SECURITY.md`;
      container troubleshooting in `docs/TROUBLESHOOTING.md`.
- [x] Same codebase as local/portable — no separate "server version" (D-004).

---

## Post-roadmap polish

- [x] **Audience & Sources frontend views** (`SourcesView.vue`, `AudienceView.vue`)
      — closes the main UI gap; the PHASE 5 API was already complete. RU-first,
      search/filters/tags/pagination, scan confirmation + progress, export/import.
- [x] Fully self-contained Windows portable build: `scripts/fetch_embedded_python.sh`
      downloads the official embeddable Python, writes the `._pth`, and installs
      dependencies; wired into `scripts/build_portable.sh` with a
      `--no-runtime`/`SKIP_RUNTIME=1` offline fallback.
- [x] **Post-1.0 hardening**: manager-bot runtime (admin-whitelisted RU command
      loop + notification forwarding, D-047/D-048) and a standalone account
      permission probe (`ok`/`partial`/`no_access`/`auth_required`/`admin_required`/
      `privacy_restricted`/`flood_wait`/`error`, D-049).
- [ ] Optional (remaining): Alembic migrations; channel-binding registry/UI;
      Mini App BotFather registration helper.

---

## Release

- **v1.0.0 (2026-10-03):** first production release — the complete PHASE 0–11
  suite plus RC and post-1.0 hardening. Annotated tag `v1.0.0` + GitHub Release
  on the `develop → main` merge commit `82c1059`. See `docs/RELEASE_CHECKLIST.md`
  and `agent/CHANGELOG.md`. After v1.0.0, development continues on `develop`; no
  artificial new phases.

---

## Cross-cutting (do continuously)
- Persistent memory files updated every phase.
- Tests for every module (unit, db, api, scheduler, providers, portable smoke).
- Security review against `docs/SECURITY.md` before each commit.
- Keep the app runnable after every phase.
