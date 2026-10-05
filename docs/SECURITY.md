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
- **Telegram Desktop `tdata` folders** (they contain the account auth key);
- **Telethon StringSession strings** (`1BVtsOK…` — an auth key in text form);
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

### Account Hub import security (v1.1)

The multi-format importer (`backend/app/services/session_import.py`) only reads
**local artifacts the owner supplies**; it never searches for, downloads or
bulk-registers third-party accounts, and never bypasses Telegram verification,
FloodWait, privacy or identity checks.

- A **StringSession string** is treated exactly like a `.session` file: it is
  written to `SESSIONS_DIR` (gitignored), and the raw string is **never logged,
  returned by the API, or rendered in the UI** after submission.
- A **`.session` + companion JSON** is read with a whitelist
  (`api_id`/`app_id`/`api_hash`/`app_hash`/`phone`/`dc_id`). Secret keys
  (`session_string`, `auth_key`, `password`, `api_hash`) are used only to seed the
  account and are stored sealed, never persisted as raw JSON.
- A **`tdata` folder** is read in place and **never modified, copied out or
  uploaded**; the resulting session is stored internally.
- `.gitignore` excludes `sessions/`, `*.session*`, `tdata/`, `models/`,
  `backups/`, `exports/`, `data/` and `.env*`.

### Network routes (proxies) security (v1.1, D-065)

A proxy is an ordinary connection route, **not** a Telegram-limit bypass. Profile
credentials (`username`/`password`) are sealed with the same Fernet key as session
secrets and are never returned; the API exposes only whether a password is set.
Bound-account proxy credentials never appear in logs, exports, backups or the
diagnostics report.

---

## 4. Secret storage by platform

| Platform | Mechanism |
|----------|-----------|
| Windows  | OS-protected secret storage where available (DPAPI via `keyring`); fall back to encrypted file using `APP_SECRET_KEY` |
| Linux/VPS| environment variables / mounted secret files (`*_FILE` convention) |
| Portable | encrypted local file inside `data/` (never in the repo, never on a share) |

`APP_SECRET_KEY` is used to derive encryption keys for at-rest secrets. It must
be long and random (≥ 32 bytes entropy).

### VPS / Docker specifics (PHASE 11)

- Keep `.env` out of git and readable only by root: `chmod 600 .env`.
- Prefer Docker secrets or a root-only env file over baking values into images or
  compose files. The `.dockerignore` excludes `.env`, `sessions/`, `data/`,
  `backups/`, `logs/` and `exports/` from the build context.
- The container runs as a non-root user (uid 10001); keep host bind-mounts
  writable by that uid only.
- The app publishes `127.0.0.1:8000` by default — do not expose `8000` publicly;
  terminate TLS at the reverse proxy (Caddy/nginx/Traefik) and forward to the app.
- Back up `backups/` off-server; treat the DB and any session files as sensitive
  (D-039). Never place them in a public web root or shared folder.

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

## 7c. Content Studio (v1.2)

- **Nothing is published automatically**: grabbing material only creates items;
  a publication exists only after an explicit owner action (D-072). A moderation-
  held item is not published until released; a lost connection marks a
  publication `uncertain` instead of silently retrying.
- **Protected content is not copied**: a `noforwards` source stores only the
  post's link and metadata, never the text or media (D-006/D-074).
- **Rights are owner-declared, not legally checked**: unknown rights warn and add
  an attribution block rather than silently proceeding (D-073).
- **Media paths** stay in the local, gitignored runtime dirs; the Content Studio
  never uploads media anywhere except the owner's chosen channel during a publish
  the owner confirmed.
- **Publishing uses a bot by default**; a user account is used only in the
  expanded mode and only for actions the owner starts (least privilege, §8).
- **No new Telegram client**: reads go through `SessionProvider`, writes through a
  `PostingProvider` (D-001/D-071) — no parallel credential handling.

---

## 7d. Bot Factory (v1.3, D-077/D-078)

- **No account registration**: the factory never registers Telegram accounts,
  never automates phone verification and never bypasses Telegram limits. A bot is
  created by the owner in the official @BotFather flow and then adopted.
- **No unchecked claims**: a candidate username is reported free only after a real
  Telegram availability check.
- **Token handling**: a managed-bot token is write-only and sealed at rest with
  the existing `seal_secret` path (D-078); it is never returned by the API or
  written to logs.
- **Single path**: created bots go through the existing `BotService` /
  `BindingService`, so binding + capability rules (D-030) apply identically.

---

## 7e. LAN Mesh (v1.3, D-079…D-082)

- **No shared database**: each computer keeps its own SQLite file; a live
  database is never opened over a network share (avoids multi-writer corruption).
- **No implicit trust**: a discovered peer is a candidate; it becomes trusted only
  after the owner verifies a short one-time pairing code. The pairing credential
  is stored only as a salted hash; the raw code and the shared secret are never
  stored or returned.
- **Mesh endpoints are for the owner's own LAN**: they coordinate the owner's own
  computers. Peer requests are authenticated with the shared secret; the UI binds
  to `127.0.0.1` by default, so exposing the API beyond the LAN is a deliberate
  `APP_HOST` choice (§10/§12). Nothing derived from a secret is ever written to a
  user-visible field, and `/api/v1/mesh/ping` verifies the `X-Mesh-Secret` header
  (timing-safe) — an unpaired host cannot use it as an open probe (D-083).
- **Fencing**: a stale lease owner cannot commit a result after a failover
  (D-080); only the elected coordinator polls Telegram (D-081).
- **Never a limit bypass**: the mesh never enables Telegram-limit bypass,
  aggressive proxy rotation or mass account registration (D-082).

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

## 11. Diagnostics report redaction

The Diagnostics report (`GET /api/v1/diagnostics/report`, D-061) is explicitly a
*shareable* artifact, so it is redacted by design:

- Every payload passes through `core/redaction.py`: live configured secrets are
  replaced, and pattern rules mask bot tokens, `api_hash`/`api_id`, Telethon
  session strings, E.164 phones and long hex/base64 blobs. Forbidden keys
  (`token`, `api_hash`, `api_id`, `phone`, `password`, `session*`, `secret`,
  `app_secret_key`, `manager_bot_token`, …) are dropped entirely.
- The redacted payload is **re-scanned**; if the scan still finds anything that
  looks like a secret, **no file is produced** (the API returns a friendly error).
- It never contains session contents, database rows, audience/user records or
  private logs. Session/bot entries carry status only; paths are reported as
  folder *names* plus a writable flag.
- The response carries `X-Diagnostics-Redacted: true` and `Cache-Control:
  no-store`; the UI states «Отчёт безопасно очищен от секретов».
- Covered by `tests/test_diagnostics.py` (redaction, absence of secrets/DB
  contents, scan safety gate).

---

## 12. Pre-commit security checklist

- [ ] `git status` / `git diff --cached` reviewed — no secrets staged.
- [ ] No new secret printed in code paths (grep for token/hash logging).
- [ ] New endpoints validate input and return generic errors.
- [ ] New files respect `.gitignore` (sessions, data, logs, backups).
- [ ] No hardcoded credentials anywhere.
- [ ] Mass operations keep their confirmation + limit guards.
- [ ] Telegram limit handling (FloodWait/privacy/admin) still respected.
- [ ] Any new diagnostics field passes the redaction scan (D-061).
