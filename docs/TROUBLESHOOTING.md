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
