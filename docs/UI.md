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
| System | Setup Wizard, health checks, backup/restore, shutdown |

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
