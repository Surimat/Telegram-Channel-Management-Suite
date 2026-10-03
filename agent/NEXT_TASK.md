# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 2 — Telegram foundation
**Previous phase:** PHASE 1 — completed (runnable backend + UI + tests, committed)

---

## Goal of this phase

Give the system a real, testable connection to Telegram: a manager bot, a Bot
API adapter behind the provider interface, channel connection, managed-bot
support, and a **bot inventory** (model → repository → service → API → UI), all
covered by tests using a **fake provider** (no real account/token required).

## Constraints / reminders

- Follow **D-001**: all Telegram access behind `TelegramBotProvider`; add a
  `FakeTelegramBotProvider` for tests. Domain/services must not import aiogram
  directly.
- Never log or return bot tokens; store tokens encrypted or in `.env` only
  (see `docs/SECURITY.md`, decisions D-009/D-010).
- No FloodWait / privacy bypass (D-006).
- Keep the app runnable at the end (`python -m pytest` passes, app starts).

## Deliverables

### Provider layer
- [ ] `providers/base.py` — `TelegramBotProvider` interface (get_me, get_bot,
      send_message, set_webhook, health).
- [ ] `providers/fake_bot.py` — deterministic fake for tests/dev.
- [ ] `providers/aiogram_bot.py` — real implementation (aiogram) wrapped so the
      interface stays library-agnostic.
- [ ] `providers/registry.py` — resolve providers from configuration.

### Domain
- [ ] `db/models/bot.py` — Bot model: id, kind (manager|managed|reaction),
      username, title, enabled, token_ref (NOT the raw token), health status,
      last_health_at, timestamps.
- [ ] `db/repositories/bots.py`.
- [ ] `services/bot_service.py` — add/enable/disable/remove, health check,
      list managed bots via the manager bot.

### API / UI
- [ ] `api/schemas/bots.py`, `api/v1/bots.py` (list, add, detail, health,
      disable, delete, managed).
- [ ] Frontend `views/BotsView.vue` + route + nav item (plain-language,
      tooltips, confirmation dialogs).

### Tests
- [ ] provider contract tests (fake), bot service tests, bots API tests.
- [ ] ensure no token value can leak into events/logs/API responses.

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`.
- [ ] `git diff` review + security checklist.
- [ ] Commit.

## After PHASE 2

PHASE 3 — Reaction Manager (rules, profiles, scheduler, queue, delays,
simulation, logs, UI). See `docs/ROADMAP.md`.
