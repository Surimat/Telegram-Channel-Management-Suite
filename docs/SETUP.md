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

### Building the portable folder

Run the build script from the repository (needs Node once, for the frontend):

```bash
bash scripts/build_portable.sh /path/to/out
```

It builds the SPA, copies `backend/` into `app/`, creates the empty data
directories, copies `run.bat` / `stop.bat` / `README.txt`, and — by default —
downloads the official Windows **embeddable Python** (matching your host Python
version) into `runtime/` and installs the dependencies into
`runtime/site-packages`, so the result is truly zero-setup. The helper is
`scripts/fetch_embedded_python.sh`; it is also usable on its own:

```bash
bash scripts/fetch_embedded_python.sh /path/to/out/runtime \
  --version 3.12.7 --requirements backend/requirements.txt
```

If the network is restricted, pass `--no-runtime` (or set `SKIP_RUNTIME=1`) to
stage the code only, then add the runtime manually:

1. Download the "Windows embeddable package" for a matching Python version from
   <https://www.python.org/downloads/windows/>.
2. Unzip it into `runtime/` so `runtime\python.exe` exists.
3. Ensure `runtime\python3xx._pth` lists `../app` and `site-packages`.
4. Install dependencies:
   `runtime\python.exe -m pip install --target runtime\site-packages -r backend\requirements.txt`.

`run.bat` sets `PYTHONPATH=app` and `TCMS_ROOT` to the folder, so no installation
is needed.

### Backups

Use the **Резервные копии** page (or `POST /api/v1/backup`). A backup is one
`.tcmsbak` file containing the database; session files are excluded unless you
explicitly opt in. Configuration (rules, profiles, settings) can be exported and
imported separately — see `docs/API.md`.

---

## C. VPS / Docker

The same codebase runs on a VPS — there is **no separate "server version"**
(D-004). Everything is one FastAPI process that serves both the API and the built
SPA; SQLite lives on a mounted volume.

### 1. Prepare

```bash
git clone <your-repo> tcms && cd tcms
cp .env.example .env
# edit .env and set at least:
#   APP_SECRET_KEY=<a long random string>
#   APP_ENV=production
#   MANAGER_BOT_TOKEN=...            # from @BotFather
#   MANAGER_BOT_ADMIN_IDS=123456789  # your Telegram id
```

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Run (localhost, no TLS)

```bash
docker compose -f docker/docker-compose.yml up -d --build
curl -s http://127.0.0.1:8000/health      # {"status":"ok", ...}
```

The service binds to `127.0.0.1:8000` by default, so it is not publicly exposed.
Mutable state is bind-mounted from the project root: `data/`, `sessions/`,
`backups/`, `logs/`, `exports/`. `.env` is optional (the image has safe defaults);
when present it is loaded automatically.

### 3. HTTPS (recommended)

The app stays plain HTTP behind a TLS-terminating reverse proxy. A ready Caddy
overlay is provided (Caddy fetches and renews Let's Encrypt certificates
automatically):

```bash
# 1) edit docker/Caddyfile: set your domain + email
# 2) point your domain's A/AAAA record at the server
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.proxy.yml up -d --build
```

Caddy publishes `80`/`443` and proxies to `app:8000`. The app's own
`127.0.0.1:8000` binding remains and is harmless.

<details>
<summary>nginx alternative</summary>

```nginx
server {
    listen 80;
    server_name tcms.example.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl;
    server_name tcms.example.com;
    ssl_certificate     /etc/letsencrypt/live/tcms.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tcms.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```
</details>

Once HTTPS works, set `MINIAPP_PUBLIC_URL=https://tcms.example.com` and
`MINIAPP_ENABLED=true` in `.env` to use the Telegram Mini App (register the URL
with @BotFather as a Web App).

### 4. Operations

```bash
docker compose -f docker/docker-compose.yml logs -f      # follow logs
docker compose -f docker/docker-compose.yml ps           # status / health
docker compose -f docker/docker-compose.yml restart app  # restart
docker compose -f docker/docker-compose.yml down         # stop
```

- **Backups**: use the UI (**Резервные копии**) or `POST /api/v1/backup`. The
  archive lands in the bind-mounted `backups/`. Session files are excluded unless
  you opt in (D-039). Copy `backups/` off the server regularly.
- **Restore**: `POST /api/v1/backup/restore?filename=...` (a safety backup of the
  current state is written first), then `docker compose ... restart app`.
- **Secrets**: keep `APP_SECRET_KEY`, tokens and `.env` out of git; prefer Docker
  secrets or an env file readable only by root (`chmod 600 .env`).
- **Never** bake `.env`, session files, or secrets into the image; the
  `.dockerignore` already excludes them.

See `docs/SECURITY.md` for the secret-handling policy and
`docs/TROUBLESHOOTING.md` for container issues.

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
