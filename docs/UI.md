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
| Reactions | Reaction profiles, emoji weights, delays, simulation |
| Rules | Category rules: allowed/preferred/forbidden, confidence, priority |
| AI | Tiny classifier: enable/disable, model, confidence routing |
| Analytics | Content + audience charts with plain-language explanations |
| Settings | All configuration, with descriptions and safe defaults |
| Logs | Log / error center with "Что произошло?" + "Как исправить?" |
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
| `/reactions` | `ReactionsView` | 3 |
| `/sessions` | `SessionsView` | 4 |
| `/sources` | `SourcesView` | 5 |
| `/audience` | `AudienceView` | 5 |
| `/invites` | `InvitesView` | 6 |
| `/ai` | `AiView` (Обзор / Модель / Настройки / Проверка / Диагностика) | 7 |
| `/analytics` | `AnalyticsView` | 8 |
| `/settings` | `SettingsView` | 1 |
| `/logs` | `LogsView` | 1 |
| `/queue` | `QueueView` | 1 |
| `/system` | `SystemView` (Setup Wizard) | 1 |

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

### AI page (`AiView.vue`, PHASE 7)

The AI page follows the "Название / Зачем нужно / Что произойдёт / Безопасное
значение по умолчанию" rule for every complex control, and states clearly that
the AI is optional and that the system works on rules alone when it is off. Tabs:

- **Обзор** — status card (enabled / model / effective) with a plain-language
  reason and "как исправить", lifetime + today metrics.
- **Модель** — list `.gguf` files found, check / load / unload.
- **Настройки** — all AI settings with per-field help (what/why/large effect/safe
  default) sourced from the backend, never hardcoded in the frontend.
- **Проверка** — type a post text, choose mode (`auto`/`rules`/`ai`), see the
  routed result: category, tone, confidence, and which source won.
- **Диагностика** — recent AI records and aggregate metrics.

The UI never shows stack traces or model internals; AI problems appear as
friendly messages with a suggested fix.

### Analytics page (`AnalyticsView.vue`, PHASE 8)

A read-only page that explains the numbers in plain Russian. A period switch
(7/14/30/90/365 дней) reloads `GET /api/v1/analytics/overview`. Content:

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

Three owner-facing additions, all RU-first and consistent with §1–§4:

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
