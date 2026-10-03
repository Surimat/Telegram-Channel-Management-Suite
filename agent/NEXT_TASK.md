# NEXT TASK — Telegram Channel Management Suite

> The single "what to do next" pointer. Update at the end of every phase.

**Updated:** 2026-10-03
**Active phase:** PHASE 7 — Tiny AI (rules fast path + optional tiny GGUF classifier)
**Previous phase:** PHASE 6 — Invite Manager (completed; commit pending on `develop`).

---

## Repository sync status (2026-10-03)

PHASE 0–6 live on the `develop` branch. A PR (`develop → main`, #1) is open —
**not merged** pending owner confirmation. Continue on `develop` (feature
branches off it as needed). **Never push directly to `main`.**

---

## PHASE 6 — done (checklist)

- [x] `InviteJob`/`InviteTask` models (+ enums, terminal set); repositories with
      `claim_batch`, counters, `next_due`, `retry_failed`.
- [x] `InviteService`: dry-run preview, draft job + planner (per-account randomized
      spacing, `max_total`/`max_per_account` caps), confirm→start, pause/resume/stop,
      bounded durable `run_tick` (`done`/`more`/`paused`), safe retry, `recover`.
- [x] FloodWait → pause run + record `wait_until`; privacy/admin → per-user
      non-retryable statuses; transient network stays pending.
- [x] API `/api/v1/invites/*` + schemas + deps + router registration.
- [x] Setup-Wizard `invites` check; startup recovery for interrupted runs.
- [x] `InvitesView.vue` + client types/methods + route + sidebar link.
- [x] Tests: **238 passed**; `ruff check backend tests` clean; SPA builds.
- [ ] **Commit PHASE 6** on `develop` (single stable commit; do not push to `main`).
- [ ] (Deferred) Dedicated Audience/Sources **frontend views** — tracked with the
      frontend rollout, not blocking PHASE 7.

---

## Goal of PHASE 7 — Tiny AI

Keep the deterministic Rules Engine as the default classifier and add an
**optional** tiny classifier (a ~0.5–1B GGUF model via llama.cpp) that is only
consulted when the rules are not confident. The AI returns strict JSON
(`{category, tone, confidence}`) and can be fully disabled. The LLM is never used
to pick emoji — emoji selection stays deterministic (weights), per D-021.

## Constraints / reminders

- **D-001/D-005**: AI is an adapter behind an interface (`Classifier`), optional
  and disableable; no business logic may depend on it. The rules engine remains
  the source of truth.
- **D-020/D-021**: rules/classification are deterministic where possible; emoji
  are never chosen by the LLM.
- **D-010**: the model path and any AI config must not leak secrets; never store
  model credentials in git; log redaction stays intact.
- Keep the app runnable at the end (`pytest` passes, app starts, SPA builds).
- Prefer no new heavy dependency unless essential — the classifier must degrade
  gracefully when llama.cpp / the model is absent (offline mode).

## Deliverables

### Backend
- [ ] `backend/app/ai/` (or `services/classifier.py`): `Classifier` Protocol with
      `classify(text) -> Classification` (`category`, `tone`, `confidence`,
      `source`); `RulesClassifier` (wraps the existing Rules Engine fast path) and
      `TinyLlmClassifier` (GGUF via llama.cpp, strict JSON, robust parsing/errors).
- [ ] `Config` — `ai_enabled`, `ai_model_path`, `ai_min_confidence`,
      `ai_timeout`, `ai_threads`; sensible defaults, safe when path missing.
- [ ] Router logic: rules first → if confidence below threshold and AI enabled →
      tiny LLM → fall back to rules/neutral on failure. Fully off = rules only.
- [ ] Wire into `ReactionService._classify` (keep the interface so tests inject a
      fake classifier). Structured JSON only; never random emoji.

### API + Setup
- [ ] `api/schemas/ai.py` + `api/v1/ai.py`: status (enabled, model present,
      backend ready), a **classify test** endpoint (returns category/tone/
      confidence/source), enable/disable, model-path config.
- [ ] Setup-Wizard `ai` check extended: "model available / backend ready /
      disabled — rules only" in plain language.

### Frontend
- [ ] `AiView.vue`: enable/disable, model path, confidence threshold, a live
      "test a text" panel showing the routed result + which source won; clear
      explanation of what AI does and that it is optional.

### Tests
- [ ] classifier routing (rules win when confident; AI consulted only when
      needed; AI off ⇒ rules only; AI failure ⇒ graceful fallback), strict JSON
      parsing incl. malformed output, API endpoints, secret/leak checks.

### Finish
- [ ] Update `agent/CURRENT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`,
      `CHANGELOG.md`, and the relevant `docs/*`; run `ruff` + `pytest`; build the
      SPA; `git diff` review; commit on `develop`.

## After PHASE 7

PHASE 8 — Analytics (content + audience, charts, plain-language Dashboard). See
`docs/ROADMAP.md`.
