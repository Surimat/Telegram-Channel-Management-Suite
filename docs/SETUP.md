# Setup — Telegram Channel Management Suite

This guide covers all three run modes. Pick the one that matches your situation.

- **A. Local development** (fastest to try, needs Python + Node)
- **B. Windows portable** (no Python, no Node, no Docker — for end users)
- **C. VPS / Docker** (production)

> New to Telegram bots? Read `docs/TROUBLESHOOTING.md` and the Setup Wizard
> section first — the app explains every step in plain language (RU-first).

---

## 0. Requirements overview

| Mode | Needs |
|------|-------|
| Local dev | Python 3.11+, Node 18+ (only to build the UI), pip |
| Windows portable | nothing pre-installed (bundled runtime) |
| VPS / Docker | Docker + Docker Compose |

---

## A. Local development

```bash
# 1. Clone
git clone https://github.com/Surimat/Telegram-Channel-Management-Suite.git
cd Telegram-Channel-Management-Suite

# 2. Create the environment file
cp .env.example .env
#    then edit .env and set at least APP_SECRET_KEY

# 3. Backend environment
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux:    source .venv/bin/activate
pip install -r backend/requirements-dev.txt

# 4. Build the frontend (produces backend/app/static)
cd frontend && npm install && npm run build && cd ..

# 5. Run the app
python -m backend.app.main
# or: uvicorn backend.app.main:app --reload
```

Open http://127.0.0.1:8000

### Generating a secret key

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the result into `APP_SECRET_KEY` in `.env`.

---

## B. Windows portable

Target experience:

```
unpack folder → double-click run.bat → app starts → browser opens → it works
```

Layout after unpacking:

```
TelegramChannelManagementSuite/
  app/          # application code + built UI
  runtime/      # embedded Python (bundled)
  data/         # database + mutable state
  sessions/     # Telegram session files (keep private!)
  backups/
  logs/
  exports/
  run.bat
  stop.bat
  README.txt
```

Steps:

1. Download the portable archive and extract it anywhere (USB stick is fine).
2. Double-click **`run.bat`**.
3. The browser opens `http://127.0.0.1:8000` automatically.
4. Use **`stop.bat`** (or close the console window) for a graceful shutdown.

No Python, Node, npm, Docker, PostgreSQL, or Redis is required.
All mutable data stays inside the extracted folder.

> Portable packaging is delivered in PHASE 10. Until then use mode A.

---

## C. VPS / Docker

```bash
cp .env.example .env
# edit .env: set APP_SECRET_KEY, APP_ENV=production, bind settings, etc.

docker compose -f docker/docker-compose.yml up -d --build
```

- The same backend serves both the API and the built UI.
- Terminate HTTPS with a reverse proxy (Caddy / nginx / Traefik) in front.
- Persist `data/`, `sessions/`, `backups/`, `logs/` as volumes.
- **Never** bake `.env`, session files, or secrets into the image.

See `docs/SETUP.md` (this file) for HTTPS notes and `docs/SECURITY.md` for the
secret-handling policy.

---

## First-run Setup Wizard

After the app is running, open the Web UI → **System → Setup Wizard**. It checks,
in plain language:

- runtime / Python;
- database;
- Telegram API credentials;
- Bot API;
- manager bot;
- managed bots;
- user sessions;
- channel access;
- required permissions;
- frontend;
- scheduler;
- filesystem / writable directories.

Each item shows: **STATUS**, a description, what it means, and what to do next —
with human-friendly wording instead of raw error codes.

---

## Adding a Telegram user account

Open the Web UI → **Аккаунты → + Добавить аккаунт** and follow the wizard:

1. **API ID / API Hash** — from https://my.telegram.org → *API development tools*.
2. **Phone number** in international format (e.g. `+79991234567`).
3. **Login code** — sent by Telegram to your app/service chat.
4. **2FA password** — only if the account has two-step verification enabled.
5. The session is created in `SESSIONS_DIR` and the account is checked; its
   username/user ID are shown.

Alternatively, **Import .session** registers an existing `.session` file by path.
The file is copied into `SESSIONS_DIR`; on import failure nothing is registered.

Secrets are stored sealed (Fernet via `APP_SECRET_KEY`) and never shown. The
account can be health-checked, disabled, re-authorized or deleted from the list.

---

## Parsing an audience (PHASE 5)

Open the Web UI → **Аудитория** (or use the API) and:

1. **Add a source** — a public channel/group `@username`, a `t.me/...` link, or
   a numeric Telegram ID. Pick which user account performs the scan.
2. **Check** the source — the system resolves it and reports whether Telegram
   exposes the member list.
3. **Preview scan** — a dry run shows the account, batch/chunk sizes and any
   Telegram-reported total. Nothing runs until you confirm.
4. **Start scan** — the scan runs in small chunks (weak-machine friendly) and can
   be **paused / resumed / cancelled** at any time; progress survives a restart.
5. **Review results** — filter, search, sort, tag and bulk-update users; export
   to CSV/JSON or import an existing list.

Completeness is reported honestly: `complete`, `partial` (Telegram returned only
part of the list), or `no_access` (Telegram hides the list for that account).
FloodWait pauses the scan and shows the wait time — limits are never bypassed.

Exports are written to the local, gitignored `exports/` directory and never sent
anywhere. Phone numbers are never stored in full; PII columns are excluded from
exports unless `AUDIENCE_STORE_PII` is enabled.

---

## Configuration

All configuration is available through:

1. `.env` (bootstrap / secrets), and
2. the **Settings** page in the UI (stored in the DB `settings` table).

`.env` values are the bootstrap defaults; UI settings override runtime behavior
and survive restarts.

### Key variables

| Variable | Meaning |
|----------|---------|
| `APP_SECRET_KEY` | signs local sessions / encrypts secrets — **set this** |
| `APP_HOST` / `APP_PORT` | bind address (default `127.0.0.1:8000`) |
| `DATABASE_URL` | SQLAlchemy URL (default SQLite in `data/`) |
| `MANAGER_BOT_TOKEN` | manager bot token from @BotFather |
| `MANAGER_BOT_ADMIN_IDS` | who may control the manager bot |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | from https://my.telegram.org |
| `SESSIONS_DIR` | where `.session` files live (outside git) |
| `AI_ENABLED` / `AI_MODEL_PATH` | optional tiny classifier |

See `.env.example` for the full annotated list.

---

## Stopping / restarting

- Local: `Ctrl+C` in the terminal running the app.
- Portable: `stop.bat`.
- Docker: `docker compose -f docker/docker-compose.yml down`.

Pending queue jobs are stored in the database and resumed on the next start.
