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

---

## 8. Principle of least privilege

- The manager bot only responds to whitelisted admin ids.
- User accounts are used only for actions the owner explicitly starts.
- No background action touches an account the owner has disabled.

---

## 9. Backup / restore security

Backups include DB, config, rules, reaction profiles, and app state. **Session
files are handled separately** and stored with the strongest protection
available. Backups are written to `backups/` (gitignored) and should never be
copied into the repository or a shared/public location.

---

## 10. Pre-commit security checklist

- [ ] `git status` / `git diff --cached` reviewed — no secrets staged.
- [ ] No new secret printed in code paths (grep for token/hash logging).
- [ ] New endpoints validate input and return generic errors.
- [ ] New files respect `.gitignore` (sessions, data, logs, backups).
- [ ] No hardcoded credentials anywhere.
- [ ] Mass operations keep their confirmation + limit guards.
- [ ] Telegram limit handling (FloodWait/privacy/admin) still respected.
