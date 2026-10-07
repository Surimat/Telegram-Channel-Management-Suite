# UI — Telegram Channel Management Suite

The Web UI is a first-class part of the product. It must look and feel like a
finished modern desktop/web application, **not** a technical admin panel.

- RU-first, beginner-friendly, informative.
- Responsive (desktop + tablet + phone) because the **same SPA** powers the
  Telegram Mini App (PHASE 9).
- Served as static files by FastAPI so production needs no Node.js.

---

## 1. Design principles

1. **Explain, don't expose.** Show meaning, not internals. Never show raw stack
   traces or error codes as the primary message.
2. **Plain language.** No unexplained jargon. If a term is unavoidable, add a
   tooltip.
3. **Safe by default.** Every setting shows a safe default value.
4. **State at a glance.** Color indicates health: green = ok, amber = attention,
   red = problem, grey = disabled/unknown.
5. **Confirm destructive actions.** Confirmation dialogs for delete/revoke/start
   mass operations.
6. **Always give a next step.** Empty states and errors tell the user what to do.

---

## 2. Sections

| Section | Purpose |
|---------|---------|
| Dashboard | Human-readable overview: health, activity, "what happened" summary |
| Bots | Manager + managed bots: status, health, add/disable/remove |
| Sessions | Telegram user accounts: add (wizard), import, revoke, health |
| Audience | Parsed users: search, filter, tags, sort, export |
| Sources | Audience sources: channels/groups/entities, scan, stats |
| Invites | Invite queue: build, dry-run, approve, run, monitor |
| Кампании | Invite-link campaigns (no account needed) + source quality |
| Reactions | Reaction profiles, emoji weights, delays, simulation |
| Rules | Category rules: allowed/preferred/forbidden, confidence, priority |
| AI | Tiny classifier: enable/disable, model, confidence routing |
| Analytics | Content + audience charts with plain-language explanations |
| Channels | Shared channel registry: add/verify, module toggles, default |
| Settings | All configuration, with descriptions and safe defaults |
| Logs | Log / error center with "Что произошло?" + "Как исправить?" |
| Диагностика | Per-component status + safe actions + redacted report |
| Резервные копии | Backup / restore + configuration export/import (PHASE 10) |
| System | Setup Wizard, health checks, shutdown |

---

## 3. For every non-trivial setting, show

```
Название        — what it is called
Зачем нужно     — why it matters
Что произойдёт  — what happens when changed
По умолчанию    — the safe default value
```

Example (good):

> **Задержка между реакциями**
> Зачем: чтобы реакции выглядели естественно и не нарушали лимиты Telegram.
> Что произойдёт: каждая реакция будет отправлена через случайное время в
> указанном диапазоне.
> По умолчанию: 30–180 секунд.

Example (bad, forbidden):

> `reaction_delay_min=30 reaction_delay_max=180`

---

## 4. Required UI capabilities

- Search, filters, sorting, pagination.
- Loading states, empty states, error states.
- Tooltips / inline help.
- Confirmation dialogs (especially destructive + mass operations).
- Clear, friendly error messages with a suggested fix.
- Color-coded status indicators.
- Responsive layout (mobile-first where practical).

---

## 5. Setup Wizard UX

The wizard runs in **System → Setup Wizard** and checks each item with a
STATUS + explanation:

| Item | Meaning shown to the user |
|------|---------------------------|
| Runtime | "Программа запущена правильно." |
| Database | "Хранилище данных работает." |
| Telegram API | "Доступ к Telegram настроен." |
| Bot API | "Связь с Telegram Bot API работает." |
| Manager bot | "Управляющий бот подключён / ещё не подключён." |
| Managed bots | "Найдено N ботов." |
| User sessions | "Добавлено N аккаунтов." |
| Channel access | "Доступ к каналу есть / нет." |
| Permissions | "Прав достаточно / чего не хватает." |
| Frontend | "Интерфейс собран." |
| Scheduler | "Планировщик работает." |
| Filesystem | "Папки для данных доступны для записи." |

Wording rule — instead of `BOT_TOKEN missing`, write:

> **Управляющий бот ещё не подключён.**
> Создайте бота через @BotFather и вставьте токен сюда.

---

## 6. Telegram Mini App

- Uses the **same** SPA and the **same** API as the Web UI (no second interface).
- Local mode URL: `http://127.0.0.1:<port>`.
- VPS mode URL: public HTTPS URL.
- A public server is **never** required for normal local use.
- Minimum Mini App sections: Dashboard, Bots, Reactions, Queue, Audience
  statistics, System health, Settings.
- Mobile-friendly layout; Telegram WebApp theme integration where useful.
- **Setup helper:** Settings has a "Мини-приложение Telegram" card. The owner
  enters the public HTTPS URL and clicks "Подключить мини-приложение"; the
  backend registers it as the manager bot's Web App menu button
  (`POST /api/v1/miniapp/setup`) and remembers the URL. Non-HTTPS or empty URLs
  are rejected with a plain-language explanation; the bot token is never shown.

---

## 7. Frontend architecture

- Vue 3 + Vite + TypeScript.
- One API client module shared by Web UI and Mini App.
- State management kept light (composition API + a small store).
- Build output copied to `backend/app/static/` and served by FastAPI.
- No runtime Node.js dependency in production.

> Implementation details and component inventory are added in PHASE 1 and grow
> with each phase. Keep this document updated as sections are built.

### Built views (running inventory)

| Route | View | Phase |
|-------|------|-------|
| `/` | `DashboardView` | 1 |
| `/bots` | `BotsView` | 2 |
| `/channels` | `ChannelsView` | hardening |
| `/reactions` | `ReactionsView` | 3 |
| `/sessions` | `SessionsView` (Account Hub + accounts + network routes / proxies) | 4 |
| `/sources` | `SourcesView` (sources + donor discovery) | 5 |
| `/audience` | `AudienceView` | 5 |
| `/invites` | `InvitesView` | 6 |
| `/campaigns` | `CampaignsView` (invite-link campaigns + donor quality) | polish |
| `/ai` | `AiView` (Обзор / Модель / Настройки / Проверка / Диагностика) | 7 |
| `/analytics` | `AnalyticsView` | 8 |
| `/settings` | `SettingsView` | 1 |
| `/logs` | `LogsView` | 1 |
| `/queue` | `QueueView` | 1 |
| `/system` | `SystemView` (Setup Wizard) | 1 |
| `/diagnostics` | `DiagnosticsView` (status + safe actions + redacted report) | polish |
| `/backup` | `BackupView` (backup / restore + config export/import) | 10 |
| `/bot-factory` | `BotFactoryView` | v1.3 |
| `/mesh` | `MeshView` (Компьютеры) | v1.3 |
| `/editorial` | `EditorialView` (Редакция) | v1.4 |
| `/notifications` | `NotificationsView` (Центр уведомлений) | v1.4 |

### Audience & Sources pages (`SourcesView.vue`, `AudienceView.vue`, PHASE 5)

Two linked pages close the audience workflow; both talk only to the existing
PHASE 5 API (no backend change).

**Источники (`/sources`)** — where the audience is collected from:

- Headline cards from `GET /api/v1/audience/dashboard` (sources, unique users,
  new in 7 days, collection errors).
- Add-source form (reference / title / type / account) with a plain-language note
  that closed sources require the account to already be a member.
- Per-source row: type, scan status + completeness (full/partial/hidden list),
  found/new/duplicate/error counts, last scan time, last error.
- **Проверить** (`/check`) reports availability and, when the member list is
  hidden, explains why instead of failing silently.
- **Сканировать** opens a confirmation card built from `/scan/preview` (source,
  type, account, estimated total, chunk size) before starting; while a scan runs
  the page polls `/scan/progress` every few seconds and offers
  Пауза / Продолжить / Отменить. The UI never bypasses Telegram limits — a
  FloodWait or hidden list is shown as a status with a suggested fix.

**Аудитория (`/audience`)** — the collected base:

- Search, source/tag/status filters, `has_username` / `is_premium` toggles, sort
  key + order, and page size; one-click filter presets come from
  `/filters/presets`.
- Paginated table with selection, bulk "add tag" and bulk status change.
- Tag manager (list, rename, delete) via `/tags*`.
- User detail (`/users/{id}`) shows status, score with components, tags, sources,
  masked phone, invite status, and the last invite error.
- **Export** (`/export/preview` → `/export`) writes a local file into `exports/`
  with an explicit opt-in for personal data; **Import** (`/import`) merges CSV or
  JSON without creating duplicates.
- Empty/loading states throughout; all errors use the friendly API envelope.

Both pages are reachable from the desktop sidebar and the Mini App bottom nav.

### Account Hub & bots (`SessionsView.vue`, `BotsView.vue`, v1.1)

**Боты (`/bots`)** explains the three bot kinds in plain language — what each is,
why it exists, what it can do, what it cannot do, and whether it must be added to
a channel:

- **Управляющий бот** — the suite's control bot (commands, status); it lives in
  your personal chat and is **not** added to a channel.
- **Управляемый бот** — a bot the suite creates and drives for automatic actions
  such as reactions. It only works once it is connected to the channel and its
  rights are verified.
- **Обычный бот** — a bot you added yourself and use for reactions; it also needs
  to be added to the channel with the reaction right.

The bot table has a **Канал** column with an honest status (`Готов` / `Нужны
права` / `Не подключён` / `Ошибка` / `Недоступен`), a channel picker, a
**«Подключить к каналу»** button and a **«Проверить»** button. A status is only
`Готов` after a real Telegram check; nothing is claimed without one.

**Центр аккаунтов (`/sessions`)** is the multi-format local importer:

- **«Центр аккаунтов (импорт)»** — detect and import a local artifact by path
  (`.session`, `.session` + companion JSON, or a `tdata` folder) or a
  StringSession string. After choosing a source the page shows
  **«Определяем формат…»** then the detected `Формат`, `Состояние`
  (`валиден`/`повреждён`/`неавторизован`/`не удалось определить`) and, on
  success, **«Аккаунт подключён.»**.
- A permanent warning: *«Файл авторизации Telegram — чувствительные данные.
  Никому его не передавайте.»* A StringSession string is masked, sent once and
  never shown again.
- Each account row has a **«Риск ограничений»** column with a colour band
  (`Healthy`/`Warning`/`FloodWait`/`Restricted`/`Auth required`/`Disabled`) and
  the note that using a user account for mass invites may lead to restrictions —
  no safe invite count is ever promised.
- **Сетевые маршруты (прокси)** are attached to an account as a plain connection
  route; the page states explicitly *«Прокси не отменяет ограничения Telegram.»*

### AI page (`AiView.vue`, PHASE 7)

The AI page follows the "Название / Зачем нужно / Что произойдёт / Безопасное
значение по умолчанию" rule for every complex control, and states clearly that
the AI is optional and that the system works on rules alone when it is off. Tabs:

- **Обзор** — status card (enabled / model / effective) with a plain-language
  reason and "как исправить", lifetime + today metrics.
- **Модель** — list `.gguf` files found, check / load / unload.
- **Настройки** — all AI settings with per-field help (what/why/large effect/safe
  default) sourced from the backend, never hardcoded in the frontend.
- **Проверка** — type a post text, choose mode (`auto`/`rules`/`encoder`/`ai`),
  see the routed result: category, tone, intent, confidence, and which source won.
- **Диагностика** — recent AI records and aggregate metrics.

The UI never shows stack traces or model internals; AI problems appear as
friendly messages with a suggested fix.

**Мини-ИИ (lightweight encoder, v1.1)** — a card on the AI page turns the
optional ruBERT-tiny2 install into one honest action. It shows the state
(`Не установлена` / `Установлена` / `Готова` / `нет библиотеки`), the size on
disk, and three buttons: **«Установить лёгкую модель»**, **«Проверить»**,
**«Удалить модель»**. The model is downloaded only on the owner's click, from the
official repository, verified by SHA-256, stored in the gitignored `models/`
folder, and never bundled. Install never claims success without a real load.

### Analytics page (`AnalyticsView.vue`, PHASE 8)

A read-only page that explains the numbers in plain Russian. A period switch
(7/14/30/90/365 дней) and a channel selector (registry channels + "Все каналы",
defaulting to the registry's default channel) reload
`GET /api/v1/analytics/overview`. Content:

- **Кратко о главном** — the backend's plain-language takeaways (bulleted).
- **Headline cards** — posts, planned reactions (+ success rate), audience (+ new
  7d), sources; each links to the relevant section.
- **Charts** — dependency-free inline SVG: posts per day, reactions planned and
  completed per day, new users per day (`Sparkline.vue`).
- **Bars** — post categories, who classified (rules vs. AI), popular reactions,
  reactions by category, largest sources (`BarList.vue`).
- **Tables/lists** — audience status breakdown, invite outcomes, per-source scan
  effectiveness (discovered/new/duplicates/errors/completeness).

The Dashboard embeds a compact "Что показывают цифры" block (the same summary +
two sparklines) linking to the full page. No charting dependency is added, so the
portable runtime stays light (D-037). The UI shows only friendly numbers and
messages — never stack traces.

**Bot-only mode (v1.1)** — the page works without any user account. When no
account is connected a **«Режим без личного аккаунта»** note explains that the
figures cover posts, reactions and campaigns collected after the bots were
connected, and that *«Историческая информация недоступна этому типу
подключения.»* The analytics window is not hidden — only the unavailable history
is called out honestly.

### Telegram Mini App mode (PHASE 9)

The same SPA runs inside Telegram as a Mini App — there is no second interface
(D-003). On load, `App.vue` asks the `miniapp` Pinia store to bootstrap:

- If `window.Telegram.WebApp` is present with non-empty `initData`, the store
  calls `GET /api/v1/miniapp/config`; when available it posts `initData` to
  `POST /api/v1/miniapp/auth` and shows the app.
- If Telegram has no `initData` (normal browser) the store stays inert and the
  desktop layout is unchanged.
- If config is unavailable or auth fails, a friendly gate screen explains what
  happened and how to fix it (never a stack trace).

Mobile layout: inside Telegram the sidebar is hidden and a fixed bottom
navigation bar appears with the sections required by the brief (Панель, Боты,
Реакции, Очередь, Аналитика, Система, Настройки). The app also honors the
Telegram dark theme (`data-tg-theme="dark"`). The full desktop Web UI is
untouched when not running inside Telegram.

The Telegram WebApp SDK is loaded from `telegram.org` in `index.html`; it is only
used when the page is opened inside Telegram, so the local/portable runtime is
unaffected.

---

## 8. Backup page (`BackupView.vue`, PHASE 10)

The **Резервные копии** section lets a non-technical owner protect and move data:

- A plain-language card explains what a backup is, why it matters, and warns
  that session files are excluded by default.
- **Create backup** has an explicit opt-in checkbox for session files with a
  confirmation dialog; the default (unchecked) is the safe one.
- A table lists backups with date, size, and whether sessions are included, plus
  Download / Restore / Delete actions. Restore requires confirmation and states
  that a safety backup is created first.
- **Configuration** export/import moves rules, reaction profiles and settings as
  a reviewable JSON file; secrets and accounts are never included (the page says
  so). Import has a "replace current configuration" toggle.
- All errors are shown as friendly messages with hints (via the API error
  envelope), never as stack traces.

---

## 9. Hardening additions (post-1.0)

Four owner-facing additions, all RU-first and consistent with §1–§4:
- **Channels page** (`ChannelsView.vue`, `/channels`): the shared channel
  registry. Add a channel once (@username, t.me link or numeric ID), verify it
  with a chosen account, toggle which modules it feeds (реакции/аудитория/
  приглашения/аналитика), and mark a default. The default is auto-promoted when
  the current one is removed. Verification is honest — a privacy/FloodWait result
  shows a plain-language status and hint, never bypassing Telegram. The same
  table now has a **«Бот и реакции»** column: connect a bot to the channel, verify
  its rights, and probe the channel's available reactions — all **bot-only**, no
  user account required.
- **Permission probe** (Sessions page): pick an account + a channel and press
  "Проверить доступ". The result is a plain-language status (`ok`, `partial`,
  `no_access`, `auth_required`, `admin_required`, `privacy_restricted`,
  `flood_wait`, `error`) with a "как исправить" hint. Never reveals session
  content; a FloodWait shows the wait time instead of retrying in a loop.
- **Notifications** (Settings page): a master switch plus per-category toggles
  (`system`, `telegram`, `reactions`, `audience`, `invites`, `ai`) forwarded by
  the manager bot. Each toggle explains what it will send.
- **Manager bot card** (System page): shows connection state, bot username,
  admin count, and pending notifications, with a next-step hint when not
  connected. Tokens are never displayed.

---

## 10. Diagnostics page (`DiagnosticsView.vue`, `/diagnostics`)

The first place a non-technical owner should look when something is off:

- A table lists every subsystem (application, database, Telegram API, manager
  bot, managed bots, accounts, network routes/proxies, channels, bot↔channel
  bindings, channel reaction capabilities, audience, donors, donor candidates,
  reactions, invites, campaigns, AI, scheduler/queue, storage, backup
  destinations, update, portable runtime) with a colour status badge
  (`Готово` / `Внимание` / `Ошибка` / `Не настроено`) and two plain-language
  columns: **«Что это значит»** and **«Что делать»**.
- **«Создать отчёт диагностики»** downloads a **redacted** report (ZIP/JSON/TXT)
  the owner can hand to a developer — no manual log hunting. The page states
  explicitly that the report is cleared of secrets; tokens, keys, session data,
  phone numbers, passwords and database contents are never included.
- **Safe actions** ("Перезапустить планировщик", "Перепроверить Telegram",
  "Перепроверить каналы", "Очистить зависшие локальные задания") are listed with
  a description. Nothing is deleted; the potentially surprising action asks for
  confirmation and is hidden while the scheduler is running.

---

## 11. Product polish: campaigns, destinations, wizard, update

Owner-facing additions that make the suite usable without a user account and
without reading docs:

- **Кампании** (`CampaignsView.vue`, `/campaigns`): invite-link promotion that
  works with the manager bot only. Create a campaign, pick a channel and a
  **risk mode** (conservative by default), create and revoke invite links, and
  see joins/requests. The page also shows **source quality** — an explainable
  band (`Хороший источник` / `Средний` / `Похоже на накрутку` /
  `Недостаточно данных`) plus confidence; when member data is unavailable no bot
  share is invented, it reads "не измерено".
- **Резервные копии → Места хранения** (`BackupView.vue`, `/backup`): each new
  backup is delivered to every enabled destination. A local folder is created
  automatically and cannot be removed; Telegram / Google Drive / Яндекс.Диск are
  optional. Credentials are sealed and never shown; "Проверить" reports
  reachability in plain language.
- **Мастер первой настройки** (System page): a resumable wizard with presets
  (minimal → professional). Every step reflects **real** state and never claims
  to be done unless it is; without an account, session-gated steps are
  `optional`, not required.
- **Обновления** (System page): conservative auto-update — off by default, only
  checks and downloads a **SHA-256-verified** file, and never installs anything
  without an explicit owner action.

---

## 11a. Content Studio page (`ContentStudioView.vue`, `/content`, v1.2)

A four-tab workspace: **Обзор**, **Источники**, **Материалы**, **Календарь**.

- **Обзор** shows status counts (черновики / готовы / запланировано /
  опубликовано сегодня / импортировано / ошибки) and which source kinds are
  available — Telegram needs a connected account, RSS/Atom/manual do not.
- **Источники** adds a source (manual / RSS / Atom / Telegram), runs «Собрать
  материалы» and reports new, duplicate, filtered and moderation-held counts. A
  protected source keeps only its link and says so.
- **Материалы** opens an editor: show/apply/revert the deterministic cleaning,
  check Telegram markup, render a Telegram-like preview, then pick a channel and
  either prepare a publication or schedule it. A held item shows «Удержано» and
  can be released. Unknown rights show a warning and an attribution block.
- **Календарь** is a multi-channel view of upcoming publications and their
  statuses.

Plain-language help topics `content_studio`, `content_source` and
`content_rights` explain the section in beginner terms. The page never claims a
publishing capability it cannot verify and never publishes without a click.

---

## 11b. Bot Factory page (`BotFactoryView.vue`, `/bot-factory`, v1.3)

A guided page that creates a set of worker bots for the owner's channels.

- The owner names a batch (prefix + how many bots, optional topic/style/channel),
  the page shows the planned names and usernames, and «Проверить» asks Telegram
  whether each username is free. A username is never shown as free without a
  real check.
- Creation is explicit: the owner creates the bot in the official @BotFather
  flow and the page **adopts** it. The page never registers Telegram accounts and
  never bypasses Telegram limits.
- **Creation queue (v1.7).** «Запустить очередь» marks the free candidates and
  lets the durable scheduler create them **one at a time**, so the batch survives
  a restart and can be closed safely — already-created bots are never rolled
  back. «Остановить очередь» / «Продолжить очередь» stop and restart it; a
  failed candidate can be «Повторить» or «Пропустить». Each row shows its queue
  state and attempt count, plus a display-only masked token (`1234…xyz`) once the
  token is fetched — the token itself is never shown.
- A created bot can be bound to a channel from here, following the same binding
  and capability rules as the Боты page. The managed-bot token is write-only and
  is never displayed.

---

## 11c. Компьютеры / LAN Mesh page (`MeshView.vue`, `/mesh`, v1.3)

An optional page for the owner's several computers on one local network. It
states up front that the app works on one computer by default and this page is
only needed to join several.

- Shows this computer's identity, role (главный / рабочий / один компьютер) and
  advertised capabilities.
- «Найти компьютеры» looks for peers on the LAN; a manual address form is
  available when broadcast is blocked.
- «Показать код сопряжения» issues a short one-time code; the other computer
  enters it to become trusted. A found computer is never trusted automatically.
- Each peer shows its status (В сети / Не в сети / Занят / Неизвестно) and a
  «Проверить» action that performs a real liveness check.
- The lease table explains that each task runs on exactly one computer and is
  handed to another if that computer goes offline.

No pairing code or shared secret is ever shown after pairing.

---

## 11d. Notification Center page (`NotificationsView.vue`, `/notifications`, v1.4)

A single place to see important events and control how they reach you.

- The top card shows whether notifications are on, how many are pending or
  failed, and whether quiet hours are currently active.
- Category toggles and quiet hours are editable in place; «Объединять похожие»
  merges identical messages so you are never spammed.
- «Отправить тест» proves delivery works for a chosen category and urgency.
- The history lists every event with its category, priority, status and a plain
  «→ что делать» hint when there is a fix; unread items can be marked read.
- The page never shows a token; a Windows toast that is unavailable is reported
  honestly instead of silently failing.

---

## 11e. Редакция / Editorial Workspace page (`EditorialView.vue`, `/editorial`, v1.4)

A team queue over a linked Telegram forum supergroup.

- The owner links a channel and a forum group (with topics) and picks the bot;
  «Проверить права и создать темы» performs a **real** Telegram check. The status
  only becomes «Готова» after Telegram confirms the bot can send messages; a
  missing right stays «Нужны права».
- The board shows one column per queue status (Входящие → В работе → На
  согласование → Запланировано → Опубликовано, plus Отклонено/Пауза/Ошибка); each
  card lists its available actions and moves only when the actor's role allows it.
- Roles are set by **numeric Telegram id** (Редактор / Модератор / Наблюдатель);
  a username is never an identity.
- The audit log lists who moved what and when.
- The page states plainly that the suite owns the order and that topics only
  mirror the queue (cards are not moved between topics by the bot).

---

## 12. Terminology (one word per entity)

Use exactly one term per entity across the UI, docs and API text:

| Entity | Term |
|--------|------|
| Telegram channel/group in the registry | **Канал** |
| MTProto user account | **Аккаунт** |
| Manager/managed Telegram bot | **Бот** |
| Audience origin (channel/group/entity to parse) | **Источник** |
| Reaction configuration set | **Профиль реакции** |
| Unit of scheduled work | **Задание** |
| Durable job list | **Очередь** |
| Account connection route (proxy) | **Сетевой маршрут** (прокси) |
| Collected material for publishing | **Материал** |
| Where material comes from | **Источник контента** |
| Prepared item sent to a channel | **Публикация** |

Do not use "База участников", "Задачи", "Объект", "Пользователь Telegram"
etc. as synonyms for the terms above.

Internal values must never reach the user raw: job kinds (`reaction.job`,
`audience.scan`, `invite.batch`) and statuses (`pending`/`running`/…) are shown as
plain Russian labels (see `QueueView.vue`), just like subsystem statuses.

## What is available now (v1.6)

Two views explain capability state in plain language, both fed by the same
evaluated **capability graph**:

- **Dashboard → "Что уже доступно"** — a short list of capabilities with a badge
  (`Доступно` / `Частично` / `Требует настройки` / `Недоступно` / `Не реализовано`)
  and, when a step is missing, exactly what is missing (e.g. "не хватает: Канал,
  Бот, привязанный к каналу"). `Не реализовано` marks a capability the product
  describes but has not built yet (`media_conversion`) — it can never be shown as
  `Доступно`. As of v1.6 `config_sync` is implemented: it reports `Недоступно`
  until an owner profile exists, `Требуется настройка` with a profile but no
  provider, and `Доступно` once a provider is connected.
- **Diagnostics → "Проверка целостности"** — the consistency report. It shows
  errors and warnings by default; low-confidence "к сведению" findings are hidden
  behind a checkbox so the page never looks alarming for no reason. Each finding
  states what it is, why it matters and what to do.
- **Settings → "Язык интерфейса"** — a RU/EN selector writing the stored
  `language` preference. It localises backend-produced strings (capability titles
  and states); the beginner help catalog stays RU-first.

Wording rules: never claim a right or a capability without a real check; a missing
optional dependency is shown as "требует настройки" or "недоступно", never as an
error; and a capability that needs a session is never presented as blocked — it is
shown with what still works without one.

## 11f. Владелец / Owner page (`OwnerView.vue`, `/owner`, v1.6)

One RU-first page for the local owner profile and configuration sync:

- **Профиль владельца** — shows whether a profile exists, whether protection is
  on, the method (пароль / PIN) and the last login. Buttons: turn protection
  on/off, sign out.
- **Создать профиль** (no profile yet) — password + repeat, method, optional name
  and a non-secret recovery reminder. The page states plainly that the password is
  stored only as a one-way fingerprint and cannot be recovered.
- **Вход владельца** (profile exists, not signed in) — the panel asks for the
  password before the rest of the API answers.
- **Сменить пароль** (signed in).
- **Перенос настроек** (signed in) — choose the provider (Локальная папка /
  Google Drive), connect Google, then upload / preview / apply the encrypted
  bundle with the owner password. It shows the state badge, the last cloud copy
  and its device, and reports a conflict explicitly. The page states that the
  database, sessions and TDATA are never copied and that secrets are excluded.

A `Владелец` link sits at the bottom of the sidebar; the page is reached from the
Promotion Wizard step "Настроить перенос настроек (необязательно)". Help topics
`owner_auth` and `config_sync` explain both in beginner language.
