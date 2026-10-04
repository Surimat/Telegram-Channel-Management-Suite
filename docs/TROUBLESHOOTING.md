# Troubleshooting — Telegram Channel Management Suite

Plain-language fixes for common problems. The in-app **Диагностика** page and
**Logs / Error Center** surface the same guidance.

---

## Start here: the Diagnostics page

Open **Диагностика** in the Web UI. It shows every component with a plain status
(`Готово` / `Внимание` / `Ошибка` / `Не настроено`), what it means and what to do
— no Python or log reading needed.

If you need help from a developer, press **«Создать отчёт диагностики»** there.
The downloaded report (ZIP/JSON/TXT) is **redacted**: it never contains bot
tokens, keys, session data, phone numbers, passwords or database contents. Attach
it to your message instead of copying logs by hand.

The page also offers safe actions that never delete your data:
**Перезапустить планировщик**, **Перепроверить Telegram**, **Перепроверить
каналы**, **Очистить зависшие локальные задания** (the last one asks for
confirmation).

---

## Quick table: symptom → cause → what to do

| Symptom | Cause | What to do |
|---------|-------|------------|
| **Web UI does not open** | Server not started, wrong port, or frontend not built | Wait a few seconds; open http://127.0.0.1:8000. If port busy set `APP_PORT`. Local dev: `cd frontend && npm run build`. Check **Диагностика** → Приложение / Хранилище |
| **`run.bat` does not start** | No embedded `runtime\python.exe` and no system Python, or a blocked/antivirus script | Put the Python embeddable package into `runtime\`, or install Python 3.11+; allow the app in antivirus. See "Portable build problems" below |
| **Telegram bot does not connect** | No token, bot disabled, or network cannot reach api.telegram.org | **Диагностика** → Управляемые боты; add the token in **Боты**; press **Перепроверить Telegram** |
| **Account requires authorization** | Session expired or never signed in | Open **Аккаунты** → "Проверить"/re-auth wizard. **Диагностика** → Аккаунты Telegram shows `auth_required` |
| **Channel unavailable** | Wrong reference, no access, or Telegram privacy/admin restriction | **Каналы** → "Проверить" (uses a ready account). **Диагностика** → Каналы. Restrictions are never bypassed |
| **Audience scan partial** | Telegram hid the member list or a limit hit | Expected, not a bug. **Диагностика** → Аудитория shows "Частичных". Reduce rate; retry later |
| **Invite paused** | FloodWait, account not ready, or a privacy restriction | **Очередь** shows the reason; wait for the shown time. **Диагностика** → Аккаунты / Очередь. The app never retries in a loop |
| **FloodWait** | Too many requests for that action | Wait the shown time. Reduce delays/limits in **Настройки**. Never bypass it |
| **AI model missing** | AI enabled but no valid `.gguf` path | Optional. **Диагностика** → Мини-ИИ shows `Не настроено`/`Внимание`; set the model in **AI** or leave AI off |
| **Database migration required** | The app version is newer than the database schema | **Диагностика** → База данных shows the pending state; restart the app — migrations run automatically at startup |
| **Backup restore** | Wrong `APP_SECRET_KEY`, or the running process still holds the old DB | Restore the original key or re-enter the token; restart the app after restoring. See the table below |
| **Network route (proxy) fails** | Wrong host/port/credentials, or the proxy is down | **Аккаунты → Сетевые маршруты**, press **«Проверить»**; fix or remove the route. A route never bypasses Telegram limits |
| **Donor discovery finds nothing** | No account connected, topic too narrow, or hidden data | Connect an account; broaden keywords; candidates must be added explicitly. See below |

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

### The database file is damaged

**Symptom:** the Web UI opens but **Диагностика** shows «Файл базы данных
повреждён или не является базой данных», and other rows show «Не удалось
прочитать данные из базы».

**Cause:** `data/app.db` is corrupt (interrupted write, full disk, a non-SQLite
file, or a copy of the wrong file). The app no longer crashes on this — it starts
and explains the problem so you can recover.

**What to do:**
1. Open **Резервные копии** and restore the most recent working backup.
2. If you have no backup and do not need the data, stop the app, delete
   `data/app.db` (and any `app.db-wal`/`app.db-journal` beside it), and restart —
   a fresh database is created automatically.
3. Restart the app; **Диагностика → База данных** should read «Готово».

Never edit the database file by hand; use **Резервные копии** or the app.

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

### Bot is not connected to a channel / reactions do nothing

**What it means:** a managed bot must be an admin in the channel before it can
set reactions or create invite links.

**How to fix:**
1. Open **Каналы**, pick the channel, use the **«Бот и реакции»** column and press
   **«Подключить бота»**. The app shows the official link to add the bot.
2. Add the bot to the channel as an administrator (rights to post / set
   reactions / invite as needed).
3. Press **«Проверить права»**. The status becomes «Готово» when Telegram confirms
   the rights; otherwise a plain-language reason and hint are shown.
4. Press **«Проверить реакции»** to record which reactions the channel supports.
   The reaction planner then never schedules an unsupported emoji.

No user account is required for this — the bot alone is enough.

---

### Кампании (invite links) do nothing

- The campaign must be **Активна** (press «Запустить»).
- The manager bot must be an admin in the target channel with the right to invite.
- The chosen **risk mode** sets conservative spacing; nothing is sent instantly.
- If links are revoked, create a new one.

---

### Обновления: check or download fails

- Auto-update is **off by default**; enable it on the **Система** page first.
- The check contacts the public GitHub API; if the network blocks it, the state
  shows a friendly error — the app keeps working on the current version.
- A download is only accepted if its **SHA-256 matches** the published checksum;
  a mismatch is reported and nothing is staged.
- The updater **never installs** anything by itself — you decide.

---

### The report says «Место хранения копий» has an error

- Open **Резервные копии → Места хранения копий** and press **«Проверить»**.
- Telegram / Google Drive / Яндекс.Диск are optional; a bad token shows a
  plain-language error. Disable or remove the destination, or re-enter its token.
- The **local** destination is the primary store and cannot be removed.

---

### Network route (proxy) does not work

**What it means:** a proxy is an optional connection route for an account. It does
**not** lift Telegram limits and is not a way around FloodWait/privacy/admin
restrictions.

**How to fix:**
1. Open **Аккаунты → Сетевые маршруты (прокси)** and press **«Проверить»** on the
   profile. The status is honest: `Доступен` / `Ошибка подключения` / `Нет ответа`.
2. Check host, port and (if the proxy requires it) login/password. Credentials are
   stored sealed and are never shown again.
3. Assign the route to an account with the **Маршрут** column on the accounts table.
4. If the proxy is down, set the account back to **Прямое подключение** — a missing
   route never blocks the account permanently.

### Donor discovery finds nothing

- Donor search needs a working **account** (the Telegram provider runs through it);
  if no account is connected, the provider list explains that it is unavailable.
- The topic may be too narrow; try broader keywords or clear the subscriber range.
- A found channel is only a **candidate** — press **«Добавить в источники»** to use
  it. Hidden subscriber/activity data stays zero and is marked as partial; nothing
  is invented and no limits are bypassed.

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
