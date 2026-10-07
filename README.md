# Telegram Channel Management Suite

A modular, locally runnable suite for managing a Telegram channel: a manager bot,
managed bots, user (MTProto) accounts, audience parsing, invites, automatic
reactions, a rules engine with an optional tiny AI classifier, analytics, a
channel registry, a scheduler, a Web UI / Telegram Mini App, backup/restore, and
portable Windows + VPS/Docker deployment — all from **one codebase**.

> Runs locally on a weak Windows PC (portable, no Python/Node/Docker required for
> end users) and on a VPS via Docker, without a separate "server version".

**Current stable release: `v1.7.0`.** It turns the **Bot Factory** into a
durable **creation queue**: a batch can create its worker bots **one at a time**
through the scheduler, so it survives a restart and can be closed safely while
already-created bots are never rolled back. A failed candidate can be retried or
skipped, and each candidate exposes a display-only masked token (`1234…xyz`) —
the raw token is never returned, logged or exported. The release is additive: no
new account registration and no Telegram-limit bypass.
**v1.6.1** is an independent verification patch of
v1.6.0 (owner-guard path normalisation, `config_sync` state, Google Drive UI).
**v1.6.0** adds an **Owner Auth + Config Sync**
vertical slice: a **local owner profile** (password or PIN) that protects the
panel with a one-way PBKDF2 verifier and a signed session token, and an
**encrypted configuration bundle** that moves your settings to a new computer
without ever copying the SQLite database, Telegram sessions or TDATA. Sync uses
**Google Drive (app-data scope, least privilege)** or a local folder, and it
refuses to overwrite on a conflict instead of a blind last-write-wins. Owner Auth
is **local-first**: while no owner profile exists, the panel stays open exactly as
before. It adds no account registration and no Telegram-limit bypass. It keeps the
**Consistency Auditor** (now also auditing config-sync providers and the bundle's
secret denylist, D-106), the **Capability Graph**, and the **localized message
catalog** (RU/EN, single-sourced in `core/i18n.py`). See Status below.

## What it does

- **Owner Auth** — one local owner profile (password or PIN) protects the panel
  with a one-way PBKDF2 verifier and a signed session token. It is local-first:
  while no profile exists the panel stays open, exactly as before.
- **Config Sync** — move your settings to a new computer as a versioned encrypted
  bundle (AES-256-GCM) via a local folder or Google Drive (app-data scope). Never
  the database, sessions or TDATA; a conflict is reported, not overwritten.
- **Manager Bot** — control the suite from Telegram (admin whitelist, notifications).
- **Managed Bots** — add/health/remove Telegram bots; tokens sealed at rest.
- **Bot Factory** — plan a set of worker bots, check usernames with Telegram,
  create each through the official @BotFather flow and adopt it, then bind it to
  your own channel. It never registers accounts or bypasses Telegram limits.
- **Notification Center** — every important event is recorded (category,
  priority, destination, delivery status) and can be routed to the owner DM, a
  notification group or a Windows toast; quiet hours hold non-urgent messages and
  identical messages are aggregated so you are never spammed.
- **Editorial Workspace** — a linked Telegram forum supergroup with one topic per
  queue status; the suite owns the queue order, cards mirror it as inline
  buttons, roles are by numeric Telegram id and the bot's rights are verified (a
  room is only "ready" after Telegram confirms them).
- **Tray Agent** — an optional Windows tray icon that starts the backend hidden,
  waits for `/health` (never a fixed sleep), supervises it with a bounded restart
  backoff and can register itself in the Startup folder (no admin needed).
- **Bot ↔ channel bindings** — connect a bot to a channel, verify its rights and
  the channel's available reactions (bot-only, no account needed).
- **User Sessions / Account Hub** — MTProto accounts with an interactive auth
  wizard, plus local import of `.session`, `.session` + JSON, StringSession and
  optional TDATA (owner-scoped; auth files are never logged or shown).
- **Network routes (proxies)** — optional per-account connection routes; a route
  never bypasses Telegram limits.
- **Audience** — parse members of channels/groups, search, tag, export.
- **Donor discovery** — search donor channels by topic; results are candidates
  that become sources only on an explicit click.
- **Invite Manager** — build, dry-run, approve and run invite campaigns.
- **Кампании** — invite-link promotion with the manager bot only (no account) and
  explainable source-quality indicators.
- **Reaction Manager** — reaction profiles, emoji weights, delays, simulation;
  the AI's communicative intent only *narrows* the allowed emoji.
- **Rules Engine** — per-category rules with allowed/preferred/forbidden emoji.
- **Content Studio** — collect material from Telegram / RSS / Atom / manual
  sources, deduplicate, clean, check usage rights and Telegram markup, add inline
  buttons, preview it like Telegram, then publish or schedule it to your own
  channels (with optional auto-delete and first comments). Nothing is ever
  published without your confirmation.
- **Tiny AI** — optional local classifier (rules-only mode is fully supported);
  a lightweight local **encoder** mode works with no model download, plus an
  optional **ruBERT-tiny2** encoder with a one-click, verified install.
- **Analytics** — per-channel content, reactions, audience and takeaways; works
  without a user account (and says so honestly).
- **Channel Registry** — one shared channel identity for every module.
- **Mini App** — the same SPA opens inside Telegram (one-click setup helper).
- **Diagnostics** — per-component status in plain language + a redacted report.
- **Setup Wizard** — a resumable first-run guide that reflects real system state.
- **Auto-update** — off-by-default, checks/downloads a SHA-256-verified release.
- **Backup / Restore** — data backups, reviewable config export/import and
  optional delivery destinations (local / Telegram / Google Drive / Яндекс.Диск).
- **Windows Portable** — unpack, run `run.bat`, open the Web UI (zero setup).
- **Docker / VPS** — one compose file, optional Caddy TLS overlay.
- **LAN Mesh (optional)** — join several of your own computers on one local
  network with no cloud control plane; Standalone (one computer) is the default.
  It never enables Telegram-limit bypass or mass account registration.

## Documentation (project memory)

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system fits together
- [docs/ROADMAP.md](docs/ROADMAP.md) — phased plan (all phases complete)
- [docs/SETUP.md](docs/SETUP.md) — install & run (local / portable / Docker)
- [docs/SECURITY.md](docs/SECURITY.md) — secret & limits policy
- [docs/UI.md](docs/UI.md) — UI/UX principles
- [docs/API.md](docs/API.md) — REST contract
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — fixes & recovery

## Agent / developer state

Persistent memory so work can continue across sessions:

- [agent/CURRENT_STATE.md](agent/CURRENT_STATE.md) — what exists now
- [agent/NEXT_TASK.md](agent/NEXT_TASK.md) — what to do next
- [agent/DECISIONS.md](agent/DECISIONS.md) — locked architecture decisions
- [agent/CHANGELOG.md](agent/CHANGELOG.md) — history

## Status

**PHASE 0–11 complete.** The suite is feature-complete against the planned
roadmap and shipped as **v1.0.5** (the roadmap has no open phases; remaining work
is maintenance / optional extensions). Post-1.0 additions include versioned
Alembic migrations (replacing `create_all`), the shared Channel Registry,
per-channel analytics, GitHub Actions CI, a one-click Mini App setup helper,
reproducible cross-platform portable packaging (a versioned Windows ZIP is built
and attached to each GitHub Release automatically), the **Diagnostics** page
with a **redacted diagnostic report** for support, and a **product slice**:
bot↔channel bindings + reaction capabilities, session-free invite **Кампании**
with source-quality indicators, **backup delivery destinations**, a first-run
**Setup Wizard**, and a conservative, off-by-default **auto-update**.
**v1.1.0 (released)** adds the multi-format **Account Hub** local importer
(`.session`, `.session` + JSON, StringSession, optional TDATA; owner-scoped and
secret-safe), optional per-account **network routes (proxies)**, **donor
discovery** (candidate proposals only), a **lightweight local encoder** classifier
mode plus the optional **ruBERT-tiny2** backend with a verified one-click install,
and the **bot-only / risk UX** (session-free analytics, an adaptive wizard and
intent-narrowed reactions).
**v1.2.0 (released)** adds **Content Studio** (the v1.2 content-studio
foundation): content sources (Telegram / RSS / Atom / manual) with deduplication,
a deterministic cleaner with an explainable, cancellable preview, usage-rights
tracking with an attribution block, Telegram markup validation and a
Telegram-like preview, inline button sets, per-source moderation (blocked
keywords + quiet hours), multi-channel planning/calendar, publishing through a
`PostingProvider` (bot by default; a user account only in the expanded mode),
durable auto-delete and first comments, and a bounded, restart-safe posting tick.
**v1.3.0 (released)** adds the **Bot Factory** (plan a set of worker bots, check
usernames with Telegram, create each bot through the official owner-confirmed
@BotFather flow and adopt it, then bind it through the existing binding rules;
D-077/D-078) and the **optional LAN Mesh / offline control plane** (deterministic
identity, bounded broadcast discovery + manual peers, one-time-code pairing,
deterministic coordinator election, fencing leases, a `mesh.tick` maintenance job
and a guard so only the coordinator polls Telegram; D-079…D-083). Standalone (one
computer) stays the default; neither feature registers accounts or bypasses
Telegram limits.
**v1.5.0 (released)** adds the **Capability Graph** (one machine-readable view
of what the product can do and what each capability requires; unimplemented
capabilities are reported honestly as "Не реализовано" rather than "Доступно"),
the **localized message catalog** (RU/EN, single-sourced in `core/i18n.py`, with
the language preference selectable in Settings) and the **Consistency Auditor**
(cross-module drift detection surfaced in Diagnostics, with a failed check
reported as an error instead of being silently skipped). It adds no account
registration and no Telegram-limit bypass.
**v1.7.0 (this release)** turns the **Bot Factory** (v1.3) into a durable
**creation queue**: `enqueue_candidates` / `run_queue_once` advance the batch
through the scheduler job `bot_factory.create` — one creation operation per tick,
restart-resumable. A batch can be stopped and resumed; a failed candidate can be
retried or skipped; already-created bots are never rolled back. Each candidate
carries a `queue_state`/`attempts` and a display-only `token_mask` (`1234…xyz`)
derived without decrypting the sealed token. Deep-link batches are not
background-ticked (the owner finishes them by hand). It adds no account
registration and no Telegram-limit bypass.
**v1.6.1** is a verification patch over v1.6.0: the owner guard
now normalises the request path before deciding whether a path is protected (a
leading `//` can no longer skip the guard while the router still matches it), the
`config_sync` capability reports `needs_setup` until a provider is connected
(never a false `partial`), and the `/owner` Google Drive flow has the missing
token field wired to the existing connect endpoint. No new features.
**v1.6.0** adds **Owner Auth + Config Sync**: a local owner
profile (password/PIN) that protects the panel, and an **encrypted settings
bundle** that carries your configuration to a new computer via Google Drive
(app-data scope) or a local folder — never the database, sessions or TDATA. It is
local-first (open until an owner profile enables protection) and reports sync
conflicts instead of overwriting. Three new Consistency Auditor checks guard the
sync providers and the bundle's secret denylist. It adds no account registration
and no Telegram-limit bypass.
**v1.5.4** closed the **last three Consistency Auditor gaps** with
static detectors — an **unused DB field** (N), a **backend service without a
caller** (O) and a **frontend control without behaviour** (P) — proven by the
**runtime mutation engine**, which computes the kill rate from real executions:
**100% (25/25 seeded defects), 0 critical or high misses, 0 false positives**.
`KNOWN_GAP_IDS` is now empty. It adds no account registration and no
Telegram-limit bypass.
**v1.5.3** closed two high-impact **Consistency Auditor** gaps with static
detectors — a setting that is **saved but never read** (M) and a **channel-aware
module that bypasses the Channel Registry** (Q) — proven by the runtime mutation
engine (88%, 22/25).
**v1.5.2** proved the **Consistency Auditor** actually detects the breakages it is
meant to catch ("Проверка проверяющего"): a meta-audit harness seeds defects into
an isolated copy of the source tree and asserts each is reported, closing four
detection gaps and adding router/backup/notification checks; it also fixed a real
silent failure in the runtime channel-aware check.
See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Deployment modes

- **Local dev** — `python -m backend.app.main` (http://127.0.0.1:8000).
- **Windows portable** — unpack the ZIP, run `run.bat`; no Python/Node/Docker.
- **VPS / Docker** — `docker compose -f docker/docker-compose.yml up -d --build`,
  with an optional Caddy TLS overlay (`docker/docker-compose.proxy.yml`).
  See [docs/SETUP.md](docs/SETUP.md).

## Quick start (development)

```bash
cp .env.example .env          # then set APP_SECRET_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
python -m backend.app.main    # http://127.0.0.1:8000
```

## Security

Never commit `.env`, bot tokens, API hashes, session files, passwords, or keys.
See [docs/SECURITY.md](docs/SECURITY.md).
