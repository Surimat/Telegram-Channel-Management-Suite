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
- [x] SQLAlchemy async + SQLite, Base. (Originally `create_all`; since v1.0.1
      versioned **Alembic** migrations are the source of truth — see PHASE 1
      hardening below and `docs/database-migrations.md`.)
- [x] Health checks (`/health`, `/health/deep`).
- [x] Settings table + settings service.
- [x] Events (log/error center) model + service.
- [x] Job queue model + durable queue skeleton + scheduler.
- [x] Vue 3 + Vite + TS frontend foundation, builds to static, served by FastAPI.
- [x] Windows `run.bat` / `stop.bat` skeleton.
- [x] Docker foundation (`Dockerfile`, `docker-compose.yml`).
- [x] Tests: config, db, health, api smoke. Commit.

## PHASE 2 — Telegram foundation ✅
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
- [x] **Post-1.0 hardening (v1.0.1)**: versioned Alembic migrations; channel
      registry/UI; Mini App menu-button registration helper; per-channel
      analytics; reproducible cross-platform portable packaging + Release
      workflow.
- [x] **Release-engineering patch (v1.0.2)**: the Release workflow now creates the
      GitHub Release itself (`gh release create --verify-tag`) and attaches the
      portable ZIP + checksum, so a `v*` tag is a fully automated release; the
      portable-build relative-output-path fix (D-059) rides along. No product
      changes.
- [x] **Product polish (v1.0.3)**: **Diagnostics** page — per-component status in
      plain language ("что это значит" + "что делать") for application, database,
      Telegram API, manager/managed bots, accounts, channels, audience, reactions,
      invites, AI, scheduler/queue, storage and portable runtime; a **redacted
      diagnostic report** (ZIP/JSON/TXT) with a server-side secret scan before
      export; and safe maintenance actions (restart scheduler, recheck Telegram,
      recheck channels, clean up stuck local jobs) that never delete user data.
- [x] **Startup robustness (v1.0.4)**: a damaged/unreadable database no longer
      crashes startup or the Diagnostics page — every DB-backed check degrades to
      a friendly row, the report falls back to safe empty sections, and the DB
      row explains recovery; the Queue page shows plain Russian job labels.
      No new phases or features.
- [x] **Product slice (v1.0.5)**: owner-facing features that make the suite usable
      without a user account — bot↔channel **bindings** with verified rights and
      channel **reaction capabilities** (the reaction planner now honours the
      channel's real emoji set); session-free invite **Кампании** with conservative
      risk modes and explainable **donor quality** indicators; **backup delivery
      destinations** (local / Telegram / Google Drive / Яндекс.Диск, credentials
      sealed); a resumable first-run **Setup Wizard**; and a conservative,
      off-by-default **auto-update** that only checks and stages a SHA-256-verified
      file. New API + RU-first UI + tests; no new phases.
- [x] **Maintenance additions (v1.1.0, complete on `develop`)**: the multi-format
      **Account Hub** importer (`.session`, `.session` + companion JSON,
      StringSession and optional TDATA; local-only, owner-scoped, secret-safe,
      D-070); optional per-account **network routes (proxies)** — CRUD, honest
      reachability check and account binding, explicitly never a limit bypass
      (D-065); **donor discovery** — search donor channels by topic with candidate
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
      control plane — deterministic identity, bounded broadcast discovery + manual
      peers, one-time-code pairing, deterministic coordinator election, fencing
      leases, a `mesh.tick` maintenance job, and a guard so only the coordinator
      polls Telegram (D-079…D-082). Standalone (one computer) stays the default.
      New API (`/api/v1/bot-factory/*`, `/api/v1/mesh/*`), two RU-first UI pages
      and tests; no new phases.
- [x] **Notification Center + Tray Agent + Editorial Workspace (v1.4.0,
      released)**: a durable, queryable **Notification Center** (categories,
      priorities, per-category routing to owner DM / notification group / Windows
      toast, quiet hours for non-urgent messages, anti-spam aggregation and a
      history; D-084…D-086); the **TCMS Tray Agent** so the portable app runs with
      no console window (hidden start, `/health` readiness, bounded restart
      backoff, optional Startup-folder autostart, secret-free snapshot surfaced in
      Diagnostics; D-087…D-088); and the **Editorial Workspace**, a linked Telegram
      forum supergroup where the owner, editors and moderators work the same
      publication queue as the Web UI (verified bot rights, roles by numeric
      Telegram id, optimistic-version moves and a full audit trail;
      D-089…D-091). New API (`/api/v1/notifications/*`, `/api/v1/editorial/*`),
      two RU-first UI pages and tests; no new phases.
- [ ] Optional (remaining, non-blocking): a full automated BotFather Mini App
      flow (the one-click menu-button registration exists, D-054); richer
      analytics; additional AI backends; a reliable permissively-licensed TDATA
      converter adapter (D-070). No new phases are planned — see
      `agent/NEXT_TASK.md` (maintenance / optional extensions).

---

## Release

- **v1.8.2 (2026-10-11):** a **Web Wrapper Hub practical-verification patch**
  (D-115). It exercises the wrapper pipeline end to end on a deterministic
  **local fixture site** (real HTTP + HTML; index/search, article, extract, login
  and 500 pages) with **no external site, account, key or AI credential**, and
  fixes a real defect the genuine Playwright runtime had: `extract()` read `href`
  from the matched node itself, so a container selector (`li.link`, `tr.row`)
  returned empty links. Adds `WrapperDefinition.extract_attrs`, a 7/7 benchmark
  (`agent/WEB_WRAPPER_BENCHMARK.json`) and a skipping real-Chromium test. No new
  features, no schema change, no new runtime dependency. Released via a reviewed
  `develop → main` PR #21 (merge `8542d4c`), tag `v1.8.2`; the Release workflow
  (run `37747125558`) attached the Windows portable ZIP (24 906 383 bytes, sha256
  `f0c6984d…f619`) + `.sha256`.
- **v1.8.1 (2026-10-10):** an **AI Gateway verification patch** (D-114) over
  v1.8.0. It proves the gateway *works* by behaviour and fixes two real defects —
  a `web` provider whose wrapper id does not exist reported `available` (and lost
  its configured name), and `AIRouter._attempt` returned a transient *response*
  without retrying — plus frontend lockfile version drift. No new features. The
  Release workflow (run `37705225761`) attached the Windows portable ZIP
  (24 905 404 bytes, sha256 `0ec6aca1…a9d4`) + `.sha256`.
- **v1.8.0 (2026-10-09):** the **AI Gateway + Web Wrapper Hub** (D-111…D-113) —
  one access layer over many AI providers (OpenAI-compatible, OpenRouter, Google,
  Anthropic, DeepSeek, local Ollama) plus browser **web wrappers** that drive the
  owner's own logged-in session. Strategy-based routing, bounded retries, a
  per-provider circuit breaker and automatic failover; keys sealed and write-only;
  the request journal stores metadata only. Honest availability, no account
  registration and no CAPTCHA/MFA/regional-block or Telegram-limit bypass.
  Released via a reviewed `develop → main` PR #19 (merge `d8c62c1`), tag `v1.8.0`;
  the Release workflow (run `37653661662`) attached the Windows portable ZIP
  (24 904 789 bytes, sha256 `9bb39e4b…d353c`) + `.sha256`.
- **v1.7.0 (2026-10-08):** the **Bot Factory** (v1.3) becomes a **durable creation
  queue** (D-109/D-110). A batch marks its free candidates and the scheduler job
  `bot_factory.create` creates them **one operation per tick**, so the batch is
  restart-resumable, can be stopped/resumed, and never rolls back an
  already-created bot; a failed candidate can be retried or skipped. A
  display-only `token_mask` (`1234…xyz`) is derived from the non-secret numeric
  bot id — the raw managed-bot token is never returned, logged or exported.
  Deep-link batches are not background-ticked (the owner finishes them in
  Telegram). Additive only; no account registration and no Telegram-limit bypass.
- **v1.6.1 (2026-10-07):** a verification patch over v1.6.0 (D-107) — owner-guard
  path normalisation (a leading `//` can no longer skip the guard), the
  `config_sync` capability reports `needs_setup` until a provider is connected,
  and the Google Drive token step is wired into the `/owner` UI. No new features.
- **v1.6.0 (2026-10-07):** an **Owner Auth + Config Sync** vertical slice (D-105/D-106).
  A **local owner profile** (password or PIN) protects the panel with a one-way
  PBKDF2 verifier and an HMAC-signed session token (`X-Owner-Token`; default-on
  middleware, local-first — open until a profile enables protection). A
  **versioned encrypted configuration bundle** (canonical JSON → AES-256-GCM, secret
  denylist) moves settings to a new computer via a local folder or Google Drive
  (app-data scope) — never the DB, sessions or TDATA; conflicts are reported, not
  overwritten. Additive only; no account registration and no Telegram-limit bypass.
- **v1.5.4 (2026-10-06):** the last three **Consistency Auditor** coverage gaps
  (N, O, P) are closed with pure static checks — an unused ORM column, a public
  service class no module references, and a Vue control whose handler is undefined
  or empty. The runtime mutation engine now detects **every** seeded defect:
  **25/25, 100%, 0 false positives**, and `KNOWN_GAP_IDS` is empty. Additive only;
  no new phases; no account registration and no Telegram-limit bypass.
- **v1.5.3 (2026-10-06):** two high-impact **Consistency Auditor** gaps (M, Q)
  closed statically — a setting saved but never read, and a channel-aware module
  that bypasses the Channel Registry; the runtime orphan-setting allow-list made
  honest (88%, 22/25).
- **v1.5.2 (2026-10-06):** the auditor's kill rate is **computed from runtime
  mutation executions**, never declared; silent-failure guard, router/backup/
  notification checks (D-102).
- **v1.5.1 (2026-10-06):** five forensic-audit fixes — false `available`
  capabilities, a swallowed consistency-check failure, a write-only `language`
  preference, runtime-image source-unavailable checks, and `README.md` version
  drift (D-095…D-098).
- **v1.5.0 (2026-10-05):** Capability graph + i18n + Consistency Auditor. Three
  small cross-cutting layers that make the product explain itself honestly: a
  machine-readable **capability graph** (`GET /api/v1/capability-graph`, also
  embedded in the Promotion Wizard and the Dashboard) so every surface agrees on
  what is available now and what still needs setup; a bilingual RU/EN **i18n
  catalog** (`core/i18n.py`) plus a stored `language` preference so wording is
  single-sourced; and a **Consistency Auditor** (`GET /api/v1/consistency`,
  rendered as the Diagnostics "Проверка целостности" panel) whose static checks run
  in CI to catch cross-module drift. Additive only; no new phases; no account
  registration and no Telegram-limit bypass.
- **v1.4.0 (2026-10-05):** Notification Center + Tray Agent + Editorial
  Workspace (D-084…D-091). A durable, queryable Notification Center with
  categories, priorities, per-category routing (owner DM / notification group /
  Windows toast), quiet hours and anti-spam aggregation; the TCMS Tray Agent so
  the portable app runs with no console window (hidden start, `/health`
  readiness, bounded restart backoff, optional Startup-folder autostart); and the
  Editorial Workspace, a linked Telegram forum supergroup where the owner,
  editors and moderators work the same publication queue as the Web UI with
  verified bot rights and a full audit trail. New API
  (`/api/v1/notifications/*`, `/api/v1/editorial/*`), two RU-first UI pages and
  tests; no new phases. Neither feature registers accounts nor bypasses Telegram
  limits. Released from `develop` via a reviewed `develop → main` PR #10
  (merge `306672e`), tagged `v1.4.0`; the Windows portable ZIP + `.sha256` are attached to the GitHub
  Release by the automated Release workflow (D-060).
- **v1.3.0 (2026-10-05):** Bot Factory + LAN Mesh / offline control plane
  (D-077…D-082). Create a set of worker bots for the owner's own channels through
  the official owner-confirmed @BotFather flow, and optionally join several of the
  owner's computers on one local network with no cloud control plane. Standalone
  (one computer) stays the default; neither feature registers Telegram accounts or
  bypasses Telegram limits. No new phases. Released from `develop` via a reviewed
  `develop → main` PR (PR #9, merge `7788125`), tagged `v1.3.0`; the Windows
  portable ZIP + `.sha256` are attached to the GitHub Release by the automated
  Release workflow (D-060).
- **v1.2.0 (2026-10-05):** Content Studio — content sources (Telegram / RSS /
  Atom / manual), deduplication, an explainable cleaner, usage-rights tracking,
  markup validation + Telegram-like preview, inline buttons, per-source
  moderation, multi-channel planning/calendar, and publishing through a
  `PostingProvider` with durable auto-delete and first comments (D-071…D-076).
  No new phases. Released from `develop` via a reviewed `develop → main` PR,
  tagged `v1.2.0`; the Windows portable ZIP + `.sha256` are attached to the
  GitHub Release by the automated Release workflow (D-060).
- **v1.1.0 (2026-10-05):** Account Hub local importer, network routes (proxies),
  donor discovery, the lightweight encoder + ruBERT-tiny2 backend, and the
  bot-only / risk UX (D-065…D-070). No new phases. Released from `develop` via
  reviewed PR #7 (`develop → main`, merge `3438305`), tagged `v1.1.0`; the Windows
  portable ZIP + `.sha256` are attached to the GitHub Release by the automated
  Release workflow (D-060).
- **v1.0.5 (2026-10-04):** product-slice release — bot↔channel **bindings** +
  channel **reaction capabilities** (the reaction planner honours the channel's
  real emoji set), session-free invite **Кампании** with conservative risk modes
  and explainable **donor quality** indicators, **backup delivery destinations**
  (local / Telegram / Google Drive / Яндекс.Диск, credentials sealed), a
  resumable first-run **Setup Wizard**, and a conservative, off-by-default
  **auto-update** (checks + stages a SHA-256-verified file, never auto-installs).
  New API + RU-first UI + tests; Diagnostics gained the new subsystem rows and
  redacted-report sections. No new phases. Published from `develop` via
  reviewed PR #6 (`develop → main`, merge `496598f`), tagged `v1.0.5`; the Windows portable ZIP +
  `.sha256` are attached to the GitHub Release by the automated Release workflow
  (D-060).
- **v1.0.4 (2026-10-04):** startup-robustness patch — a corrupt/unreadable
  database no longer crashes application startup or the **Диагностика** page
  (checks degrade to friendly rows, the report falls back to safe empty sections,
  and the DB row explains recovery; D-062); the Queue page shows plain Russian
  job kind/status labels; `docs/TROUBLESHOOTING.md` gained a damaged-database
  entry. No new phases or features. Published from `develop` via a reviewed
  `develop → main` PR, tagged `v1.0.4`; the Windows portable ZIP + `.sha256` are
  attached to the GitHub Release by the automated Release workflow (D-060).
- **v1.0.3 (2026-10-04):** product-polish patch — the **Diagnostics** page
  (per-component status in plain language), a **redacted diagnostic report**
  (ZIP/JSON/TXT with a server-side secret scan) and **safe maintenance actions**
  (restart scheduler, recheck Telegram, recheck channels, clean up stuck local
  jobs), none of which delete user data (D-061). Also a UI-wording consistency
  pass. Published from `develop` via a reviewed `develop → main` PR (merge commit
  `f18f53a`), tagged `v1.0.3`; the Windows portable ZIP + `.sha256` are attached
  to the GitHub Release by the automated Release workflow (D-060).
- **v1.0.2 (2026-10-04):** release-engineering patch — the Release workflow
  creates/updates the GitHub Release itself and attaches the Windows portable ZIP
  + `.sha256` (D-060), making a `v*` tag a fully automated release with no manual
  fallback; carries the `build_portable.sh` relative-output-path fix (D-059). No
  product/functional changes. Published from `develop` via a reviewed
  `develop → main` PR.
- **v1.0.1 (2026-10-04):** post-1.0 hardening release — versioned Alembic
  migrations, the shared Channel Registry, per-channel analytics, GitHub Actions
  CI, the Mini App setup helper, and reproducible cross-platform portable
  packaging with an automated Release workflow. Version string is
  `1.0.1`. Published from `develop` via a reviewed `develop → main` PR (merge
  commit `d267cf6`), tagged `v1.0.1`; the Windows portable ZIP is attached to the
  GitHub Release. The Release workflow's portable job hit a path bug for a
  relative output dir; the fix landed on `develop` (D-059) and the tag was **not**
  moved (D-050) — the ZIP for `v1.0.1` was built from `d267cf6` and attached
  manually. The next tag (`v1.0.2`) runs the fixed workflow.
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
