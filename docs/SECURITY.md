# Security — Telegram Channel Management Suite

Security is a first-class requirement, not an afterthought. This document is the
policy; `docs/TROUBLESHOOTING.md` and `agent/DECISIONS.md` reference it.

---

## 1. Never commit secrets

The following must **never** appear in git history:

- `.env` files (only `.env.example` is committed);
- bot tokens;
- `TELEGRAM_API_HASH` / `TELEGRAM_API_ID` (treat as secret);
- MTProto `.session` files and their journals;
- passwords, 2FA passwords;
- database secrets / private keys;
- any `*.pem`, `*.key`, `credentials.json`.

`.gitignore` already excludes these. Before every commit, verify:

```bash
git status
git diff --cached
git grep -nI -E '(BOT_TOKEN|API_HASH|[0-9]{8,10}:[A-Za-z0-9_-]{35})' -- . ':(exclude).env.example'
```

If a secret ever leaks into history, **rotate it immediately** (new token / new
API hash) and then clean history. Rotation matters more than history rewriting.

---

## 2. Never expose secrets in output

Secrets must not be written to:

- the console / stdout;
- the Web UI (never render a token or session content);
- logs;
- exception messages / stack traces returned to clients;
- API responses.

Rules for implementers:

- Wrap secret-bearing config in a `SecretStr` (pydantic) so `repr()` is masked.
- Centralize redaction in the logging setup (a filter that masks known secret
  patterns) — see `backend/app/core/logging.py` (PHASE 1).
- Return generic messages to clients; keep technical detail in the server log.
- The UI shows *state* (e.g. "token configured ✅"), never the value.

---

## 3. Session files (MTProto)

- Stored **only** in `SESSIONS_DIR` (default `./sessions`), which is gitignored.
- **Excluded from Docker images** (`.dockerignore`).
- Each session has a human-readable owner label and can be **revoked/deleted**
  from the UI.
- Health-checkable (still authorized? rights available?).
- Session **contents** are never displayed, logged, or returned.

Implementation (PHASE 4, D-025):

- The API hash and the **full phone number** are stored **sealed** (Fernet, key
  derived from `APP_SECRET_KEY`) in `api_hash_encrypted` / `phone_encrypted`.
  Only `phone_masked` (e.g. `+7999***4567`) and the non-secret `api_id` are stored
  in plaintext. The API never returns the api_hash or the full phone number.
- A session file is referenced by a UUID basename (`session_ref`) resolved against
  `SESSIONS_DIR`; the file is never read, exported or shown. The API exposes only
  `has_session`, `has_api_hash` and `session_file_exists` booleans.
- If `APP_SECRET_KEY` is lost/changed, sealed values become unreadable; the UI
  shows a friendly "add the account again" message (never a stack trace).

---

## 4. Secret storage by platform

| Platform | Mechanism |
|----------|-----------|
| Windows  | OS-protected secret storage where available (DPAPI via `keyring`); fall back to encrypted file using `APP_SECRET_KEY` |
| Linux/VPS| environment variables / mounted secret files (`*_FILE` convention) |
| Portable | encrypted local file inside `data/` (never in the repo, never on a share) |

`APP_SECRET_KEY` is used to derive encryption keys for at-rest secrets. It must
be long and random (≥ 32 bytes entropy).

---

## 5. Web / API security

- Local UI binds to `127.0.0.1` by default — **no public server required** for
  normal local use.
- CORS restricted to configured origins.
- Auth: local session signing + (for Mini App) validated Telegram `initData`.
- Validate and sanitize all inputs (pydantic schemas on every endpoint).
- CSRF protection for state-changing browser calls.
- Rate-limit sensitive endpoints.
- HTTPS is mandatory on VPS (terminated at the reverse proxy).

---

## 6. Telegram server-limit compliance

We **never** attempt to bypass Telegram restrictions:

- **FloodWait** → pause the affected account/queue, display the wait time. No
  retry-until-success loops that ignore the limit.
- **Privacy restrictions** → store as the target user's status; do not work
  around them.
- **Admin restrictions** → surface as an error; do not attempt evasion.

All operation limits are **configurable** (per account, per run, delays).

---

## 7. Mass-operation safeguards

Before any bulk operation (invites, reactions) the UI shows a mandatory
confirmation summary: source, target, user count, account count, applied
filters, planned operation count. The user must confirm.

Audience scans also use a dry-run **preview** (account, batch/chunk sizes,
estimated total, notes) before any job is queued.

---

## 7a. Invites (PHASE 6)

- **Confirmation is enforced server-side**: a job is created as `draft` and only
  `POST /confirm` (which records `confirmed_at`) can start it — the summary cannot
  be skipped by calling the API directly.
- **Limits are configurable, never bypassed**: per-account spacing
  (`INVITE_DELAY_MIN/MAX`), `INVITE_MAX_TOTAL`, `INVITE_MAX_PER_ACCOUNT`,
  `INVITE_BATCH_SIZE`. The planner spaces tasks per account; a bulk run is not
  one burst.
- **FloodWait** pauses the whole run, records `wait_until`, and surfaces the
  waiting account — the system never retries in a loop. **Privacy** becomes a
  per-user `privacy` status; **admin-required** becomes an error status. Neither
  is retried automatically.
- **Restart safety**: an interrupted run is paused on startup, never resumed
  silently; the operator resumes explicitly (`recover()`).
- **Responses/logs/UI** expose only `telegram_user_id`, `username`, statuses and
  counts — never session strings, tokens, api_hash or raw phones.

---

## 7b. Audience data (PHASE 5)

- **No raw PII at rest**: only `phone_masked` may be stored, and only when the
  `AUDIENCE_STORE_PII` setting is enabled; full phone numbers are never persisted
  by the audience subsystem.
- **Exports are local-only**: CSV/JSON files are written to the gitignored
  `exports/` directory and are never uploaded or sent anywhere automatically. PII
  columns are excluded by default and exporting them requires the setting above.
- **Completeness honesty**: when Telegram exposes only part of an audience the
  source is marked `partial` / `no_access` and explained in plain language; a
  partial list is never presented as complete.
- **FloodWait / privacy / admin** during a scan pause or fail the source with a
  visible wait/status — never bypassed (see section 6).
- **Responses/logs** never contain session strings, tokens, api_hash, or raw
  phones (verified by `tests/test_audience_security.py`).

---

## 8. Principle of least privilege

- The manager bot only responds to whitelisted admin ids.
- User accounts are used only for actions the owner explicitly starts.
- No background action touches an account the owner has disabled.

---

## 9. Backup / restore security

Backups are single `.tcmsbak` zip files (SQLite database + `manifest.json`),
written to `backups/` (gitignored). They should never be copied into the
repository or a shared/public location.

- **Session files are excluded by default** (D-039). They grant full account
  access, so including them requires an explicit opt-in
  (`backup_include_sessions` / `include_sessions=true`) and a confirmation in the
  UI; the manifest records whether they were included.
- Restoring always writes a **safety backup** of the current state first, so a
  mistaken restore is recoverable.
- Configuration export/import (`/api/v1/backup/config/*`) moves only
  `settings`, `reaction_profiles` and `reaction_rules`. The `bots` and
  `user_sessions` tables (sealed tokens / session references) are **never**
  exported or imported.
- Backup filenames are validated against path traversal; no token, hash, phone
  number or session content is ever placed in an API response, log line, or the
  manifest.

---

## 10. Telegram Mini App security

- `initData` is verified **server-side** with `HMAC_SHA256(bot_token,
  "WebAppData")` over the sorted key/value pairs (constant-time compare). The
  client is never trusted for identity.
- Stale `initData` (older than `MINIAPP_INITDATA_MAX_AGE`) is rejected, as is a
  payload whose `auth_date` is in the future.
- The manager bot token is used only as the HMAC key. Neither the token nor the
  raw `initData` is ever logged, stored, or returned in any API response.
- When `MANAGER_BOT_ADMIN_IDS` is set, only those Telegram ids may sign in;
  rejected attempts are recorded in the Error Center without exposing secrets.
- The session cookie (`tcms_miniapp`) is `HttpOnly`, `SameSite=Lax`, and
  `Secure` in production. Its token is HMAC-signed with a key derived from
  `APP_SECRET_KEY` (`derive_key`), and expires after `MINIAPP_SESSION_TTL`.
- The Mini App is off by default. It never requires a public server for the local
  Web UI, and enabling it does not weaken local (`127.0.0.1`) access.

---

## 11. Pre-commit security checklist

- [ ] `git status` / `git diff --cached` reviewed — no secrets staged.
- [ ] No new secret printed in code paths (grep for token/hash logging).
- [ ] New endpoints validate input and return generic errors.
- [ ] New files respect `.gitignore` (sessions, data, logs, backups).
- [ ] No hardcoded credentials anywhere.
- [ ] Mass operations keep their confirmation + limit guards.
- [ ] Telegram limit handling (FloodWait/privacy/admin) still respected.
