# Roadmap ‚Äî Telegram Channel Management Suite

Status legend: ‚úÖ done ¬∑ üü° in progress ¬∑ ‚¨ú planned
Each phase must end **runnable**, with tests + docs + updated persistent state + a
git commit. Phases are large vertical slices (backend + DB + UI + tests).

---

## PHASE 0 ‚Äî Repository audit + architecture + persistent memory ‚úÖ
- [x] Repository audit (repo was empty except a stub README).
- [x] `.gitignore`, `.env.example`, directory skeleton.
- [x] `docs/ARCHITECTURE.md`.
- [x] `docs/ROADMAP.md` (this file).
- [x] Persistent agent state: `agent/CURRENT_STATE.md`, `NEXT_TASK.md`,
      `DECISIONS.md`, `CHANGELOG.md`.
- [x] Remaining docs: SETUP, SECURITY, UI, API, TROUBLESHOOTING.
- [x] Initial git commit.

## PHASE 1 ‚Äî Application skeleton ‚úÖ
- [x] FastAPI app factory, config (pydantic-settings), logging.
- [x] SQLAlchemy async + SQLite, Base. (Originally `create_all`; since v1.0.1
      versioned **Alembic** migrations are the source of truth ‚Äî see PHASE 1
      hardening below and `docs/database-migrations.md`.)
- [x] Health checks (`/health`, `/health/deep`).
- [x] Settings table + settings service.
- [x] Events (log/error center) model + service.
- [x] Job queue model + durable queue skeleton + scheduler.
- [x] Vue 3 + Vite + TS frontend foundation, builds to static, served by FastAPI.
- [x] Windows `run.bat` / `stop.bat` skeleton.
- [x] Docker foundation (`Dockerfile`, `docker-compose.yml`).
- [x] Tests: config, db, health, api smoke. Commit.

## PHASE 2 ‚Äî Telegram foundation ‚úÖ
- [x] `TelegramBotProvider` interface + aiogram impl + fake impl + registry.
- [x] Bot inventory: `Bot` model + repository + `BotService`.
- [x] Managed bots: list/register, health, add, disable, remove, get/replace
      token (official API).
- [x] Bot inventory API + UI section (`BotsView`) + Dashboard card.
- [x] Tokens sealed at rest; never returned by the API.
- [x] Setup Wizard `manager_bot` + `managed_bots` checks.
- [x] Tests (fake provider): 60 passed; ruff clean. Commit.
- [ ] Manager-bot runtime (command loop, admin whitelist, notifications, error
      forwarding, `managed_bot` update ingestion) ‚Äî deferred into PHASE 3+/manager
      runtime work.

## PHASE 3 ‚Äî Reaction Manager ‚úÖ
- [x] Reaction planner (weights, probability, delays, skip, profiles).
- [x] Scheduler + durable queue + restart recovery.
- [x] `reaction_jobs` model + per-job status/attempts/error.
- [x] Rules Engine (categories, allowed/preferred/forbidden, confidence, priority).
- [x] Preview/simulation.
- [x] API + UI (Reactions: profiles, rules, simulation, queue). Tests. Commit.

## PHASE 4 ‚Äî User Session Manager ‚úÖ
- [x] `SessionProvider` + Telethon impl + fake.
- [x] Interactive auth wizard (api id/hash, phone, code, 2FA).
- [x] Session import, list, re-auth (logout), health check, owner labelling.
- [x] Secure storage: api_hash + full phone sealed (Fernet); session files in
      git-ignored `sessions/` (out of the Docker image); never in logs/UI/errors.
- [x] API `/api/v1/sessions/*` + UI (`SessionsView` wizard). Tests. Commit.

## PHASE 5 ‚Äî Audience ‚úÖ
- [x] Sources CRUD (`/api/v1/audience/sources`) + scan of public channel/group/
      entity; source `check` (resolve + reachability) and scan `preview` (dry-run).
- [x] `audience_sources` + `audience_users` + `source_user_links` (many-to-many);
      dedup is enforced by a unique `telegram_user_id`.
- [x] Bounded, restart-safe streaming scan (durable job, per-chunk commits,
      `scanned_offset` progress, recover‚Üípause on restart).
- [x] Honest completeness: `complete` / `partial` / `no_access` / `failed`,
      explained in plain language; FloodWait pauses, never bypassed.
- [x] Filters, tags (assign/remove/rename/delete), search, sort, pagination.
- [x] CSV/JSON export (streaming; PII off by default, gated by setting) and
      CSV/JSON import with dedup + invalid-row counting.
- [x] Audience dashboard + per-source statistics.
- [x] API `/api/v1/audience/*` + Setup Wizard `audience` check. Tests. Commit.
- [ ] Dedicated Audience/Sources UI views ‚Äî deferred to the frontend rollout.

## PHASE 6 ‚Äî Invite Manager ‚úÖ
- [x] Invite queue, account/source/target selection, filters.
- [x] Dry-run preview + mandatory pre-run confirmation summary.
- [x] Start/pause/resume/stop, per-account and per-user status, logs,
      safe retry (only technically retryable failures).
- [x] FloodWait / privacy / admin handling (pause + show wait; never bypassed).
- [x] Durable queue: one bounded batch per tick, restart-safe; recover‚Üípause.
- [x] API `/api/v1/invites/*` + Setup Wizard `invites` check + `InvitesView.vue`.
- [x] Tests. Commit.

## PHASE 7 ‚Äî Tiny AI ‚úÖ
- [x] Classifier interface (`Classifier` Protocol) + rules fast path
      (`RulesClassifier`); rules-first routing (`RoutingClassifier`).
- [x] Optional llama.cpp tiny GGUF backend (`LlamaCppBackend`, lazy, optional),
      strict JSON contract validation, deterministic fake backend for offline/tests.
- [x] Confidence routing (rules threshold ‚Üí AI ‚Üí threshold ‚Üí graceful fallback),
      AI enable/disable, DB-overridable model path + settings with UI help.
- [x] API `/api/v1/ai/*` + Setup Wizard `ai` check + `AiView.vue`. Tests. Commit.
      Models are user-provided `.gguf` assets in gitignored `/models/`.
- [x] Committed on `develop` (`4b42fcb`).

## PHASE 8 ‚Äî Analytics ‚úÖ
- [x] Content analytics (posts, time, reactions, type, category) ‚Äî
      `AnalyticsRepository` + `AnalyticsService.content()`.
- [x] Audience analytics (sources, growth, source effectiveness, invite outcomes).
- [x] Reaction analytics (status mix, success rate, emoji, per-bot, per-category).
- [x] Charts (`Sparkline.vue`, `BarList.vue`, dependency-free SVG) + plain-language
      explanations on the Dashboard and the new `AnalyticsView.vue`.
- [x] API `/api/v1/analytics/{overview,content,reactions,audience}`. Tests. Commit.
- [x] Committed on `develop` (`f295111`).

## PHASE 9 ‚Äî Mini App ‚úÖ
- [x] Reuse the same SPA for Mini App (no second interface; D-003).
- [x] Telegram WebApp authentication: server-side `initData` HMAC-SHA256
      verification, freshness check, owner allow-list, signed session cookie.
- [x] API `/api/v1/miniapp/{config,auth,me,logout}` + Setup Wizard `miniapp` check.
- [x] Responsive mobile UI (bottom nav) + Telegram dark theme; the same views
      cover Dashboard/Bots/Reactions/Queue/Analytics/Health/Settings.
- [x] Tests (auth unit + API). Commit.

## PHASE 10 ‚Äî Portable Windows ‚úÖ
- [x] `run.bat` (start + open browser, sets `TCMS_ROOT`/`PYTHONPATH`) and
      `stop.bat` (graceful shutdown via the local endpoint).
- [x] `scripts/build_portable.sh` assembles the portable tree (`app/`, `runtime/`,
      data dirs, launcher files); `portable/README.txt` for the owner.
- [x] Backup/restore service + API: `.tcmsbak` zip (DB + manifest); sessions
      excluded by default; safety backup before restore; config export/import
      (`settings`/`reaction_profiles`/`reaction_rules` only).
- [x] `BackupView.vue` (–Ý–µ–∑–µ—Ä–≤–Ω—ã–µ –∫–æ–ø–∏–∏) with plain-language help + confirmations.
- [x] `static_dir()` resolved package-relative so code can live under `app/`.
- [x] Portable startup smoke test (`tests/test_portable_smoke.py`).
- [x] Tests (backup service + API + smoke) green; docs + memory updated. Commit.

## PHASE 11 ‚Äî VPS / Docker ‚úÖ
- [x] Production `Dockerfile` (multi-stage: Node SPA build ‚Üí Python runtime,
      non-root uid 10001) ‚Äî **built and smoke-tested** (health + SPA + backup).
- [x] `docker/docker-compose.yml` (optional `.env`, bind-mounted mutable state,
      healthcheck, `restart: unless-stopped`, `127.0.0.1` binding).
- [x] HTTPS: `docker/docker-compose.proxy.yml` + `docker/Caddyfile` (automatic
      Let's Encrypt) with an nginx alternative documented in `docs/SETUP.md`.
- [x] Backup/restore docs for VPS; secrets policy in `docs/SECURITY.md`;
      container troubleshooting in `docs/TROUBLESHOOTING.md`.
- [x] Same codebase as local/portable ‚Äî no separate "server version" (D-004).

---

## Post-roadmap polish

- [x] **Audience & Sources frontend views** (`SourcesView.vue`, `AudienceView.vue`)
      ‚Äî closes the main UI gap; the PHASE 5 API was already complete. RU-first,
      search/filters/tags/pagination, scan confirmation + progress, export/import.
- [x] Fully self-contained Windows portable build: `scripts/fetch_embedded_python.sh`
      downloads the official embeddable Python, writes the `._pth`, and installs
      dependencies; wired into `scripts/build_portable.sh` with a
      `--no-runtime`/`SKIP_RUNTIME=1` offline fallback.
- [x] **Post-1.0 hardening**: manager-bot runtime (admin-whitelisted RU command
      loop + notification forwarding, D-047/D-048) and a standalone account
      permission probe (`ok`/`partial`/`no_access`/`auth_required`/`admin_required`/
      `privacy_restricted`/`flood_wait`/`error`, D-049).
- [x] **Post-1.0 hardening (v1.0.1)**: versioned Alembic migrations; channel
      registry/UI; Mini App menu-button registration helper; per-channel
      analytics; reproducible cross-platform portable packaging + Release
      workflow.
- [x] **Release-engineering patch (v1.0.2)**: the Release workflow now creates the
      GitHub Release itself (`gh release create --verify-tag`) and attaches the
      portable ZIP + checksum, so a `v*` tag is a fully automated release; the
      portable-build relative-output-path fix (D-059) rides along. No product
      changes.
- [x] **Product polish (v1.0.3)**: **Diagnostics** page ‚Äî per-component status in
      plain language ("—á—Ç–æ —ç—Ç–æ –∑–Ω–∞—á–∏—Ç" + "—á—Ç–æ –¥–µ–ª–∞—Ç—å") for application, database,
      Telegram API, manager/managed bots, accounts, channels, audience, reactions,
      invites, AI, scheduler/queue, storage and portable runtime; a **redacted
      diagnostic report** (ZIP/JSON/TXT) with a server-side secret scan before
      export; and safe maintenance actions (restart scheduler, recheck Telegram,
      recheck channels, clean up stuck local jobs) that never delete user data.
- [x] **Startup robustness (v1.0.4)**: a damaged/unreadable database no longer
      crashes startup or the Diagnostics page ‚Äî every DB-backed check degrades to
      a friendly row, the report falls back to safe empty sections, and the DB
      row explains recovery; the Queue page shows plain Russian job labels.
      No new phases or features.
- [x] **Product slice (v1.0.5)**: owner-facing features that make the suite usable
      without a user account ‚Äî bot‚Üîchannel **bindings** with verified rights and
      channel **reaction capabilities** (the reaction planner now honours the
      channel's real emoji set); session-free invite **–ö–∞–º–ø–∞–Ω–∏–∏** with conservative
      risk modes and explainable **donor quality** indicators; **backup delivery
      destinations** (local / Telegram / Google Drive / –Ø–Ω–¥–µ–∫—Å.–î–∏—Å–∫, credentials
      sealed); a resumable first-run **Setup Wizard**; and a conservative,
      off-by-default **auto-update** that only checks and stages a SHA-256-verified
      file. New API + RU-first UI + tests; no new phases.
- [x] **Maintenance additions (v1.1.0, complete on `develop`)**: the multi-format
      **Account Hub** importer (`.session`, `.session` + companion JSON,
      StringSession and optional TDATA; local-only, owner-scoped, secret-safe,
      D-070); optional per-account **network routes (proxies)** ‚Äî CRUD, honest
      reachability check and account binding, explicitly never a limit bypass
      (D-065); **donor discovery** ‚Äî search donor channels by topic with candidate
      proposals that become audience sources only on an explicit click (D-066);
      a **lightweight local encoder** classifier mode that needs no model download
      (D-067) plus the optional **ruBERT-tiny2** embedding backend and its honest
      install flow (D-068); and the **bot-only / risk UX** (D-069: session-free
      analytics, adaptive wizard, intent-narrowed reactions). New API + RU-first
      UI + tests; Diagnostics and the redacted report gained matching rows and
      sections. No new phases.
- [x] **Content Studio (v1.2.0, complete on `develop`)**: a content pipeline that
      collects material from Telegram / RSS / Atom / manual sources, deduplicates
      it (source hash / message id / content hash / media hash), cleans it with a
      deterministic, explainable, cancellable preview, tracks usage rights with an
      attribution block, validates Telegram markup and renders a Telegram-like
      preview, manages inline button sets, applies per-source moderation (blocked
      keywords + quiet hours), plans multi-channel publications with a calendar,
      and publishes through a `PostingProvider` (bot by default; a user account
      only in the expanded mode) with durable auto-delete and first comments. A
      bounded, restart-safe posting tick (`content.posting`) drives due work.
      New API (`/api/v1/content/*`), a RU-first **Content Studio** UI page and
      tests; no new phases.
- [x] **Bot Factory + LAN Mesh (v1.3.0, released)**: a guided,
      local **Bot Factory** that plans a set of worker bots, checks usernames with
      Telegram, creates each bot through the official owner-confirmed @BotFather
      flow and adopts it, then binds it through the existing binding rules
      (D-077/D-078); and an **optional LAN Mesh / offline control plane** that
      joins several of the owner's computers on one local network with no cloud
      control plane ‚Äî deterministic identity, bounded broadcast discovery + manual
      peers, one-time-code pairing, deterministic coordinator election, fencing
      leases, a `mesh.tick` maintenance job, and a guard so only the coordinator
      polls Telegram (D-079‚Ä¶D-082). Standalone (one computer) stays the default.
      New API (`/api/v1/bot-factory/*`, `/api/v1/mesh/*`), two RU-first UI pages
      and tests; no new phases.
- [x] **Notification Center + Tray Agent + Editorial Workspace (v1.4.0,
      released)**: a durable, queryable **Notification Center** (categories,
      priorities, per-category routing to owner DM / notification group / Windows
      toast, quiet hours for non-urgent messages, anti-spam aggregation and a
      history; D-084‚Ä¶D-086); the **TCMS Tray Agent** so the portable app runs with
      no console window (hidden start, `/health` readiness, bounded restart
      backoff, optional Startup-folder autostart, secret-free snapshot surfaced in
      Diagnostics; D-087‚Ä¶D-088); and the **Editorial Workspace**, a linked Telegram
      forum supergroup where the owner, editors and moderators work the same
      publication queue as the Web UI (verified bot rights, roles by numeric
      Telegram id, optimistic-version moves and a full audit trail;
      D-089‚Ä¶D-091). New API (`/api/v1/notifications/*`, `/api/v1/editorial/*`),
      two RU-first UI pages and tests; no new phases.
- [ ] Optional (remaining, non-blocking): a full automated BotFather Mini App
      flow (the one-click menu-button registration exists, D-054); richer
      analytics; additional AI backends; a reliable permissively-licensed TDATA
      converter adapter (D-070). No new phases are planned ‚Äî see
      `agent/NEXT_TASK.md` (maintenance / optional extensions).

---

## v2.0 cycle — owner-approved priorities (released in v2.0.0)

Owner-approved priorities, worked sequentially in separately verifiable stages
(**Этапы**). Do not invent new directions and do not revisit implemented work.
All three stages shipped as **v2.0.0** (PR #23, merge `926a3b3`, tag `v2.0.0`).

1. **Web Wrappers and free text & image-generation AI providers — MAIN priority.**
   - **Stage 1 — free-first providers and honest capabilities (implemented;
     released in v2.0.0).** Free-first providers and honest capability
     reporting for the AI Gateway:
     - Keyless free text provider **`pollinations`** (`PollinationsProvider`,
       OpenAI-compatible `POST /openai/chat/completions`); it is **text only**
       (no vision — a real request returns `400 "model does not support image
       input"`).
     - Second keyless free text provider **`llm7`** (`Llm7Provider`, llm7.io
       OpenAI-compatible gateway, model `gpt-oss:20b`); anonymous chat works with
       no key, but the keyless models refused an image request upstream, so it is
       declared **text only** too.
     - Keyless free **image generation** — **`pollinations_image`**
       (`PollinationsImageProvider`, `https://image.pollinations.ai/prompt/…`,
       model `flux`). Probed HTTP 200 / `image/jpeg`, deterministic per
       prompt+seed. It is generation only and is **off by default** (opt-in), and
       it never claims image *understanding*.
     - Model-capability **catalog** (`ai/gateway/catalog.py`), **provisioning**
       (`ai/gateway/provisioning.py`, idempotent, never overwrites an
       owner-configured provider) and browser **preflight**
       (`ai/gateway/preflight.py`, honest per-step progress, never fails).
     - New endpoints: `GET /models`, `GET /operations`, `GET /browser/preflight`,
       `POST /browser/prepare`, `POST /provision`.
     - Honesty fix: `ProviderInfo.info` sets `auth_required` from the actual auth
       mode, so a keyless or browser-session provider never claims it needs a key.
     - `GET /operations` reports `image_generation` by matching a generator by
       kind (a generator is not a text provider, so it is never matched by
       `at_least`).
     - Session expiry is **failover**, not a hard stop: a wrapper that meets a
       login wall returns `AUTH_REQUIRED` and the router moves to the next
       eligible provider (`fallback_used`). The browser layer still never bypasses
       login, CAPTCHA or MFA.
     - UI: `AiGatewayView.vue` gains the model/operation matrix, a free-first
       provisioning button and a browser-preflight panel.
     - Tests: `tests/test_v2_ai_providers.py`.
     - **Deliberately not done:** bypassing an anti-bot JS challenge (e.g.
       Duck.ai) or unverified third-party keys — those stay browser-session-only
       or unavailable, reported honestly.
   - **Stage 2 — free vision (image understanding): CONFIRMED 2026-10-11 (D-122),
     released in v2.0.1.** A re-probe found **one** genuine keyless-free
     image-understanding path: the **Kilo Gateway** free pool
     (`api.kilo.ai/api/gateway`, OpenAI-compatible, model
     `dots-studio/dots-3-note-preview:free`). No key and no account; it described
     two distinct generated PNGs correctly and reproduced 3× identically.
     - Integrated **additively through the existing gateway**:
       `KiloGatewayProvider` (an `OpenAICompatibleProvider`), the `kilo_gateway`
       registry kind, a `catalog` entry (`verified` for `image_understanding`
       only) and a provisioning default.
     - **Opt-in and best-effort:** disabled by default; a rate limit/upstream
       outage is an honest failure and the router fails over, so no material is
       lost. The paid `kilo-auto/*` router is never requested
       (`PAID_MODEL_AUTH_REQUIRED`).
     - Still not possible: `api.llm7.io` keyless refuses an image (`400`);
       `gen.pollinations.ai` vision needs a key (`401`); `api.airforce` is paid
       (`402`); DuckDuckGo is an anti-bot challenge (never bypassed, D-117). No
       key is bundled and no challenge is bypassed.
     - Tests: `tests/test_v2_ai_providers.py`; opt-in live probe
       `tests/test_kilo_free_vision_live.py` (`TCMS_LIVE_KILO_VISION=1`).
2. **Mass connection of created bots to channels.** Implemented (released in
   v2.0.0) —
   see the Mass Bot-to-Channel Onboarding section below (D-120).
3. **Complete Content Operations with target-language translation.** Implemented
   (released in v2.0.0) — see the Target Language section below.

### v2.0 implementation notes (released in v2.0.0)

**Target-language translation (D-118).** The Content Studio gains an explicit
language stage: a **source language** (auto-detected or set per source) and a
**target language** resolved by precedence (publication → channel → source →
global default). Translation runs only when the languages differ, goes through
the **existing AI Gateway** (routing/retries/failover unchanged) and masks URLs,
`@username`, `t.me` links, hashtags, inline code, HTML and Telegram-entity spans
so the model never rewrites a link or markup. A total failure keeps the original
material. Additive migration `20261013_0900_d4e5f6a7b8c9_v2_0_target_language.py`.

**Mass bot-to-channel onboarding (D-120).** A batch connects up to 50 already
created bots to one channel using Telegram's official
`t.me/<bot>?startchannel&admin=<rights>` deep link (rights joined by `+`, not a
space — Bot API 6.0+). Rights are least-privilege, purpose-named profiles
(`reactions`, `posting`, `editing`), never a blanket "all rights". The owner
confirms each bot in Telegram; the candidate is then re-checked against Telegram
through the existing **BindingService**, so `ready` means "Telegram reports the
rights", not "a link was sent", and insufficient rights is an explicit
`needs_permission` state. `bot_onboarding.tick` is a durable, restart-safe
scheduler job that advances one bot per tick; a failure never stops the rest and
already-connected bots are never rolled back (pause/resume/retry/skip). The bot
token is never part of any request or response. Additive migration
`20261014_0900_e5f6a7b8c9d0_v2_0_bot_onboarding.py`; UI `BotOnboardingView.vue`
(`/bot-onboarding`). Tests: `tests/test_bot_onboarding.py`.

---

## Unreleased on `develop` (D-123…D-128, D-130, D-131)

Eight owner-approved stages are **merged on `develop` and not in a stable
release**. The six stages D-123…D-128 are shipped in the `v2.1.0-rc.1`
**pre-release** (2026-10-15); the latest **stable** tag remains `v2.0.1`. D-130
(the Reaction Manager channel-post fix) and D-131 (the one-step data-preserving
updater) came after the pre-release and are not in any tag yet. They are
additive; the version string reads `2.1.0` until the owner decides to cut a
stable release (D-060). Worked sequentially, each with its own locked decision
and tests. Do not tag anything here until asked.

- **D-123 — Personal Account Safety (2026-10-11, unreleased).** Acting through a
  personal Telegram (MTProto) account is refused unless the owner opts in.
  `services/personal_account.py` (`PersonalAccountPolicy`) reads two UI-editable
  switches — `personal_account_enabled` (master, default **OFF**) and
  `invites_enabled` (mass invitations, default **OFF**) — seeded at startup by
  `ensure_personal_account_settings()`. The master switch blocks every MTProto
  provider at one chokepoint (`SessionService.provider_for()`), so the API, the
  scheduler and background tasks are all refused while the Telegram **Bot API**
  keeps working. Mass invites require both switches, are capped and **clamped**
  (`invite_max_total=100`, `invite_max_per_account=20`) and are bounded by a rolling
  24-hour per-account ceiling (`invite_max_per_day=50`) that **pauses** a job with an
  honest `wait_until` instead of inviting. A blocked action answers a friendly `403`
  (`code/message/hint`). Additive migration `20261015_0900_f6a7b8c9d0e1`
  (`invite_jobs.rate_limited_at`); tests `tests/test_personal_account_safety.py`.
- **D-124 — Operational Module Registry (2026-10-12, unreleased).** A per-channel
  module map (`reactions`, `audience`, `invites`, `analytics`) becomes authoritative
  server-side. `services/channel_modules.py` (`parse_modules`, `effective_modules`,
  `ChannelModuleGuard`) is enforced in the **services** (not only the router), so
  the durable reaction tick, the audience scan and the invite resume path are all
  gated; a blocked durable job is retired honestly (`SKIPPED`/`PAUSED`) without
  contacting Telegram. An unconfigured channel has every module enabled (no silent
  lock-out) and an unknown name is ignored. The registry is a *permission to
  operate*, never a replacement for the D-123 safety gates or the real bot-rights
  probe. Friendly `403` (`ChannelModuleDisabledError`). Tests
  `tests/test_channel_modules.py`, `tests/test_reaction_service.py`.
- **D-125 — Bot Lifecycle Recovery and Adoption (2026-10-12, unreleased).**
  `services/bot_lifecycle.py` (`BotLifecycleService`) owns recovery and adoption
  over the two existing durable queues. `recover()` re-queues rows left mid-flight
  by a crash (`BotFactoryService.recover()`: `RUNNING → QUEUED`;
  `BotOnboardingService.recover()`: `VERIFYING → QUEUED`) and runs once at startup,
  so a queue cannot hang forever. `adopt_managed_bot()` routes a Telegram
  `managed_bot` update (the official `t.me/newbot` deep link) into its Bot Factory
  batch **idempotently** and settles the batch once no candidate remains waiting; a
  duplicate update is a no-op and a username that is not already a candidate is
  ignored — never searched for or imported (D-070). Tests
  `tests/test_bot_lifecycle_consolidation.py`. No schema change.
- **D-126 — Content Pipeline Consolidation (2026-10-13, unreleased).**
  `ContentPipelineService` (`services/content_pipeline.py`) is the single
  content-processing engine: the v1.2 `ContentService.rewrite_preview`/
  `apply_rewrite` **delegate** to it and map `PipelineError → ContentError`, so the
  v1.2 `/rewrite` contract is unchanged and the two engines cannot diverge.
  `ContentService` stays the receive/dedup owner (`grab`) and `PostingService` stays
  the publish owner. No feature change, no schema change. Tests
  `tests/test_content_consolidation.py`.
- **D-127 — Channel Overview (2026-10-13, unreleased).**
  `services/channel_overview.py` (`ChannelOverviewService`) is a **read-only**
  aggregation of a channel's real state across every module (identity/verification,
  module map, bindings, audience, invites, bots, content, pipeline, queue) with an
  honest attention level (`ok`/`info`/`warning`/`error`). It reads through the
  existing repositories and the D-124 module map, never writes a row, queues a job
  or calls Telegram. `GET /api/v1/channels/overview`, UI `/channel-overview`
  (`ChannelOverviewView.vue`). No schema change; tests `tests/test_channel_overview.py`.
- **D-128 — End-to-End Setup Wizard (2026-10-14, unreleased).**
  `services/setup_wizard.py` (`SetupWizardService`) is a **guided, resumable** flow
  from a fresh install to a working channel. A step's status is the **stored** result
  of a real server check (`SetupWizardStep`), never inferred: `verified` means the
  check ran and passed, `pending` means it failed, `unchecked` means it never ran.
  Opening the state endpoint writes nothing. The only step that contacts Telegram is
  `POST /api/v1/setup-wizard/test-publication`, which refuses unless the request sets
  `confirmed` **and** the stored `bot` and `content` checks passed; it then publishes
  one material through the existing Content Studio posting path. Exposed as
  `GET /api/v1/setup-wizard`, `POST /api/v1/setup-wizard/steps/{key}/run` and
  `POST /api/v1/setup-wizard/test-publication`; UI `/setup-wizard`
  (`SetupWizardView.vue`). Additive migration
  `20261016_0900_a7b8c9d0e1f2_v2_0_setup_wizard.py`; tests
  `tests/test_setup_wizard.py`.
- **D-130 — Reaction Manager channel-post source (2026-10-17, unreleased).**
  The manager bot now reads real **`channel_post`** / `edited_channel_post`
  updates (`MANAGER_ALLOWED_UPDATES` is passed as `allowed_updates`), and
  `ReactionService.ingest_channel_post()` stores the post with its real Telegram
  `chat_id`/`message_id` and plans the reaction jobs (idempotently; an edit never
  re-plans). `plan_post()` refuses a post without a real message id, so the manual
  UI path can no longer create an unrunnable job. Additive; no version, tag, PR or
  release change. Tests `tests/test_reaction_channel_post_repro.py` (15) and
  `tests/test_reaction_channel_post_pipeline.py` (12, end-to-end + a negative
  control); plain-language check `scripts/check_reactions.py`.
- **D-131 — One-step data-preserving updater (2026-10-18, unreleased).** The
  non-programmer owner updates an existing portable install by double-clicking
  `portable/UPDATE_EXISTING.bat`, which runs `scripts/update_existing.py` with the
  embedded Python. It backs up `.env`/`data`/`sessions`/`exports`/`app` to
  `backups/preupdate-<timestamp>/`, replaces only the code (never the new `.env`
  over the old one), applies pending migrations and verifies that every `enc:`
  secret still decrypts with the preserved `APP_SECRET_KEY`; a second run is a
  no-op and it touches no Telegram state. `scripts/build_portable.sh` bundles both
  files. Additive; no version, tag, PR or release change. Tests
  `tests/test_portable_update.py` (6).

See `docs/REAL_TELEGRAM_VERIFICATION_CHECKLIST.md` for the isolated-environment
verification these stages still need before a release.

---

## Release

- **v2.1.0 (2026-10-15):** a **release candidate** (`v2.1.0-rc.1`) published as a
  GitHub **Pre-release** built from `develop`. It rolls up the six committed stages
  D-123…D-128: **Personal Account Safety** (personal MTProto accounts opt-in and
  off by default, bounded invite caps plus a rolling 24-hour per-account ceiling,
  D-123); the **Operational Module Registry** (the per-channel module map gates
  every launch path, D-124); **bot-lifecycle recovery and deep-link adoption**
  (D-125); **Content Pipeline Consolidation** (one content-processing engine,
  D-126); the read-only **Channel Overview** (D-127); and the end-to-end **Setup
  Wizard** with real, server-verified per-step checks (D-128). It is a testing
  pre-release — it is **not** the Latest release and does not replace the stable
  `v2.0.1`. Migrations
  `20261015_0900_f6a7b8c9d0e1_v2_0_invite_rate_limit.py` and
  `20261016_0900_a7b8c9d0e1f2_v2_0_setup_wizard.py`.
- **v2.0.1 (2026-10-11):** a patch over v2.0.0 that adds the keyless-free
  **image understanding** (vision) path through the **Kilo Gateway** free model
  (`api.kilo.ai/api/gateway`, `dots-studio/dots-3-note-preview:free`), integrated
  additively through the existing AI Gateway (D-122). It is **opt-in and off by
  default**; a rate limit or upstream outage is an honest failure and the router
  fails over, so material is never lost. The verified free surface is now **text +
  image generation + image understanding**; no key is bundled and no challenge is
  bypassed. Released via a reviewed `develop → main` PR, tag `v2.0.1`.
- **v2.0.0 (2026-10-09):** the three agreed v2.0 stages. An **AI Gateway** over
  many providers (including keyless-free **text** and **image generation** ones)
  and browser **web wrappers**
  with verified free-first routing and honest capabilities (D-117…D-119); a
  per-content **Target Language** (D-v2 Part 1); **mass bot-to-channel onboarding**
  as a durable, restart-safe queue where `ready` means Telegram confirms the bot's
  rights (D-120); **Content Operations 2.0** (D-116); and a **hidden (windowless)
  background launch**. Additive migrations
  `20261012_0900_c3d4e5f6a7b8_v1_9_content_operations.py`,
  `20261013_0900_d4e5f6a7b8c9_v2_0_target_language.py`,
  `20261014_0900_e5f6a7b8c9d0_v2_0_bot_onboarding.py`. Released via a reviewed
  `develop → main` PR, tag `v2.0.0`.
- **v1.9.0 (2026-10-08):** **Content Operations 2.0** (D-116) — the existing
  Content Studio is extended into one pipeline (`source → gather → clean →
  mini-AI → moderation → publish → comment/delete`) instead of a second studio.
  Adds reusable **AI profiles** (prompt as data), a **mini-AI** classifier
  (category + intent, never an emoji), human **moderation** states, declarative
  **automation rules** and **secret-free pipeline analytics**. Additive migration
  `20261012_0900_c3d4e5f6a7b8_v1_9_content_operations.py`. Released via a
  reviewed `develop → main` PR, tag `v1.9.0`.
- **v1.8.2 (2026-10-08):** a **Web Wrapper Hub practical-verification patch**
  (D-115). It exercises the wrapper pipeline end to end on a deterministic
  **local fixture site** (real HTTP + HTML; index/search, article, extract, login
  and 500 pages) with **no external site, account, key or AI credential**, and
  fixes a real defect the genuine Playwright runtime had: `extract()` read `href`
  from the matched node itself, so a container selector (`li.link`, `tr.row`)
  returned empty links. Adds `WrapperDefinition.extract_attrs`, a 7/7 benchmark
  (`agent/WEB_WRAPPER_BENCHMARK.json`) and a skipping real-Chromium test. No new
  features, no schema change, no new runtime dependency. Released via a reviewed
  `develop ‚Üí main` PR #21 (merge `8542d4c`), tag `v1.8.2`; the Release workflow
  (run `37747125558`) attached the Windows portable ZIP (24 906 383 bytes, sha256
  `f0c6984d‚Ä¶f619`) + `.sha256`.
- **v1.8.1 (2026-10-07):** an **AI Gateway verification patch** (D-114) over
  v1.8.0. It proves the gateway *works* by behaviour and fixes two real defects ‚Äî
  a `web` provider whose wrapper id does not exist reported `available` (and lost
  its configured name), and `AIRouter._attempt` returned a transient *response*
  without retrying ‚Äî plus frontend lockfile version drift. No new features. The
  Release workflow (run `37705225761`) attached the Windows portable ZIP
  (24 905 404 bytes, sha256 `0ec6aca1‚Ä¶a9d4`) + `.sha256`.
- **v1.8.0 (2026-10-07):** the **AI Gateway + Web Wrapper Hub** (D-111‚Ä¶D-113) ‚Äî
  one access layer over many AI providers (OpenAI-compatible, OpenRouter, Google,
  Anthropic, DeepSeek, local Ollama) plus browser **web wrappers** that drive the
  owner's own logged-in session. Strategy-based routing, bounded retries, a
  per-provider circuit breaker and automatic failover; keys sealed and write-only;
  the request journal stores metadata only. Honest availability, no account
  registration and no CAPTCHA/MFA/regional-block or Telegram-limit bypass.
  Released via a reviewed `develop ‚Üí main` PR #19 (merge `d8c62c1`), tag `v1.8.0`;
  the Release workflow (run `37653661662`) attached the Windows portable ZIP
  (24 904 789 bytes, sha256 `9bb39e4b‚Ä¶d353c`) + `.sha256`.
- **v1.7.0 (2026-10-07):** the **Bot Factory** (v1.3) becomes a **durable creation
  queue** (D-109/D-110). A batch marks its free candidates and the scheduler job
  `bot_factory.create` creates them **one operation per tick**, so the batch is
  restart-resumable, can be stopped/resumed, and never rolls back an
  already-created bot; a failed candidate can be retried or skipped. A
  display-only `token_mask` (`1234‚Ä¶xyz`) is derived from the non-secret numeric
  bot id ‚Äî the raw managed-bot token is never returned, logged or exported.
  Deep-link batches are not background-ticked (the owner finishes them in
  Telegram). Additive only; no account registration and no Telegram-limit bypass.
- **v1.6.1 (2026-10-07):** a verification patch over v1.6.0 (D-107) ‚Äî owner-guard
  path normalisation (a leading `//` can no longer skip the guard), the
  `config_sync` capability reports `needs_setup` until a provider is connected,
  and the Google Drive token step is wired into the `/owner` UI. No new features.
- **v1.6.0 (2026-10-06):** an **Owner Auth + Config Sync** vertical slice (D-105/D-106).
  A **local owner profile** (password or PIN) protects the panel with a one-way
  PBKDF2 verifier and an HMAC-signed session token (`X-Owner-Token`; default-on
  middleware, local-first ‚Äî open until a profile enables protection). A
  **versioned encrypted configuration bundle** (canonical JSON ‚Üí AES-256-GCM, secret
  denylist) moves settings to a new computer via a local folder or Google Drive
  (app-data scope) ‚Äî never the DB, sessions or TDATA; conflicts are reported, not
  overwritten. Additive only; no account registration and no Telegram-limit bypass.
- **v1.5.4 (2026-10-06):** the last three **Consistency Auditor** coverage gaps
  (N, O, P) are closed with pure static checks ‚Äî an unused ORM column, a public
  service class no module references, and a Vue control whose handler is undefined
  or empty. The runtime mutation engine now detects **every** seeded defect: at that
  release **25/25** (the engine reports **32/32, 100%, 0 false positives**
  today), and `KNOWN_GAP_IDS` is empty. Additive only;
  no new phases; no account registration and no Telegram-limit bypass.
- **v1.5.3 (2026-10-06):** two high-impact **Consistency Auditor** gaps (M, Q)
  closed statically ‚Äî a setting saved but never read, and a channel-aware module
  that bypasses the Channel Registry; the runtime orphan-setting allow-list made
  honest (88%, 22/25).
- **v1.5.2 (2026-10-06):** the auditor's kill rate is **computed from runtime
  mutation executions**, never declared; silent-failure guard, router/backup/
  notification checks (D-102).
- **v1.5.1 (2026-10-06):** five forensic-audit fixes ‚Äî false `available`
  capabilities, a swallowed consistency-check failure, a write-only `language`
  preference, runtime-image source-unavailable checks, and `README.md` version
  drift (D-095‚Ä¶D-098).
- **v1.5.0 (2026-10-06):** Capability graph + i18n + Consistency Auditor. Three
  small cross-cutting layers that make the product explain itself honestly: a
  machine-readable **capability graph** (`GET /api/v1/capability-graph`, also
  embedded in the Setup Wizard and the Dashboard) so every surface agrees on
  what is available now and what still needs setup; a bilingual RU/EN **i18n
  catalog** (`core/i18n.py`) plus a stored `language` preference so wording is
  single-sourced; and a **Consistency Auditor** (`GET /api/v1/consistency`,
  rendered as the Diagnostics "–ü—Ä–æ–≤–µ—Ä–∫–∞ —Ü–µ–ª–æ—Å—Ç–Ω–æ—Å—Ç–∏" panel) whose static checks run
  in CI to catch cross-module drift. Additive only; no new phases; no account
  registration and no Telegram-limit bypass.
- **v1.4.0 (2026-10-06):** Notification Center + Tray Agent + Editorial
  Workspace (D-084‚Ä¶D-091). A durable, queryable Notification Center with
  categories, priorities, per-category routing (owner DM / notification group /
  Windows toast), quiet hours and anti-spam aggregation; the TCMS Tray Agent so
  the portable app runs with no console window (hidden start, `/health`
  readiness, bounded restart backoff, optional Startup-folder autostart); and the
  Editorial Workspace, a linked Telegram forum supergroup where the owner,
  editors and moderators work the same publication queue as the Web UI with
  verified bot rights and a full audit trail. New API
  (`/api/v1/notifications/*`, `/api/v1/editorial/*`), two RU-first UI pages and
  tests; no new phases. Neither feature registers accounts nor bypasses Telegram
  limits. Released from `develop` via a reviewed `develop ‚Üí main` PR #10
  (merge `306672e`), tagged `v1.4.0`; the Windows portable ZIP + `.sha256` are attached to the GitHub
  Release by the automated Release workflow (D-060).
- **v1.3.0 (2026-10-05):** Bot Factory + LAN Mesh / offline control plane
  (D-077‚Ä¶D-082). Create a set of worker bots for the owner's own channels through
  the official owner-confirmed @BotFather flow, and optionally join several of the
  owner's computers on one local network with no cloud control plane. Standalone
  (one computer) stays the default; neither feature registers Telegram accounts or
  bypasses Telegram limits. No new phases. Released from `develop` via a reviewed
  `develop ‚Üí main` PR (PR #9, merge `7788125`), tagged `v1.3.0`; the Windows
  portable ZIP + `.sha256` are attached to the GitHub Release by the automated
  Release workflow (D-060).
- **v1.2.0 (2026-10-05):** Content Studio ‚Äî content sources (Telegram / RSS /
  Atom / manual), deduplication, an explainable cleaner, usage-rights tracking,
  markup validation + Telegram-like preview, inline buttons, per-source
  moderation, multi-channel planning/calendar, and publishing through a
  `PostingProvider` with durable auto-delete and first comments (D-071‚Ä¶D-076).
  No new phases. Released from `develop` via a reviewed `develop ‚Üí main` PR,
  tagged `v1.2.0`; the Windows portable ZIP + `.sha256` are attached to the
  GitHub Release by the automated Release workflow (D-060).
- **v1.1.0 (2026-10-05):** Account Hub local importer, network routes (proxies),
  donor discovery, the lightweight encoder + ruBERT-tiny2 backend, and the
  bot-only / risk UX (D-065‚Ä¶D-070). No new phases. Released from `develop` via
  reviewed PR #7 (`develop ‚Üí main`, merge `3438305`), tagged `v1.1.0`; the Windows
  portable ZIP + `.sha256` are attached to the GitHub Release by the automated
  Release workflow (D-060).
- **v1.0.5 (2026-10-04):** product-slice release ‚Äî bot‚Üîchannel **bindings** +
  channel **reaction capabilities** (the reaction planner honours the channel's
  real emoji set), session-free invite **–ö–∞–º–ø–∞–Ω–∏–∏** with conservative risk modes
  and explainable **donor quality** indicators, **backup delivery destinations**
  (local / Telegram / Google Drive / –Ø–Ω–¥–µ–∫—Å.–î–∏—Å–∫, credentials sealed), a
  resumable first-run **Setup Wizard**, and a conservative, off-by-default
  **auto-update** (checks + stages a SHA-256-verified file, never auto-installs).
  New API + RU-first UI + tests; Diagnostics gained the new subsystem rows and
  redacted-report sections. No new phases. Published from `develop` via
  reviewed PR #6 (`develop ‚Üí main`, merge `496598f`), tagged `v1.0.5`; the Windows portable ZIP +
  `.sha256` are attached to the GitHub Release by the automated Release workflow
  (D-060).
- **v1.0.4 (2026-10-04):** startup-robustness patch ‚Äî a corrupt/unreadable
  database no longer crashes application startup or the **–î–∏–∞–≥–Ω–æ—Å—Ç–∏–∫–∞** page
  (checks degrade to friendly rows, the report falls back to safe empty sections,
  and the DB row explains recovery; D-062); the Queue page shows plain Russian
  job kind/status labels; `docs/TROUBLESHOOTING.md` gained a damaged-database
  entry. No new phases or features. Published from `develop` via a reviewed
  `develop ‚Üí main` PR, tagged `v1.0.4`; the Windows portable ZIP + `.sha256` are
  attached to the GitHub Release by the automated Release workflow (D-060).
- **v1.0.3 (2026-10-04):** product-polish patch ‚Äî the **Diagnostics** page
  (per-component status in plain language), a **redacted diagnostic report**
  (ZIP/JSON/TXT with a server-side secret scan) and **safe maintenance actions**
  (restart scheduler, recheck Telegram, recheck channels, clean up stuck local
  jobs), none of which delete user data (D-061). Also a UI-wording consistency
  pass. Published from `develop` via a reviewed `develop ‚Üí main` PR (merge commit
  `f18f53a`), tagged `v1.0.3`; the Windows portable ZIP + `.sha256` are attached
  to the GitHub Release by the automated Release workflow (D-060).
- **v1.0.2 (2026-10-04):** release-engineering patch ‚Äî the Release workflow
  creates/updates the GitHub Release itself and attaches the Windows portable ZIP
  + `.sha256` (D-060), making a `v*` tag a fully automated release with no manual
  fallback; carries the `build_portable.sh` relative-output-path fix (D-059). No
  product/functional changes. Published from `develop` via a reviewed
  `develop ‚Üí main` PR.
- **v1.0.1 (2026-10-04):** post-1.0 hardening release ‚Äî versioned Alembic
  migrations, the shared Channel Registry, per-channel analytics, GitHub Actions
  CI, the Mini App setup helper, and reproducible cross-platform portable
  packaging with an automated Release workflow. Version string is
  `1.0.1`. Published from `develop` via a reviewed `develop ‚Üí main` PR (merge
  commit `d267cf6`), tagged `v1.0.1`; the Windows portable ZIP is attached to the
  GitHub Release. The Release workflow's portable job hit a path bug for a
  relative output dir; the fix landed on `develop` (D-059) and the tag was **not**
  moved (D-050) ‚Äî the ZIP for `v1.0.1` was built from `d267cf6` and attached
  manually. The next tag (`v1.0.2`) runs the fixed workflow.
- **v1.0.0 (2026-10-03):** first production release ‚Äî the complete PHASE 0‚Äì11
  suite plus RC and post-1.0 hardening. Annotated tag `v1.0.0` + GitHub Release
  on the `develop ‚Üí main` merge commit `82c1059`. See `docs/RELEASE_CHECKLIST.md`
  and `agent/CHANGELOG.md`. After v1.0.0, development continues on `develop`; no
  artificial new phases.

---

## Cross-cutting (do continuously)
- Persistent memory files updated every phase.
- Tests for every module (unit, db, api, scheduler, providers, portable smoke).
- Security review against `docs/SECURITY.md` before each commit.
- Keep the app runnable after every phase.
