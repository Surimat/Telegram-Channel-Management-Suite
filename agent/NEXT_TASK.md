# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 8 — Analytics (content + audience, charts, plain-language Dashboard)
**Previous phase:** PHASE 7 — Tiny AI classifier (completed; commit pending on `develop`).

---

## Repository sync status (2026-10-03)

PHASE 0–7 live on the `develop` branch. A PR (`develop → main`, #1) is open —
**not merged** pending owner confirmation. Continue on `develop` (feature
branches off it as needed). **Never push directly to `main`.**

---

## PHASE 7 — done (checklist)

- [x] `backend/app/ai/` — `Classifier` Protocol + `RulesClassifier`,
      `LlmClassifier`, `FakeClassifier`; `RoutingClassifier` (rules-first);
      strict-JSON `schema.py`; friendly `errors.py`; bounded `inference.py`.
- [x] `backends/` registry with `fake` and optional `llama_cpp`; model is a
      user asset (never committed/downloaded), lazy load, single-concurrency.
- [x] `AiMetric`/`AiRecord` models + `AiRepository`; `AiService` (effective
      DB-overridable config, status, model check/load/unload, classify, metrics,
      history, events); `ai_help.py` plain-language copy.
- [x] API `/api/v1/ai/*` (status/overview/settings/classify/test/models/
      model-ops/metrics/history) + schemas + router registration.
- [x] Wired into `ReactionService._classify`; `simulate`/`ingest_post` accept a
      mode; Setup-Wizard `ai` check; inference executor shutdown on exit.
- [x] `AiView.vue` + client types/methods + `/ai` route + sidebar «Мини-ИИ».
- [x] Tests: **281 passed**; `ruff check backend tests` clean; SPA builds.
- [ ] **Commit PHASE 7** on `develop` (single stable commit; do not push to `main`).

---

## Goal of PHASE 8 — Analytics

Turn the data the system already stores into understandable insight. No new
infrastructure: aggregate the existing `posts`, `reaction_jobs`, `audience_sources`
and `audience_users` tables. The Dashboard must explain numbers in plain language
(what changed, why it matters, what to look at), not just display them.

## Constraints / reminders

- **D-002**: analytics are read-only queries over SQLite; no schema rewrite, no
  new service. Keep queries efficient (aggregate in SQL, not in Python loops).
- **D-010/D-029**: never expose secrets or PII in analytics responses or exports;
  audience figures are aggregate counts, not personal data.
- **D-003**: one API serves both the Web UI and the Mini App.
- Keep the app runnable at the end (`pytest` passes, app starts, SPA builds).
- Prefer no new heavy dependency; charts should be lightweight (a small inline
  SVG/canvas component or a tiny chart lib, not a large framework).

## Deliverables

### Backend
- [ ] `backend/app/db/repositories/analytics.py` (or extend existing repos) with
      aggregate queries: posts per day, reactions per category, reaction success
      rate, per-bot participation, audience growth over time, source effectiveness
      (found → invited → joined where known), top sources.
- [ ] `backend/app/services/analytics_service.py` — `AnalyticsService` composing
      the queries into content / audience / reaction overviews with plain-language
      summaries.
- [ ] `backend/app/api/schemas/analytics.py` + `api/v1/analytics.py`
      (`/analytics/overview`, `/analytics/content`, `/analytics/audience`,
      `/analytics/reactions`) + router registration + `api/deps.py` service getter.

### Frontend
- [ ] `AnalyticsView.vue` — charts (posts/reactions over time, category mix,
      audience growth, source effectiveness) with date-range selection, loading/
      empty states, and plain-language explanations under each chart.
- [ ] Upgrade `DashboardView.vue` to pull from the analytics overview and explain
      the headline numbers in words.
- [ ] Client types/methods in `api/client.ts`, `/analytics` route, sidebar link.

### Tests
- [ ] analytics repository/service/API tests over seeded data (deterministic);
      empty-database behaviour; no-PII/secret leak assertions.

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`, and the relevant `docs/*`; run `ruff` + `pytest`; build the
      SPA; `git diff` review; commit on `develop`.

## After PHASE 8

PHASE 9 — Telegram Mini App (reuse the same SPA + API; Telegram `initData` auth).
See `docs/ROADMAP.md`.
