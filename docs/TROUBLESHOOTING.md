# Troubleshooting — Telegram Channel Management Suite

Plain-language fixes for common problems. The in-app **Logs / Error Center** and
**Setup Wizard** surface the same guidance.

---

## How to read an error in the UI

Every event in the Error Center has two buttons:

- **Что произошло?** — a plain-language description.
- **Как исправить?** — concrete steps.

Technical details are kept in the server log, never shown as the main message.

---

## Quick diagnosis checklist

```bash
git status
git log --oneline -20
cat agent/CURRENT_STATE.md
cat agent/NEXT_TASK.md
```

If you are a new agent or a new person picking this up, read those files first —
they are the project's persistent memory.

---

## Common problems

### The app won't start

**Symptom:** `run.bat` closes immediately / command errors out.

1. Check the log in `logs/`.
2. Verify `.env` exists (copy from `.env.example`).
3. Ensure `APP_SECRET_KEY` is set (non-empty).
4. Ensure `data/` is writable.
5. Local dev: are dependencies installed? `pip install -r backend/requirements-dev.txt`.

---

### "Database locked" / data not saving

- SQLite allows few concurrent writers. Make sure only one instance runs.
- Check that `data/` is writable and not on a read-only medium.
- For heavy use, plan the PostgreSQL migration path (see ARCHITECTURE §3).

---

### Manager bot not connected

**What it means:** no manager bot token is configured yet.

**How to fix:**
1. Open Telegram, talk to **@BotFather**.
2. `/newbot`, follow prompts, copy the token.
3. Web UI → Bots → add the manager bot, paste the token.
4. Set `MANAGER_BOT_ADMIN_IDS` to your Telegram user id so only you can control it.

---

### "Telegram API credentials missing"

**What it means:** user-account features need API ID/Hash from Telegram.

**How to fix:**
1. Go to https://my.telegram.org → API development tools.
2. Create an application; copy `api_id` and `api_hash`.
3. Web UI → Sessions → Add account → enter them (or set in `.env`).

---

### Login code / 2FA problems (user session)

- Enter the code Telegram sent you (not the SMS from another service).
- If you have 2FA enabled, enter your **cloud password** when asked.
- Session content is never shown — that is expected and correct.
- If authorization fails repeatedly, delete the account entry and re-add it.

---

### FloodWait

**What it means:** Telegram asked us to wait before doing more of this action.

**What the app does (by design):**
- Pauses the affected account/queue.
- Shows you the remaining wait time.

**What to do:**
- Wait. Do not retry in a loop — that is against Telegram rules and the app
  intentionally refuses to.
- Reduce operation rates in Settings (delays, per-run limits).

We **never** bypass FloodWait, privacy, or admin restrictions.

---

### Invites fail with "privacy restricted"

**What it means:** the target user's privacy settings do not allow adding them.

**What to do:** this is stored as the user's status; it is not a bug. Consider
filtering such users out before running the invite job.

---

### Reactions not appearing

1. Is at least one bot enabled in **Reactions**?
2. Does the profile allow the emoji for that post's category (**Rules**)?
3. Are delays so long that the queue has not fired yet? Check **Queue**.
4. Are there errors in the **Logs** center?

---

### The UI is blank / fails to load

- The frontend is served from `backend/app/static`.
- Local dev: run `cd frontend && npm run build`.
- Production/portable: the build is included — no Node.js needed.
- Hard-refresh the browser (Ctrl+F5).

---

### AI classifier does nothing

- AI is **optional**. If `AI_ENABLED=false`, only the Rules Engine runs (this is
  normal and often sufficient).
- If enabled, verify `AI_MODEL_PATH` points to a valid `.gguf` file.
- Check the **AI** page for status and test a classification.

---

### Port issues

- Default: `127.0.0.1:8000`. Change `APP_PORT` in `.env`.
- If the port is busy, pick another (e.g. `8080`).
- On a VPS, do not expose the port publicly without HTTPS and auth.

---

## Backup and restore problems (PHASE 10)

| Symptom | Cause | Fix |
|---------|-------|-----|
| «Файл базы данных не найден» when creating a backup | App never started, so `data/app.db` does not exist yet | Start the app once, then create the backup |
| Backup has no session files | Sessions are excluded by default | Only if you truly need it, tick "Включить файлы сессий" (handle the file securely) |
| Restore seems to have no effect | The running process still holds the old DB | Restart the app after restoring |
| «Не удалось расшифровать сохранённый секрет» | `APP_SECRET_KEY` changed since the secret was stored | Restore the original key, or re-enter the affected bot token |
| Config import replaced something unexpectedly | Import defaults to *replace* | Re-run with "Заменить текущую конфигурацию" unchecked, or restore a backup |

## Portable build problems (PHASE 10)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `run.bat` closes instantly | `runtime\python.exe` missing and no system Python | Put the Python **embeddable package** into `runtime\`, or install Python 3.11+ |
| Browser opens but page does not load | Port 8000 busy, or server still starting | Wait a few seconds; if needed set another `APP_PORT` in `.env` |
| Data appears in the wrong place | `TCMS_ROOT` not set | Launch via `run.bat` (it sets `TCMS_ROOT` to the folder) |
| Antivirus blocks the app | Local server binding | Allow local (127.0.0.1) connections for the app |

## Release / CI problems

| Symptom | Cause | Fix |
|---------|-------|-----|
| Release workflow's portable job fails with `zip error: No such file or directory` (exit 15) | A **relative** output dir passed to `build_portable.sh` (e.g. `dist/TCMS`); the ZIP path was derived from the relative `OUT` and used after `cd "$OUT"` | Fixed in D-059 (`OUT` is normalised to an absolute path against the caller's cwd). Verify with `tests/test_portable_smoke.py::test_build_portable_zip_with_relative_output`. |
| `gh release upload` fails: "release not found" | The release did not exist; the old workflow only uploaded | Fixed in D-060: the workflow now runs `gh release create --verify-tag` when missing. |
| No portable ZIP on a GitHub Release | Release workflow not run for the tag, or the job failed | Check **Actions → Release** for the tag; if it failed, fix forward and re-tag a patch (never move the tag, D-050). |

## Docker / VPS problems (PHASE 11)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container restarts in a loop | Missing/invalid `APP_SECRET_KEY`, or a volume permission issue | `docker compose logs app`; set `APP_SECRET_KEY`; ensure `data/` etc. are writable by uid 10001 |
| `docker compose up` complains `.env` not found | Old compose or a stale `.env` path | `.env` is optional now; create it from `.env.example` or remove the `env_file` block |
| Data disappears after `down` | Volumes not bind-mounted | Keep the `volumes:` mapping (`../data:/app/data`, etc.) in `docker-compose.yml` |
| App not reachable on the public IP | It binds to `127.0.0.1` by design | Put the Caddy/nginx proxy in front; do not publish `8000` publicly |
| HTTPS certificate not issued | DNS not pointing at the server, or port 80/443 blocked | Fix the A/AAAA record; open 80/443; check `docker compose logs proxy` |
| Mini App says unavailable | `MINIAPP_PUBLIC_URL`/`MINIAPP_ENABLED` not set | Use **Настройки → Мини-приложение Telegram** (or set the vars) and restart |
| Mini App setup rejected | URL is empty or not `https://` | Enter the public HTTPS URL of the panel (e.g. `https://tcms.example.com`) and retry |
| Permission denied talking to the Docker socket | Not in the `docker` group | `sudo usermod -aG docker $USER` then re-login (or use `sudo`) |

## Hardening problems (post-1.0)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Manager bot does not answer commands | runtime off, bot not added/enabled, or your id is not an admin | Set `MANAGER_RUNTIME_ENABLED=true`, add/enable the manager bot in **Боты**, put your numeric id in `MANAGER_BOT_ADMIN_IDS` |
| No notifications arrive | master switch off, category off, or manager bot not connected | Check **Настройки → Уведомления** and the **Система** page manager-bot card |
| Permission check says `auth_required` | account not signed in | Re-authorize the account on the Sessions page |
| Permission check says `privacy_restricted` / `admin_required` | channel hides members or you lack invite rights | Expected Telegram restriction — not a bug; it is never bypassed (D-006) |
| Permission check says `flood_wait` | too many requests | Wait the shown time; the app resumes automatically, it does not retry in a loop |
| Settings page shows notifications but none send | runtime disabled in tests/dev, or Telegram unreachable | Confirm the runtime is running (System page) and the network reaches api.telegram.org |

## Recovering the project after a new chat/session

A new agent must be able to continue from files alone. Run:

```bash
git status
git log --oneline -30
cat agent/CURRENT_STATE.md
cat agent/NEXT_TASK.md
cat agent/DECISIONS.md
cat docs/ROADMAP.md
```

You should then know: what is done, what works, what is broken, what is next,
which decisions are locked, and which must not be broken. **Critical context is
never stored only in a conversation.**

---

## Getting more help

- `docs/SETUP.md` — installation for all modes.
- `docs/ARCHITECTURE.md` — how the system fits together.
- `docs/SECURITY.md` — secret handling and limits policy.
- `agent/DECISIONS.md` — why certain choices were made.
