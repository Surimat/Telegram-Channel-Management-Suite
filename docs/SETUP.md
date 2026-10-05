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
# or: uvicorn backend.app.main:app --reload   (adds watchfiles: pip install "uvicorn[standard]")
```

Open http://127.0.0.1:8000

### Continuous integration

Every push and pull request to `main` or `develop` runs
`.github/workflows/ci.yml`:

- **backend** — `ruff check backend tests` then `pytest` (Python 3.12);
- **frontend** — `npm ci` then `npm run build` (Node 20).

Run the same commands locally before pushing.

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
directories, copies `run.bat` / `stop.bat` / `README.txt`, stages the embedded
Windows runtime, and writes a versioned ZIP (plus a `.sha256` checksum) next to
the output folder. The build is **cross-platform**: it runs on Linux/macOS/Windows
and always produces a Windows runtime.

Runtime staging uses `scripts/build_win_runtime.py`, which downloads the official
Windows **embeddable Python** (`python-3.12.7-embed-amd64.zip`) and the pinned
`win_amd64` wheels from `scripts/win-requirements.lock`, then extracts them flat
into `runtime/site-packages`. No compiler is needed: `pyaes` (a Telethon
dependency with no wheel) is pure Python and is extracted from its sdist.

Options:

```bash
bash scripts/build_portable.sh /path/to/out --no-runtime   # code only, no CPython
bash scripts/build_portable.sh /path/to/out --no-zip       # folder, no archive
bash scripts/build_portable.sh /path/to/out --no-frontend  # reuse built SPA (offline)
```

The lower-level helper is also usable on its own:

```bash
python scripts/build_win_runtime.py /path/to/out/runtime --app-rel ../app
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

The portable ZIP is also built automatically by `.github/workflows/release.yml`
on every `v*` tag. The workflow **creates the GitHub Release** when it does not
exist and attaches the ZIP + `.sha256` to it, so a tag push is a complete release
with no manual step (D-060).

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
`MINIAPP_ENABLED=true` in `.env` (or open **Настройки → Мини-приложение
Telegram**, enter the URL and click **Подключить мини-приложение** — the backend
registers the bot's menu button with Telegram for you).

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
- database (migration state);
- filesystem / writable directories;
- security key (`APP_SECRET_KEY`);
- Telegram API access;
- the Telethon library (user accounts);
- the sessions folder;
- manager bot;
- managed bots;
- automatic reactions;
- user accounts;
- audience;
- invites;
- tiny AI (optional);
- Mini App (optional).

Each item shows: **STATUS**, a description, what it means, and what to do next —
with human-friendly wording instead of raw error codes.

The **System** page also shows the resumable **Мастер первой настройки** (Setup
Wizard): pick a preset (minimal → professional) and follow the steps. It reflects
real system state — a step is never shown as done unless it is, and steps that
need a user account become **optional** when no account is added. You can run the
suite with bots only (no MTProto account): add a channel, connect a bot to it,
and use **Кампании** for invite-link promotion.

The **System** page also has an **Обновления** card: auto-update is off by
default. When enabled it only checks GitHub Releases and can stage a
SHA-256-verified file — it never installs anything without your action.

The dedicated **Web UI → Диагностика** page shows the same subsystem state at any
time (not just first run) and adds:

- a **«Создать отчёт диагностики»** button that downloads a **redacted** report
  (ZIP/JSON/TXT) to hand to a developer — no manual log hunting. It contains
  versions, OS/runtime, database/migration state, module/bot/session/channel
  statuses, queue and AI status, dependency versions and last errors — and never
  tokens, keys, session data, phone numbers, passwords or database contents;
- safe maintenance actions that never delete user data: **Перезапустить
  планировщик**, **Перепроверить Telegram**, **Перепроверить каналы**,
  **Очистить зависшие локальные задания** (the last asks for confirmation).

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

### Account Hub — importing accounts you already own (v1.1)

Open the Web UI → **Аккаунты → Центр аккаунтов (импорт)**. Only use accounts and
files **you own or are authorized to manage**; the suite never searches for or
downloads someone else's session and never bypasses Telegram checks.

The page detects the format first (**«Определяем формат…»**) and shows
`Формат` + `Состояние` before anything is imported:

| Format | How to supply it |
|--------|------------------|
| Telethon `.session` | path to the `.session` file |
| `.session` + companion JSON | path to the `.session`; `<stem>.json` / `<stem>_meta.json` is read for `api_id`/`api_hash`/`phone` (secrets are stored sealed) |
| StringSession | paste the string; it is written to `SESSIONS_DIR` and never shown again |
| Telegram Desktop `tdata` | path to the `tdata` folder (optional converter; see below) |

On success the page says **«Аккаунт подключён.»** and shows the identity. A
permanent warning reminds you that a Telegram auth file is sensitive data.

> **TDATA is optional.** A `tdata` folder is a binary, version-specific format.
> The suite only converts it through an isolated adapter when a reliable,
> permissively-licensed converter is installed; otherwise it reports an honest
> **NOT AVAILABLE** state instead of a fragile best-effort conversion. The source
> `tdata` folder is never modified, copied out, or uploaded. If the converter is
> unavailable, use the `.session` or StringSession route instead.

---

## Adding an optional network route (proxy)

Open the Web UI → **Аккаунты → Сетевые маршруты**. A proxy is an ordinary
connection route for an account (SOCKS5 / HTTP / HTTPS) — it is **not** a way to
avoid Telegram limits. The page states this explicitly.

1. Add a profile (`name`, `kind`, `host`, `port`, optional `username`/`password`).
2. Press **Проверить** for an honest `OK` / `ERROR` / `TIMEOUT` result.
3. Bind the profile to an account. Credentials are sealed and never shown.

---

## Optional lightweight AI («Мини-ИИ»)

The suite works on rules alone; AI is optional. Two levels:

1. **Built-in encoder** — always available, needs **no download and no model
   file** (a dependency-free hashing encoder + prototype classifier). Select
   `encoder` mode on the AI page. Works on the weakest PC.
2. **Lightweight Russian encoder (ruBERT-tiny2)** — optional, ~115 MB. On the AI
   page press **«Установить лёгкую модель»**; the suite downloads the official
   MIT-licensed files, verifies their SHA-256, stores them in the gitignored
   `models/` folder and reports an honest status (`Не установлена` / `Установлена`
   / `Готова`). Use **«Проверить»** to run a real load and **«Удалить модель»** to
   free space. Nothing large is downloaded by default, and the model is never
   bundled into the portable ZIP.

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

## Publishing content (Content Studio, v1.2)

Open the Web UI → **Content Studio** (`/content`) and:

1. **Источники → Добавить источник** — a manual text, an RSS/Atom feed, or a
   Telegram channel (a Telegram source needs a connected account; RSS/Atom/manual
   do not).
2. **Собрать материалы** — new material is imported, duplicates are skipped, and
   per-source moderation (blocked keywords + quiet hours) is applied. A
   `noforwards` source stores only its link.
3. **Материалы → Открыть** — review the text, run **Показать очистку** and apply
   or revert it, **Проверить разметку**, and **Предпросмотр** for a Telegram-like
   view. Set the usage rights; unknown rights warn and add an attribution block.
4. **Публикация** — pick a channel and either **Подготовить публикацию** (publish
   now) or set a time (**Запланировать**). Nothing is sent without this click.
5. **Календарь** — see upcoming publications per channel.

Publishing goes through a bot by default; a user account is used only in the
expanded mode. A scheduled publication is sent by a durable posting tick that
survives restarts. Auto-delete and first comments (when configured) are also
driven by that tick.

---

## Creating a set of bots (Bot Factory, v1.3)

Open the Web UI → **Фабрика ботов** (`/bot-factory`) and:

1. **Новая партия** — give the batch a prefix and how many bots you need
   (optionally a topic/style and the target channel). The page shows the planned
   names and usernames.
2. **Проверить** — asks Telegram whether each username is free. A username is
   never reported free without a real check.
3. **Создать** — for each bot, create it in the official **@BotFather** chat and
   then **Принять** (adopt) it in the page. The factory never registers Telegram
   accounts and never bypasses Telegram limits.
4. **Подключить к каналу** — bind the created bot to your own channel; it follows
   the same binding + rights rules as the **Боты** page.

The managed-bot token is write-only: enter it once and it is sealed; it is never
displayed again.

---

## Joining several computers (LAN Mesh, v1.3, optional)

By default the suite runs on one computer (Standalone). To spread work across
several of your own computers on one local network:

1. On each computer set `MESH_ENABLED=true`, `MESH_MODE=lan_mesh`, a unique
   `MESH_NODE_NAME`, `MESH_PRIORITY` and the shared `MESH_SHARED_SECRET`
   (the same value on every computer), and `APP_HOST=0.0.0.0` so peers can reach
   it. Each computer keeps its **own** SQLite database — never open one database
   file over a network share.
2. Open **Компьютеры** (`/mesh`) → **Найти компьютеры** (or add a peer by
   address when broadcast is blocked).
3. On one computer click **Показать код сопряжения** and enter that short code on
   the other → it becomes trusted. A discovered computer is never trusted
   automatically.
4. The highest-priority online computer that advertises the `telegram`
   capability becomes the coordinator and is the only one that polls Telegram;
   tasks are leased to one computer and handed over if it goes offline.

This is coordination between your own computers — it is not a way to bypass
Telegram limits, rotate proxies aggressively or register accounts.

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
| `MANAGER_RUNTIME_ENABLED` / `MANAGER_RUNTIME_POLL_INTERVAL` | manager-bot command loop + notification forwarding (on by default; short-poll seconds) |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | from https://my.telegram.org |
| `SESSIONS_DIR` | where `.session` files live (outside git) |
| `AI_ENABLED` / `AI_MODEL_PATH` | optional tiny classifier |

See `.env.example` for the full annotated list. Notification toggles (master +
per-category) are edited in the Web UI under Settings; the account permission
probe lives on the Sessions page.

---

## Stopping / restarting

- Local: `Ctrl+C` in the terminal running the app.
- Portable: `stop.bat`.
- Docker: `docker compose -f docker/docker-compose.yml down`.

Pending queue jobs are stored in the database and resumed on the next start.
