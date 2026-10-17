# Real-Telegram verification checklist (isolated test environment)

> **This is a plan, not an automated test. Do not run it as part of CI and do not
> run it against a production channel.** It is a manual, owner-supervised
> checklist for verifying the seven unreleased stages (D-123…D-128 and D-130, see
> `docs/ROADMAP.md`) against a **throwaway** Telegram test bot and a **private**
> test channel, before a release is cut (D-060).
>
> Everything below uses only the Telegram **Bot API** and the official bot flows.
> It never enters the owner's personal MTProto account, never sends a bulk invite,
> never deletes content, and never publishes to a real channel.

## 0. Safety rules (read first)

- Use a **dedicated test bot** and a **private test channel** that belong to the
  test setup only. Never point the suite at the real channel.
- Keep the personal-account switches **OFF** for the whole session
  (`personal_account_enabled=false`, `invites_enabled=false`). The only stage that
  is exercised through a personal account (D-123) is checked by *refusal*, never by
  a real login.
- **No bulk invitations, ever.** The invite stage is verified only by its dry-run
  refusal, its caps and its 24-hour pause behaviour — never by sending invites.
- **No content deletion.** The auto-delete path is inspected by configuration and
  logs, never by deleting a real post.
- **Test publication happens only after explicit owner confirmation**, to the
  private test channel, and the post is left in place (the owner removes it by hand
  if desired).
- Run on a machine with its own `data/` directory (a disposable profile) and its
  own SQLite database. Take a copy of the database before starting so any check can
  be rolled back by restoring the file.
- If any step behaves unexpectedly, **stop** and record it; do not "make it work"
  by loosening a safety switch.

## 1. Environment preparation

| # | Step | Expected |
|---|------|----------|
| 1.1 | Create a **test bot** through the official `@BotFather` flow (`/newbot`). Record only its public `@username` (never its token in a report). | Bot exists. |
| 1.2 | Create a **private test channel** (e.g. `TCMS test — do not use`). Add the test bot as an **administrator** with the least rights needed for the stage under test (post messages; add invite rights only if a stage needs them). | Bot is an admin. |
| 1.3 | Start the suite on the disposable profile; open **Диагностика** and confirm the app starts with no migration error. | App is healthy. |
| 1.4 | Open **Настройки → Личный аккаунт (безопасность)**. Confirm **both** switches are **off** and that turning them on is a deliberate, separate owner action. | Both switches off. |
| 1.5 | Confirm the test bot is registered as the manager bot (or add it) and that it answers `/start`. | Manager bot responds. |

## 2. D-123 — Personal Account Safety (verify by refusal)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 2.1 | Master switch blocks MTProto work | With `personal_account_enabled` off, try to add/authorize a personal account. | Friendly `403` (`code/message/hint`), **no** account row and **no** session file created. |
| 2.2 | Bot API is unaffected | Do an ordinary bot action (e.g. re-check the manager bot) while the master switch is off. | It still works. |
| 2.3 | Mass-invite switch is required | With the master switch on but `invites_enabled` off, call the invite **dry-run/preview**. | Friendly `403` naming the invite switch. |
| 2.4 | Caps cannot be raised | Try to set an invite `max_total`/`max_per_account` **above** the configured ceiling. | Value is clamped down to the ceiling, never accepted as-is. |
| 2.5 | No real invites | — | **Nothing is invited.** This stage is never verified by sending invites. |
| 2.6 | Rate limit is honest | Only if a real invite is unavoidable and the owner explicitly approves it against the private test channel: observe that the rolling 24-hour ceiling **pauses** the job with a `wait_until` instead of continuing. | Job is paused, not run unbounded. Otherwise: skip and note it. |

## 3. D-124 — Operational Module Registry

| # | Check | How | Expected |
|---|-------|-----|----------|
| 3.1 | Unconfigured channel = all modules on | Point the suite at the private test channel without touching its module map. | No module is silently disabled. |
| 3.2 | Turning a module off stops the real work | Switch **Реакции** off for the test channel, then trigger a reaction path. | The durable job is retired (`SKIPPED`) with a clear Russian reason and **no** Telegram call. |
| 3.3 | Friendly error, never a 500 | With **Приглашения** off, call the invite resume endpoint. | Friendly `403`, not a `500`. |
| 3.4 | A module never weakens a safety gate | Turn a module **on** while the personal-account master switch is off. | MTProto work is still refused (D-123 wins). |

## 4. D-125 — Bot Lifecycle Recovery and Adoption

| # | Check | How | Expected |
|---|-------|-----|----------|
| 4.1 | Crash recovery, factory | Queue a Bot Factory batch, kill the process mid-creation, restart. | The in-flight candidate is re-queued (`RUNNING → QUEUED`) and the queue resumes; no bot is created twice. |
| 4.2 | Crash recovery, onboarding | Same for a Bot Onboarding batch. | The `VERIFYING` candidate is re-queued and the queue resumes. |
| 4.3 | Deep-link adoption | Create a bot through the official `t.me/newbot` link for a username already in the batch. | The `managed_bot` update adopts it into its batch; the batch settles `COMPLETED` once no candidate waits. |
| 4.4 | Idempotent adoption | Re-deliver the same `managed_bot` update. | No-op: no duplicate `Bot` row, no inflated counter. |
| 4.5 | Unknown username is ignored | Send a `managed_bot` update for a username not in any batch. | Ignored — never searched for, downloaded or imported (D-070). |

## 5. D-126 — Content Pipeline Consolidation

| # | Check | How | Expected |
|---|-------|-----|----------|
| 5.1 | v1.2 rewrite contract | Call `/api/v1/content/items/{id}/rewrite` and `/rewrite/apply` on a test item. | Same response shape and error semantics as before; the work is done by the pipeline (one engine). |
| 5.2 | One processed text | Take an item through grab → process → moderate → plan → publish (to the **private test channel**). | The published text is the processed text; a secret-free `content_operations` record exists. |
| 5.3 | AI failure keeps material | Make the AI provider unavailable, then process an item. | The item moves to `needs_review` with a clear note; nothing is lost. |

## 6. D-127 — Channel Overview (read-only)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 6.1 | Read-only | Open `/channel-overview` for the test channel. | It renders identity, module map and per-area sections. |
| 6.2 | No side effects | Watch the job queue and logs while opening the page repeatedly. | **No** row written, **no** job queued, **no** Telegram call. |
| 6.3 | Honest attention | Put one item into `needs_review`. | The section shows `warning`, not `ok`; a ready binding shows `ok`. |

## 6a. D-130 — Reaction Manager channel-post source

| # | Check | How | Expected |
|---|-------|-----|----------|
| 6a.1 | Real post is seen | Make the **manager bot** an administrator of the private test channel, then publish a post there. | Within one poll interval the post appears in the reaction queue with its real message id. |
| 6a.2 | Reactions are planned | Open `/reactions` and look at the queue for that post. | Reaction jobs are planned for the channel's reacting bots (no manual step). |
| 6a.3 | Redelivery is a no-op | Wait for a repeat `channel_post` delivery (or re-send the same update). | No duplicate post and no duplicate job. |
| 6a.4 | Edit does not re-plan | Edit the post text. | The stored text refreshes; **no** new reaction jobs are planned. |
| 6a.5 | Manual path is honest | On `/reactions`, use «Добавить пост и запланировать» **without** a message number. | Refused with a clear reason; no unrunnable job is created. |
| 6a.6 | Refusal is honest | Remove the reacting bots' reaction right, then let a job run. | The job fails with Telegram's real reason; nothing is silently swallowed. |

## 7. D-128 — End-to-end Setup Wizard

| # | Check | How | Expected |
|---|-------|-----|----------|
| 7.1 | Status is stored, not inferred | Open `/setup-wizard` without running any step. | Steps are `unchecked`; opening the page marks nothing done. |
| 7.2 | Real check required | Run the **bot** and **content** checks against the private test channel. | `verified` only when the check actually ran and passed; a missing/failed check is `unchecked`/`pending`, never `verified`. |
| 7.3 | Test publication is gated | Call `POST /api/v1/setup-wizard/test-publication` **without** `confirmed`. | Refused. |
| 7.4 | Test publication with confirmation | **Only after the owner explicitly confirms**, call it with `confirmed` set and the `bot`/`content` checks passed. | Exactly **one** material is published to the **private test channel**; no account is registered and no limit is bypassed. |
| 7.5 | Readiness gate | Re-open the wizard. | Readiness reflects the real state and never claims readiness it did not verify. |

## 8. Error and recovery checks (no mass actions)

| # | Check | How | Expected |
|---|-------|-----|----------|
| 8.1 | Restart safety | Restart the app mid-queue. | Durable queues resume; invites are **paused**, never silently resumed (D-006). |
| 8.2 | Honest failures | Point the AI gateway at an unreachable provider and run a pipeline step. | A clear failure with failover/`needs_review`; no stack trace, no secret. |
| 8.3 | Secret scan | Open the Diagnostics report for the session. | No token, `api_hash`, session string, phone number, password or DB content appears. |
| 8.4 | No orphan artifacts | After a refused action (2.1, 2.3, 3.2, 3.3). | No half-created account, session file or DB row is left behind. |

## 9. Abort / rollback

- Stop the suite, restore the copied database, and remove the disposable profile
  and session directory.
- Remove the test bot from the private test channel (or delete the test channel if
  it was created only for this run).
- Record any deviation as a finding; do not resolve it by weakening a safety gate.

## 10. Sign-off (fill in after the session)

| Item | Result | Notes |
|------|--------|-------|
| D-123 refusal paths (2.1–2.4) | | |
| D-124 module gating (3.1–3.4) | | |
| D-125 recovery + adoption (4.1–4.5) | | |
| D-126 single engine (5.1–5.3) | | |
| D-127 read-only overview (6.1–6.3) | | |
| D-128 wizard + gated test publication (7.1–7.5) | | |
| Error/recovery + secret scan (8.1–8.4) | | |

**Reminder:** this checklist was **not executed** as part of this change. It is a
plan to be run manually by the owner in an isolated environment when a release of
D-123…D-128 is being considered.
