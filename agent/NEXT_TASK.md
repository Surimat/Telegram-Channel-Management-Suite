# NEXT TASK ‚Äî Telegram Channel Management Suite

> **The single active task.** A new agent resumes here after reading
> `agent/CURRENT_STATE.md`, `agent/DECISIONS.md` and `docs/ROADMAP.md`.

**Updated:** 2026-10-17
**Status:** **v2.1.0 is published as a GitHub Pre-release (candidate tag
`v2.1.0-rc.1`, 2026-10-15); the latest stable release is v2.0.1 (2026-10-11).**
This candidate ships the six committed stages **D-123…D-128** on top of v2.0.1 —
D-123 (Personal Account Safety), D-124 (Operational Module Registry), D-125
(Bot-lifecycle recovery and adoption), D-126 (Content Pipeline Consolidation),
D-127 (Channel Overview) and D-128 (End-to-end Setup Wizard). It is built from
`develop` and published as a **pre-release for testing**, not as the Latest
release; the previous stable `v2.0.1` is unchanged. Version string is **2.1.0**.
The pre-release candidate itself is recorded as **D-129**.

After the candidate, **D-130 (Reaction Manager channel-post fix)** was committed
on `develop`: the manager bot now reads real `channel_post` updates, stores the
post with its real Telegram `chat_id`/`message_id` and plans the reactions; a post
without a real message id is never queued. Additive; it changes no version, tag,
PR or release. The owner verifies it by double-clicking `CHECK_REACTIONS.bat` in
the portable build — plain-language PASS/FAIL, runs on the embedded Python, no
terminal and nothing to install. `.github/workflows/portable-dev.yml` builds that
test ZIP from `develop` and uploads it as an Actions artifact (no tag/PR/release).

Released as a GitHub **Pre-release** from `develop` (tag `v2.1.0-rc.1`, commit
`a148d7a`); the Release workflow (run `38720969696`) created the Pre-release and
attached the Windows portable ZIP (**25 032 877 bytes**, sha256
`8f9624a1…6644`) + `.sha256`. `main` HEAD = `21f2d01` (= `origin/main`, tag
`v2.0.1`, the latest stable release); `develop` carries D-123…D-128 and is
deliberately not pinned to a SHA because it moves with every commit. Release ZIP
scan: no `.session`/TDATA/DB/model.

Version string is **2.1.0** across `backend/app/__init__.py`, `pyproject.toml`,
`frontend/package.json` + lock.

### Active task — none

**No stage is in progress.** The latest completed stage is the **Reaction Manager
channel-post source** (D-130), committed on `develop` after the `v2.1.0-rc.1`
pre-release; before it, the **End-to-end Setup Wizard** (D-128), Channel Overview
(D-127), Content Pipeline Consolidation (D-126), D-125, D-124 and D-123 — the six
D-123…D-128 stages are shipped in the `v2.1.0-rc.1` pre-release and D-130 is not
in any tag. Release only when the owner asks (D-060).

### Completed stage — End-to-end Setup Wizard (D-128, shipped in the v2.1.0-rc.1 pre-release)

**Goal:** one **guided, resumable** flow that takes a fresh install to a working
existing channel, with a **real** per-step verification. `SetupWizardService`
(`backend/app/services/setup_wizard.py`) renders the ordered steps `app` →
`channel` → `bot` → `modules` → `content` → `queue` → `readiness`, **reusing** the
existing services rather than reimplementing them: `services/setup_checks.py` for
the local program checks, `ChannelRepository` for the canonical channel identity
(D-051/D-055) and the authoritative module map (D-124), and the Content Studio
services only for the explicit test publication. The final readiness gate reads
`services/channel_overview.py` (D-127), so there is one status system, not two.

**Honesty.** A step's status is the **stored result of a real server check**
(`SetupWizardStep`, migration
`20261016_0900_a7b8c9d0e1f2_v2_0_setup_wizard.py`): `verified` = the check ran and
passed, `pending` = it ran and failed, `unchecked` = it was never run. Opening the
state endpoint writes nothing and marks nothing done; missing data or an
un-runnable check reports `unchecked`/`failed`, never `verified`. The wizard itself
performs no Telegram action; the only publish is
`POST /api/v1/setup-wizard/test-publication`, which refuses unless the request sets
`confirmed` **and** the stored `bot` and `content` checks passed, then publishes
one already-prepared material to the default channel through the existing posting
path. No account is registered and no Telegram limit is bypassed.

**Wiring.** API `GET /api/v1/setup-wizard`, `POST /api/v1/setup-wizard/steps/{key}/run`,
`POST /api/v1/setup-wizard/test-publication` (`api/v1/setup_wizard.py`,
`api/schemas/setup_wizard.py`, DI `get_setup_wizard_service` in `api/deps.py`);
UI `/setup-wizard` page (`frontend/src/views/SetupWizardView.vue`, router + nav
wired; types/methods in `frontend/src/api/client.ts`).

**Guard:** `tests/test_setup_wizard.py` (20 tests) locks the ordered steps, the
never-infer statuses, the module/channel readiness and the confirmed-only test
publication, plus the test-publication happy path (a prepared item is published
rather than re-grabbed). The full flow was verified end to end offline through the
real `/setup-wizard` UI (7/7 steps, `ready=true`). No version bump. See
`agent/DECISIONS.md` D-128.

### Completed stage — Channel Overview (D-127, shipped in the v2.1.0-rc.1 pre-release)

**Goal:** one **read-only** aggregation that answers “how is each channel doing?”
across every module. `ChannelOverviewService`
(`backend/app/services/channel_overview.py`) builds, per channel, its identity +
verification status, the authoritative module map (D-124), bot↔channel bindings,
audience sources, invite jobs, bot-onboarding batches, bot-factory batches,
content items/publications, the content pipeline and the durable job queue into
`OverviewSection`s, plus a suite-wide attention summary and a channel event
section. It never writes a row, queues a job or calls a Telegram provider, and it
reads the canonical channel identity via `ChannelRepository` (D-051/D-055).

**Wiring.** API `GET /api/v1/channels/overview` (`ChannelOverviewOut` in
`backend/app/api/schemas/channels.py`; DI `get_channel_overview_service` in
`backend/app/api/deps.py`); UI `/channel-overview` page
(`frontend/src/views/ChannelOverviewView.vue`, router + nav wired; types/method in
`frontend/src/api/client.ts`). Each area carries an honest attention level
(`ok`/`info`/`warning`/`error`) with a human reason (a `needs_review` item is a
warning, a ready bot binding is `ok`).

**Guard:** `tests/test_channel_overview.py` (20 tests) locks the attention levels,
the section structure and that `/summary` is not shadowed by `/{id}`. No schema
change, no version bump. See `agent/DECISIONS.md` D-127.

### Completed stage — Content Pipeline Consolidation (D-126, committed `0b65bf3` on `develop`, shipped in the v2.1.0-rc.1 pre-release)

**Goal:** eliminate the duplication between `backend/app/services/content_service.py`
and `backend/app/services/content_pipeline.py` and leave a **single authoritative
content-processing process**. Do **not** add new features and do **not** cut a
release until the owner asks (D-060).

**Architecture study (verified from real code + git, section 1 «Изучи архитектуру»):**

- **`ContentService`** (`content_service.py`) owns **receive**: sources CRUD,
  `grab` (the one dedup path: source hash / source message id / content hash /
  media hash), items, `clean_preview/apply_clean/revert_clean`, rights/attribution
  (`rights_warning`, `effective_text`, `attribution_block`, `publish_text`),
  moderation settings (blocked keywords + quiet hours) and the dashboard.
  FastAPI dependency `get_content_service` wires the Telegram `SessionProvider`
  resolver; the per-request session is shared with the pipeline service.
- **`ContentPipelineService`** (`content_pipeline.py`) owns **processing**:
  `classify`, `detect_language`, `translate`, `process` (AI Gateway + failover),
  `moderate`, `apply_rule_actions` and the secret-free `content_operations` audit.
- **`PostingService`** (`posting_service.py`) owns **publish**: `plan`/`schedule`/
  `calendar`/`publish`/`retry`/`tick`/comment/auto-delete; it already reuses
  `ContentService.publish_text` via `_effective_text`.
- **Real duplication found:** two AI text-transformation paths — the legacy
  `ContentService.rewrite_preview/apply_rewrite` (local `ContentRewriteService`)
  and the pipeline (`process`/`translate`) — both setting `cleaned_text` +
  `content_hash`, i.e. two implementations of "transform item text". Also two
  item-load helpers (`get_item` vs `_require_item`) with different error types.

**Consolidation decision (respects LOCKED D-116):**

1. **`ContentPipelineService` is the single content-processing engine** — all AI
   text transformation lives there. The v1.2 `rewrite_preview`/`apply_rewrite`
   moved into it (the local `ContentRewriteService` is unchanged and still the
   honest "Рерайт недоступен" source).
2. **`ContentService.rewrite_preview`/`apply_rewrite` now delegate** to the
   pipeline and map `PipelineError` → `ContentError`, so the two engines cannot
   drift while the v1.2 API contract (`/rewrite`, `/rewrite/apply`, error
   semantics, mode titles) stays exactly the same.
3. `ContentService` stays the **receive/dedup owner** (`grab`) and `PostingService`
   stays the **publish owner** — a legitimate split that D-116 already blesses, not
   duplication. Neither engine is deleted.

**Guards:** `tests/test_content_consolidation.py` (7 tests) proves the single path
(the `/rewrite` contract delegates — monkeypatched spy), the whole path
(grab → process → plan → tick → publish uses the processed text), restart
idempotency, translation/target survival, AI-failure recovery, the v1.2 API
contract and the D-124 module gate. Not released; release only when the owner asks.

### Completed stage — Bot-lifecycle recovery and adoption (D-125, committed `e4002f0` on `develop`, shipped in the v2.1.0-rc.1 pre-release)

- **Recovery service.** `backend/app/services/bot_lifecycle.py`
  (`BotLifecycleService.recover()` → `LifecycleRecoveryResult`) calls the recover
  method each durable queue already owns: `BotFactoryService.recover()` puts a
  `RUNNING` factory row back to `QUEUED`, and `BotOnboardingService.recover()` puts
  a `VERIFYING` onboarding row back to `QUEUED`. The lifespan hook in
  `backend/app/main.py` runs it once on startup, so a killed factory creation or
  onboarding verification resumes instead of hanging.
- **Adoption service.** `BotLifecycleService.adopt_managed_bot()` delegates to
  `BotFactoryService.adopt_managed_bot(telegram_id, username=..., title=...)`
  (→ `AdoptionResult`), which adopts the Telegram id into the matching candidate
  and **never creates a duplicate `Bot` row**. A duplicate `managed_bot` update is
  a no-op; an unknown username is ignored (never searched for or imported, D-070).
- **Runtime handler.** `ManagerBotRuntime._handle_managed_bot()` in
  `backend/app/manager/runtime.py` routes a `managed_bot` update through the
  adoption service and settles the deep-link batch once no candidate remains
  waiting.
- **Secret-free notification.** `BotLifecycleService._emit_adopted()` publishes a
  best-effort “bot created” notification (no token, no id leak).
- **Queue helper.** An enqueue-unless-active helper in
  `backend/app/services/queue_service.py` returns the existing active job instead
  of double-queuing.
- **Provider seam.** `backend/app/providers/aiogram_bot.py` + `backend/app/providers/types.py`
  surface the `managed_bot` update (aiogram `ManagedBotCreated`/`Updated`, field
  alias `bot_user`/`bot`).
- **UI wiring.** `frontend/src/views/BotFactoryView.vue` wires the previously-unused
  `api.adoptFactoryBot` into a deep-link **confirmation** form (owner enters the
  created bot's `@username` + numeric id; then the bot is registered, its token
  fetched and it is bound to the selected channel).
- **Fixed a pre-existing defect.** `BotFactoryService.__init__` stored the injected
  binding service in `self._binding_service`, shadowing the `_binding_service()`
  method, so `bind_created()` raised `TypeError` and `/batches/{id}/bind` was dead
  at runtime; the field is renamed `_binding_override`.

**Remaining:** nothing — D-125 is committed on `develop` (`e4002f0`) and the full
suite is green. Guards live in
`tests/test_bot_lifecycle_consolidation.py` (14 tests: duplicate-queue prevention,
idempotent adoption, crash recovery, and the runtime handler path) and
`tests/test_bot_factory_api.py::test_deeplink_adopt_registers_then_tokens_and_binds`
(adopt → token → bind over the real HTTP API). The stage is shipped in the
`v2.1.0-rc.1` pre-release; release only when the owner asks (D-060).

### Completed stage — Personal Account Safety (D-123, on `develop`, shipped in the v2.1.0-rc.1 pre-release)

A safety stage that makes an accidental action through the owner's personal
Telegram (MTProto) account impossible unless the owner opts in. Committed on
`develop` (`9295d9c`, `622053c`, `43e1cca`), not yet released. Master switch
`personal_account_enabled` (default **OFF**) blocks all MTProto work at the single
chokepoint `SessionService.provider_for()`; `invites_enabled` (default **OFF**)
gates bulk invitations and a rolling 24-hour per-account ceiling pauses a run
without overshooting. Additive migration `20261015_0900_f6a7b8c9d0e1`.
Guards: `tests/test_personal_account_safety.py`. See D-123 in `agent/DECISIONS.md`.

### Completed stage — Operational Module Registry (D-124, on `develop`, shipped in the v2.1.0-rc.1 pre-release)

**The per-channel module registry is now authoritative server-side.** It was
partially wired before; disabling a module did not actually stop the work. It is
now enforced on **every** launch path, not just a few API guards:

- **Service of record:** `backend/app/services/channel_modules.py`
  (`ChannelModuleGuard`, `effective_modules`, `parse_modules`), read/written by
  `ChannelService.modules_of`/`set_modules`. A never-configured channel keeps all
  modules enabled; an unknown module name is ignored.
- **Gated paths:** reactions (`ingest_post`, `plan_post`, and the durable
  `execute_reaction_job` tick — which also resolves the registry channel from the
  post's channel username for legacy/auto-ingested posts); audience (`add_source`,
  `update_source`, `start_scan`/`resume_scan`, plus the `check_source`/`preview_scan`
  probes);
  invites (`preview`, `create_job`, `start_job`/`resume_job`, `run_tick`);
  analytics.
- **Retire, don't crash:** a blocked durable job is retired honestly (reaction →
  `SKIPPED`, scan → `PAUSED`) without contacting Telegram; a blocked call is a
  friendly `403` envelope, never a 500.
- **Never replaces a real check:** the D-123 personal-account switches and the
  real Telegram permission probe still decide whether an action is allowed.

Guards: `tests/test_channel_modules.py`, `tests/test_reaction_service.py`. See
D-124 in `agent/DECISIONS.md`.



### Completed stage ‚Äî v2.0.1 shipped (2026-10-11)

**Previous release — v2.0.1 RELEASED (2026-10-11).** It is a patch over v2.0.0 that adds a keyless-free **image understanding** (vision) path through the **Kilo Gateway** free model (D-122), integrated additively through the existing AI Gateway ‚Äî **opt-in and off by default**, best-effort, with an honest failover so a rate limit or outage never loses material. It completes the three agreed v2.0 stages (an **AI Gateway** over many providers including keyless-free **text**, **image generation** and now **image understanding**; browser **web wrappers**; a per-content **Target Language**; **mass bot-to-channel onboarding**; **Content Operations 2.0**; and a **hidden (windowless) background launch**). Additive only ‚Äî no account registration and no Telegram-limit bypass. Version strings read **2.0.1**.

### Next stage (factual)

**No stage is in progress.** The six stages above (D-123…D-128) are committed on
`develop` and shipped in the `v2.1.0-rc.1` pre-release. Keep the gates green; for a
**stable** release (only when the owner asks, D-060): branch/review a
`develop → main` PR from the current `develop` tip, tag the merge commit, and let
the Release workflow attach the Windows portable ZIP. The non-blocking optional
items (a full automated BotFather Mini App flow, richer analytics, additional AI
backends, a permissively-licensed TDATA converter, D-070) remain, but only if the
owner asks.

Six committed stages are sitting on `develop` (D-123 Personal Account Safety,
D-124 Operational Module Registry, D-125 Bot-lifecycle recovery and adoption,
D-126 Content Pipeline Consolidation, D-127 Channel Overview, D-128 End-to-end
Setup Wizard) and are rolled up into the `v2.1.0-rc.1` pre-release; a future stable
release window promotes them.

**v2.0 completion gates added this cycle:** `tests/test_content_pipeline_e2e.py`
and `tests/test_bot_onboarding_e2e.py` (end-to-end integration), a separate
`browser-tests` CI job (Playwright + Chromium, must not skip), and
`tests/test_windows_hidden_console.py` (the no-console Windows launch). A
post-v1.9.0 memory reconciliation added release-hygiene guards in
`tests/test_meta_audit.py` ¬ß6; the meta-audit prose in `docs/ARCHITECTURE.md`
(32 mutations / 8 controls) is guarded by
`test_architecture_doc_meta_audit_counts_match_report`.

### –ó–∞–≤–µ—Ä—à—ë–Ω–Ω—ã–µ —ç—Ç–∞–ø—ã v2.0 (released in v2.0.0)

1. **Web Wrappers + free text & image-generation AI providers ‚Äî COMPLETE.**
   - **Stage 1 ‚Äî free-first providers + honest capabilities (D-117/D-118).**
     `PollinationsProvider` (keyless free text), `Llm7Provider` (llm7.io),
     `PollinationsImageProvider` (`pollinations_image`, keyless free image
     generation, off by default), the model-capability catalog
     (`ai/gateway/catalog.py`), idempotent provisioning (`POST /provision`) and
     browser preflight. Honesty: a key is required only for an `api_key` provider
     with no key; session expiry is failover, not a bypass. `GET /operations`
     reports `image_generation` by kind. Tests: `tests/test_v2_ai_providers.py`.
   - **Stage 2 ‚Äî free vision (image understanding): CONFIRMED 2026-10-11 (D-122).**
     A keyless-free image-understanding path exists: the **Kilo Gateway** free
     pool (`api.kilo.ai/api/gateway`, model `dots-studio/dots-3-note-preview:free`)
     describes an image with **no key and no account** ‚Äî verified on two distinct
     generated PNGs and reproduced 3√ó. It is integrated **additively through the
     existing gateway** (`KiloGatewayProvider` + `kilo_gateway` registry kind +
     catalog entry + provisioning default), **opt-in and best-effort** (disabled
     by default; a rate limit/outage fails over, never loses material). Still no
     challenge bypass and no bundled key. Tests: `tests/test_v2_ai_providers.py`;
     opt-in live probe `tests/test_kilo_free_vision_live.py`
     (`TCMS_LIVE_KILO_VISION=1`).
2. **Target Language ‚Äî COMPLETE.** `backend/app/services/content_language.py`,
   migration `20261013_0900_d4e5f6a7b8c9_v2_0_target_language.py`,
   `tests/test_target_language.py`.
3. **Mass Bot-to-Channel Onboarding ‚Äî COMPLETE (D-120).**
   `services/bot_onboarding.py`, migration
   `20261014_0900_e5f6a7b8c9d0_v2_0_bot_onboarding.py`, scheduler job
   `bot_onboarding.tick`; UI `BotOnboardingView.vue`; `tests/test_bot_onboarding.py`
   + `tests/test_bot_onboarding_e2e.py`.
4. **Content Operations 2.0 ‚Äî COMPLETE (D-116).** One pipeline; AI profiles as
   data; mini-AI classifies (never an emoji); migration
   `20261012_0900_c3d4e5f6a7b8_v1_9_content_operations.py`.

### Following cycle (only when the owner asks)

Branch from `develop`, then a reviewed `develop ‚Üí main` PR + tag (D-060).

### –ó–∞–≤–µ—Ä—à—ë–Ω–Ω–∞—è –∑–∞–¥–∞—á–∞ ‚Äî v1.9.0 RELEASED

**v1.9.0 is RELEASED and verified.** The quality gate was run and passed before
the release:

```bash
python -m pytest                                  # 946 passed, 8 skipped
ruff check backend tests                          # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py    # 30/30, 0 false positives
```

The commits on `develop` after the v1.9.0 release were the memory-sync commit, the
release-hygiene guards and the v2.0 stages; those v2.0 stages shipped as
**v2.0.0** (PR #23, merge `926a3b3`), and `develop` is now re-synced to `main`.

**Prior release:** **v1.8.1 (AI Gateway verification patch, D-114) is RELEASED**
via a reviewed `develop ‚Üí main` PR #20 (merge `bc8382b`), tag `v1.8.1`; the
Release workflow (run `37705225761`) created the GitHub Release and attached the
Windows portable ZIP (24 905 404 bytes, sha256 `0ec6aca1‚Ä¶a9d4`) + `.sha256`.
`main` HEAD = `bc8382b`; `develop` re-synced to `bc8382b`.
An independent verification of the v1.8.0 **AI Gateway + Web Wrapper Hub** proved
it *works* (routing, retry, failover, wrapper engine, availability, secret
safety), not merely that it compiles, and fixed two real defects plus a version
drift ‚Äî **no new features**. (1) A `web` provider whose `wrapper_id` has no
matching `WrapperDefinition` was reported `available` and lost its configured
name; it is now forced `unavailable` with an explicit reason and keeps its
configured name so a pinned provider still routes by name. (2) `AIRouter._attempt`
returned a transient *response* without retrying (only raised errors were
retried); it now retries both, bounded by the retry budget, then fails over.
(3) `frontend/package-lock.json` read `1.7.0` while the app read `1.8.0` ‚Äî synced
to the app version and locked by an assertion. New independent gateway behaviour
tests (retry/failover/availability/identity/e2e web answer) and three runtime
meta-audit cases (capability dependency, orphan provider class, unwired control).
Additive only: no account registration and no CAPTCHA/MFA/regional-block or
Telegram-limit bypass. Version strings read **1.8.1**; full suite green (909
passed); `ruff` clean; frontend `vue-tsc` + `npm run build` clean; meta-audit
**30/30, 100%, 0 false positives**.

**Prior release:** **v1.8.0 (AI Gateway + Web Wrapper Hub, D-111‚Ä¶D-113) is
RELEASED** via a reviewed `develop ‚Üí main` PR #19 (merge `d8c62c1`), tag `v1.8.0`;
the Release workflow (run `37653661662`) created the GitHub Release and attached
the Windows portable ZIP (24 904 789 bytes, sha256 `9bb39e4b‚Ä¶d353c`) + `.sha256`.
`main` HEAD = `d8c62c1`. One access layer over many AI
providers (OpenAI-compatible, OpenRouter, Google, Anthropic, DeepSeek, local
Ollama) plus browser **web wrappers** that drive the owner's own logged-in
session, with strategy-based routing, bounded retries, a per-provider circuit
breaker and automatic failover. Keys are sealed and write-only; the request
journal stores metadata only; the wrapper engine stops at a login wall.

**Previous release:** **v1.7.0 (Bot Factory creation queue) is RELEASED** via a
reviewed `develop ‚Üí main` PR #18 (merge `48eecdc`), tag `v1.7.0`; the Release
workflow (run `37634439503`) created the GitHub Release and attached the Windows
portable ZIP (24 853 898 bytes, sha256 `a444bb55‚Ä¶e5af`) + `.sha256`. The Bot
Factory batch is now a **durable creation queue** (D-109): the scheduler job
`bot_factory.create` creates the free candidates **one operation per tick**, so a
batch is restart-resumable and can be stopped/resumed; a failed candidate can be
retried or skipped; already-created bots are never rolled back. A display-only
`token_mask` (`1234‚Ä¶xyz`) is derived from the **non-secret numeric bot id**
(D-110). Deep-link batches are not background-ticked. Additive: no account
registration and no Telegram-limit bypass.

**Previous release:** **v1.6.1** (verification patch) via a reviewed
`develop ‚Üí main` PR #17 (merge `a38823d`), tag `v1.6.1`; the Release workflow (run
`37601801598`) attached the Windows portable ZIP (24 846 601 bytes, sha256
`8b6d7c18‚Ä¶f519`) + `.sha256`. v1.6.1 is a patch over v1.6.0 (Owner Auth + Config
Sync, D-105/D-106); it fixed the owner-guard path-normalisation weakness, the
`config_sync` capability state and the Google Drive `/owner` UI wiring (D-107).

The meta-audit remains a *runtime mutation engine* (D-102) and still detects
**every** seeded defect: **25 total, 25 detected, 0 missed, 100.0%, 0 false
positives, 0 critical/high misses** (`status: clean`); `KNOWN_GAP_IDS` is empty.

Previous release: **v1.5.4** (auditor gaps N/O/P closed, D-104) via a reviewed
`develop ‚Üí main` PR #15 (merge `b219341`), tag `v1.5.4`; the Release workflow (run
`37522394131`) attached the Windows portable ZIP (24 807 288 bytes, sha256
`ff01f787‚Ä¶dc67a`) + `.sha256`.
Previous: **v1.5.1 forensic-audit fixes are released** ‚Äî reviewed `develop ‚Üí main`
PR #12 (merge `f41ebc8`), tag `v1.5.1`; the Release workflow (run `37453582161`)
attached the Windows portable ZIP + `.sha256` (D-060). It fixes five confirmed
discrepancies (D-095‚Ä¶D-098): false `available` capabilities; a consistency check
that raised being silently swallowed; a write-only `language` preference;
source-unavailable checks reported as info in the runtime image; and `README.md`
version drift. Previous: **v1.5.0 Capability graph + i18n + Consistency Auditor is
released** (PR #11, merge `ad24bc6`, tag `v1.5.0`). The roadmap (PHASE 0‚Äì11) is
complete.

---

## Legacy notes: v1.8.0 release (historical ‚Äî superseded by v1.8.2 at the top)

**v1.8.0 was RELEASED** via a reviewed `develop ‚Üí main` PR #19 (merge `d8c62c1`),
tag `v1.8.0`; the Release workflow (run `37653661662`) created the GitHub Release
and attached the Windows portable ZIP (24 904 789 bytes, sha256 `9bb39e4b‚Ä¶d353c`)
+ `.sha256`. `main` HEAD = `d8c62c1`; `develop` re-synced to `d8c62c1`. Nothing is
required to follow up. Do **not** add new large features.

### What shipped (additive, v1.8.0)

- **AI Gateway domain** (`backend/app/ai/gateway/`): types, errors, reliability
  (bounded backoff + per-provider circuit breaker + rate-limit cooldown +
  `HealthStore`), `AIProvider` protocol, `HttpTransport` (httpx + fake), `AIRouter`
  (ordering, retry, failover, `describe()` dry-run), registry (single extension
  point).
- **Providers:** OpenAI-compatible, OpenRouter, Google, Anthropic, DeepSeek,
  Ollama (local) and the `web` wrapper provider.
- **Web wrappers:** `WrapperDefinition` (URL, selectors, extraction, login
  markers) + `WebWrapperEngine` driving the owner's own browser session; returns
  `AUTH_REQUIRED` and stops on a login wall. Optional Playwright runtime + fake.
- **Persistence:** `ai_providers` / `ai_route_settings` / `ai_gateway_requests`
  (+ repository), migration `20261008_1200_b2c3d4e5f6a7_v1_8_ai_gateway.py`.
- **Service + API:** `services/ai_gateway_service.py`,
  `api/v1/ai_gateway.py` (injected via `api/deps.py::get_ai_gateway_service`).
- **UI:** `AiGatewayView.vue` (`/ai-gateway`, "–¶–µ–Ω—Ç—Ä –ò–ò") + nav entry + two help
  topics (`ai_gateway`, `ai_gateway_wrapper`).
- **Guardrails:** `ai_gateway` capability + consistency anchor, i18n keys,
  meta-audit mutations `V_gateway_capability_anchor` and
  `W_frontend_unknown_gateway`.

### Verification

```bash
python -m pytest                 # full suite green
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py         # 27/27, 100%
```

## Previous release: v1.7.0 (Bot Factory creation queue)

**v1.7.0 is RELEASED** via a reviewed `develop ‚Üí main` PR #18 (merge `48eecdc`),
tag `v1.7.0`; the Release workflow (run `37634439503`) created the GitHub Release
and attached the Windows portable ZIP (24 853 898 bytes, sha256 `a444bb55‚Ä¶e5af`).
`main` HEAD = `48eecdc`; `develop` re-synced to `48eecdc`.

### What shipped (additive)

- **Bot Factory durable creation queue (D-109).** `enqueue_candidates` /
  `run_queue_once` / `queue_progress` / `retry_candidate` / `skip_candidate` /
  `cancel_queue` / `resume_queue`; scheduler job `bot_factory.create` (one op per
  tick, restart-resumable); deep-link batches are not background-ticked.
- **API queue endpoints** under `/api/v1/bot-factory/*` plus a `queue` block on
  the dashboard.
- **`token_mask` (D-110).** Display-only, derived from the non-secret numeric bot
  id; the raw token is never returned/logged/exported.
- Migration `20261008_0900_a1b2c3d4e5f6_v1_7_bot_factory_queue.py`; capability
  `bot_factory`, Diagnostics check, Promotion Wizard step, help topic and
  `BotFactoryView.vue` queue UI.

### Verification

```bash
python -m pytest                 # 854 passed
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
```

## Active task (previous): none ‚Äî v1.6.1 released

**v1.6.1 is RELEASED** via a reviewed `develop ‚Üí main` PR #17 (merge `a38823d`),
tag `v1.6.1`; the Release workflow (run `37601801598`) created the GitHub Release
and attached the Windows portable ZIP (24 846 601 bytes, sha256 `8b6d7c18‚Ä¶f519`).
`main` HEAD = `a38823d`; `develop` = `a38823d` (re-synced). Nothing is required to
follow up. Do not add new features.



The v1.6.0 Owner Auth + Config Sync slice was independently verified (D-107). Two
defects and one unwired control were fixed, **additively and with no new features**:

1. **Owner guard path normalisation** ‚Äî a leading `//` (`//api/v1/...`) skipped the
   guard while the router still matched it; `is_protected` now normalises slashes
   and dot segments and matches the allowlist by segment boundary. Verified on a
   real server with `curl --path-as-is`.
2. **`config_sync` capability** ‚Äî dropped `minimal=(owner_auth,)`; it is
   `needs_setup` (never `partial`) until a provider is connected.
3. **Google Drive `/owner` UI** ‚Äî added the missing token field + "save token"
   button calling the existing `syncGoogleConnect` endpoint.

Released as **v1.6.1** (patch) via a reviewed `develop ‚Üí main` PR and tag; the
Release workflow builds the Windows portable ZIP. After the merge, re-sync
`develop` to the merge commit and record the facts here.

### Verification for this patch

```bash
python -m pytest                 # 843 passed expected
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py         # 25/25, 100%
```

## Active task: none ‚Äî v1.6.1 released

There is **no required next task**. v1.6.1 is released (PR #17, tag `v1.6.1`) and
the meta-audit still reaches **100% (25/25, 0 false positives)**.

1. **Optional follow-up (next cycle):** only if the owner asks ‚Äî e.g. a remote
   job-dispatch + worker-execution loop over `MeshTransport`, a reliable
   permissively-licensed TDATA converter, or a dependency-free Windows toast
   backend. Record a decision first.

Do **not** add new large features and do **not** open a new PHASE.

### Owner Auth + Config Sync (v1.6) ‚Äî implemented, do not rebuild

- **Owner Auth:** `core/owner_security.py` (PBKDF2 verifier + bundle key),
  `services/owner_auth_service.py`, `db/models/owner.py`,
  `db/repositories/owners.py`, `api/owner_guard.py` (default-on middleware),
  `api/schemas/owner.py`, `api/v1/owner.py`; `/owner` UI page + `owner_auth` help
  topic.
- **Config Sync:** `services/config_bundle.py` (AES-256-GCM bundle + secret
  denylist), `services/config_sync_service.py`, `providers/config_sync_base.py` +
  `config_sync_local.py` + `config_sync_gdrive.py`, `db/models/config_sync.py`;
  `/api/v1/owner/sync/*`; `config_sync` help topic, capability and wizard step.
- **Migration:** `20261007_1000_f8b2d3e5a7c9` (`owner_identities`,
  `config_sync_state`).
- **Consistency Auditor:** section `5b-2` guards the config-sync providers and the
  bundle's secret anchors.
- **Tests:** `tests/test_owner_auth.py`, `tests/test_config_sync.py`,
  `tests/test_owner_api.py`.

### Meta-audit engine (D-102) ‚Äî implemented, do not rebuild

- **Engine:** `tests/meta_audit/engine.py` ‚Äî `MutationSandbox` (isolated copy),
  `run_mutation`, `run_suite`, `SuiteResult` (derived `detected`/`missed`/
  `kill_rate`/`false_positives`/`critical_misses`/`high_misses`), `write_report`,
  `regression_against`, and a CLI (`python tests/meta_audit/engine.py`).
- **Registry:** `tests/meta_audit/mutations.py` ‚Äî 25 mutations + 8 negative
  controls. No `detected` field anywhere; `KNOWN_GAP_IDS` is empty (all gaps
  closed).
- **Tests:** `tests/test_consistency_mutations.py` (per-mutation runtime
  classification, negative controls, detector-removal proof, new-mutation proof,
  working-tree isolation) and `tests/test_meta_audit.py` (silent-failure guard,
  runtime drift, generated-report provenance + arithmetic, closed-gap M/N/O/P/Q
  regression).
- **CI job `meta-audit`:** runs the engine, then the tests, then asserts the
  working tree has no synthetic defect. It does **not** compare against a
  hardcoded percentage.
- **Detected now (25):** A, B, C, D, E1, E2, F, F2, G, H, I, J, K, K2, L, M, N, O,
  P, Q, R1, R2, S, T, U.
- **Missed / recorded gaps (0):** none.

### Verification for this change

```bash
python -m pytest                 # full suite (green)
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
PYTHONPATH=. python tests/meta_audit/engine.py         # regenerates the report
python -m pytest tests/test_consistency_mutations.py tests/test_meta_audit.py -q
```

### What v1.5.1 adds (do not rebuild)

1. **False capability** ‚Äî `config_sync` returned `available` on an empty install
   with no implementation; `media_conversion` was listed with no ffmpeg tooling.
   Fixed: `Capability.implemented=False` ‚Üí `STATE_NOT_IMPLEMENTED`
   ("–ù–µ —Ä–µ–∞–ª–∏–∑–æ–≤–∞–Ω–æ"), mirrored through the API; `check_capability_implementation()`
   fails CI if any capability claims `implemented` without code.
2. **Silent failure** ‚Äî `ConsistencyAuditor._runtime_findings` and
   `run_static_checks` used `except Exception: continue`. Fixed: a raising check
   now emits an `error` finding `audit.check_failed.<name>`.
3. **Write-only language preference** ‚Äî the `language` setting and i18n catalog
   were never consumed. Fixed: `GET /api/v1/capability-graph` resolves the saved
   preference; Settings gained an RU/EN selector; the help store exposes
   `language`/`availableLanguages`.
4. **Runtime-image false failure** ‚Äî the Docker smoke surfaced that the honest
   no-silent-failure runner reported `overall: fail` in the runtime image (no
   `frontend/`/`docs/` source). Fixed: source-comparison checks report
   `audit.source_unavailable.<name>` as **info** and are skipped; Docker is `pass`.
5. **Doc drift** ‚Äî `README.md` said "Current stable release: `v1.4.0`". Fixed.

### Verification for this change

```bash
python -m pytest                 # 731 passed
ruff check backend tests         # clean
cd frontend && npx vue-tsc --noEmit && npm run build   # clean
```

### What v1.5.0 adds (do not rebuild)

- **Capability graph** (D-092): `services/capability_graph.py`
  (`context_from_db`, `evaluate_all`, `CapabilityState`),
  `api/v1/capability_graph.py` + `api/schemas/capability.py`
  (`GET /api/v1/capability-graph`), embedded in `WizardState.capabilities` and
  rendered on the Dashboard ("–ß—Ç–æ —É–∂–µ –¥–æ—Å—Ç—É–ø–Ω–æ").
- **i18n** (D-093): `core/i18n.py` (RU/EN catalog, `translate`,
  `normalize_language`, `missing_keys`), `services/ui_prefs.py` (`language`
  preference on `/api/v1/help/prefs`).
- **Consistency Auditor** (D-094): `services/consistency_types.py`,
  `services/consistency_checks.py` (static), `services/consistency.py` (runtime),
  `api/v1/consistency.py` + `api/schemas/consistency.py`
  (`GET /api/v1/consistency`), Diagnostics "–ü—Ä–æ–≤–µ—Ä–∫–∞ —Ü–µ–ª–æ—Å—Ç–Ω–æ—Å—Ç–∏" panel. Static
  checks also run in `pytest` (`tests/test_architecture_consistency.py`).

### 1. Release v1.5.0 (done)

Merged via a reviewed PR #11 (`develop ‚Üí main`, merge `ad24bc6`), tagged `v1.5.0`;
the Release workflow (run `37442056281`) created the GitHub Release and attached
the Windows portable ZIP + `.sha256` (D-060). `develop` was synced back to the
merge commit. No direct push to `main`; the `v1.0.0`‚Äì`v1.4.0` tags were not moved
(D-050).

### 2. Release history (done)

v1.4.0 merged via reviewed PR #10 (`develop ‚Üí main`, merge `306672e`), tagged
`v1.4.0`. v1.3.0 merged via reviewed PR #9 (`develop ‚Üí main`, merge `7788125`),
tagged `v1.3.0`. v1.2.0 merged via reviewed PR #8 (`develop ‚Üí main`, merge
`ea6c161`), tagged `v1.2.0`. v1.1.0 via PR #7 (merge `3438305`), tag `v1.1.0`.
v1.0.5 via PR #6 (merge `496598f`) ‚Üí tag `v1.0.5` ‚Üí Release workflow created the
GitHub Release and attached the Windows portable ZIP + `.sha256`. No manual step.
(v1.0.4: PR #5, merge `3f42c3d`, tag `v1.0.4`; v1.0.3: PR #4, merge `f18f53a`,
tag `v1.0.3`.)

### 3. Worker Mesh verification (done ‚Äî verified 2026-10-05)

**Status: PARTIAL.** The LAN Mesh ships the *worker primitives* (the `WORKER`
role, capability advertisement/matching, fencing-token leases that a worker can
acquire/complete, `reclaim_expired`, coordinator election, and the
coordinator-only poller guard in `main.py`), but there is **no remote
job-dispatch + worker-execution loop** ‚Äî `MeshTransport` is used only for the
`/api/v1/mesh/ping` liveness probe, and leases are acquired/completed locally via
`/api/v1/mesh/leases/*`. `MeshMode.VPS_WORKER` is a declared enum/config value
only; there is no PostgreSQL control plane (D-002). So the LAN Mesh is a real
coordination layer for the owner's own computers, **not** a distributed job mesh.
Do not claim remote worker execution until a dispatch + execution loop exists.

### 4. Maintenance / optional extensions (only if the owner asks)

- A remote job-dispatch + worker-execution loop over `MeshTransport` (turning the
  PARTIAL Worker Mesh primitives into real remote execution) ‚Äî only if the owner
  asks; record a decision first.
- A fully automated @BotFather Mini App flow (the one-click menu-button
  registration exists, D-054).
- Short-lived signed session tokens for the Mini App if it is ever exposed beyond
  the owner (D-035).
- A reliable, permissively-licensed TDATA converter adapter behind the existing
  `TdataImportProvider` seam (D-070); today TDATA honestly reports
  `NOT AVAILABLE` when no converter is installed.
- Windows toast delivery currently depends on an optional toast library; a
  bundled, dependency-free toast backend could remove that condition.
- Any new feature explicitly requested by the owner.

### What exists (do not rebuild)

- PHASE 0‚Äì11 complete; `agent/CURRENT_STATE.md` lists what is done (¬ß2, ¬ß2a‚Äì¬ß2h).
- **v1.4.0 Notification Center + Tray Agent + Editorial Workspace (D-084‚Ä¶D-091):**
  `/api/v1/notifications/*` (settings, history, dashboard, test, read) +
  `/api/v1/editorial/*` (rooms, check, members, board, items, move, reorder,
  audit); models `NotificationRecord`/`NotificationDelivery`/`EditorialRoom`/
  `EditorialMember`/`EditorialItem`/`EditorialAuditEntry`; migration
  `20261006_1000_e7a1c9d2f4b8`; the `tray/` package
  (`python -m backend.app.tray.agent`); two RU-first UI pages (`/notifications`,
  `/editorial`).
- **v1.3.0 Bot Factory + LAN Mesh (D-077‚Ä¶D-083):** `/api/v1/bot-factory/*`
  (templates, dashboard, batches, check, create, adopt, tokens, bind) +
  `/api/v1/mesh/*` (status, discover, peers, pairing-code, pair, unpair, probe,
  elect, leases) and two RU-first UI pages (`/bot-factory`, `/mesh`). Models
  `BotBatch`/`BotCandidate`/`MeshNode`/`MeshPeer`/`PairingCode`/`MeshLease`;
  migration `20261005_1600_d5b2e9c3f7a1`; the `mesh.tick` durable maintenance job.
- **v1.2.0 Content Studio (D-071‚Ä¶D-076):** `/api/v1/content/*` (sources, grab,
  items, clean, rewrite, rights, buttons, plan, schedule, publish, retry,
  calendar, dashboard, tick) + the `/content` RU-first UI page. Models
  `ContentSource`/`ContentItem`/`MediaAsset`/`Publication`/`ButtonSet`/
  `CommentPlan`; migration `20261005_1200_c4a1f8b2e6d9`. The `content.posting`
  durable periodic tick drives due work.
- **v1.1.0 (D-065‚Ä¶D-070):** `/api/v1/proxies` (network routes), `/api/v1/discovery`
  (donor discovery), the lightweight encoder + `/api/v1/ai/encoder/*`, the Account
  Hub importer (`/api/v1/sessions/import/detect`, `/import/artifact`,
  `/{id}/risk`), intent-narrowed reactions, bot-only analytics and the adaptive
  wizard. Migrations: `20261004_2047_76d92fe3e70b` (+ posts.intent /
  restriction_count follow-ups).
- **Diagnostics** (v1.0.3, D-061): `/api/v1/diagnostics` + `/diagnostics` page,
  redacted report (json/txt/zip), safe actions.
- Versioned Alembic migrations (D-052); Channel Registry (D-051/D-055);
  manager-bot runtime + permission probe (D-047‚ÄìD-049); reproducible portable
  build + Release workflow (D-056/D-059/D-060).
- Product slice (D-064): `/api/v1/bindings`, `/api/v1/capabilities`,
  `/api/v1/campaigns`, `/api/v1/donors`, `/api/v1/backup/destinations`,
  `/api/v1/promotion`, `/api/v1/update` + RU-first UI.
- Portable build: `scripts/build_portable.sh` (+ `build_win_runtime.py`,
  `win-requirements.lock`). Release process: `docs/RELEASE_CHECKLIST.md`.

### Do NOT

- Do not add Redis/Kafka/Celery/PostgreSQL (D-002 / no-heavy-infra).
- Do not fork the backend; one SPA, one API (D-003 / D-004).
- Do not bundle session files, `tdata`, `.env`, models or secrets into the
  portable package.
- Do not commit downloaded runtimes/binaries to git.
- Do not bypass Telegram FloodWait/privacy/admin limits (D-006); proxies are a
  connection route only (D-065).
- Do not add secrets or database contents to the diagnostics report (D-061) or to
  the notification history (D-084).
- Do not auto-install updates: the updater only checks and stages a verified file.
- Do not search for, download or bulk-register third-party accounts (D-070).
- Do not treat a Telegram username as an identity (editorial roles use numeric
  ids, D-090).

### Verification checklist for any change

```bash
python -m pytest                 # must stay green
ruff check backend tests         # must stay clean
cd frontend && npx vue-tsc --noEmit && npm run build   # outputs to backend/app/static
PYTHONPATH=. python tests/meta_audit/engine.py         # regenerates META_AUDIT_RESULT.json
```
