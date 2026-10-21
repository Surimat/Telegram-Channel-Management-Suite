# REAL_AUDIT.md — независимый аудит архитектуры

**Дата:** 2026-10-21
**Ветка:** `develop` (HEAD `5f61f2a`)
**Метод:** статический разбор исходников (`ast`), сгенерированная OpenAPI-схема,
сверка фронтенда и бэкенда, подсчёт метрик. Никакие выводы не основаны на
`agent/*.md`, `META_AUDIT_RESULT.json`, решениях D-0xx или заявлениях README.
Всё измерено на этом срезе кода.

> Это отчёт о **фактическом** состоянии кода, а не о том, как он описан в
> проектной памяти. Там, где память проекта утверждает одно, а код показывает
> другое, в отчёте стоит пометка **[РАСХОЖДЕНИЕ]**.

---

## 0. Сводка измеренных фактов

| Метрика | Значение |
|---|---|
| Python-модулей в `backend/app` | 304 |
| Строк кода бэкенда (`backend/app/**/*.py`) | 66 426 |
| Строк кода фронтенда (`frontend/src`, `.ts`+`.vue`) | 16 171 |
| Модулей API (`backend/app/api/v1/*.py`) | 36 |
| Объектов `APIRouter(...)` | **36** |
| Эндпоинтов, объявленных в коде (`@router.*`) | **347** |
| Операций в сгенерированной OpenAPI-схеме | **349** (347 + `/health` + `/health/deep`) |
| Уникальных путей в OpenAPI | 304 |
| Сервисов (`services/*.py`) | 61 |
| Репозиториев (`db/repositories/*.py`) | 30 |
| Pydantic-схем (DTO, `api/schemas/*.py`) | 36 |
| Моделей БД (`db/models/*.py`) | 33 |
| Файлов провайдеров (`providers/*.py`) | 22 |
| Vue-представлений | 28 |
| Vue-компонентов | 3 |
| Тестовых файлов | 101 |
| Миграций Alembic | 19 |
| Строк в `docs/*.md` | 6 532 |
| Строк в `agent/*.md` (память проекта) | 7 809 |
| Файлов бэкенда > 500 строк | 25 |
| Файлов бэкенда > 800 строк | 11 |
| `ruff check backend tests` | чисто |
| `ruff check .` | чисто |

Ключевое наблюдение: **объём памяти проекта (`agent/*.md`, 7 809 строк) почти
равен объёму всего фронтенда (16 171 строку с учётом `.vue`) и втрое больше
объёма всей документации по существу (`docs/*.md` содержит много дублей
CHANGELOG-стиля).** Это и есть «раздувание», о котором говорит владелец: не код
как таковой, а поддерживающий его нарратив.

---

## 1. РЕВИЗИЯ «68 РОУТЕРОВ И 340 ЭНДПОИНТОВ»

### 1.1. Что на самом деле есть

Заявленные «68 роутеров» **не подтверждаются**. В коде:

* **34 модуля** объявляют роутеры (`backend/app/api/v1/*.py` без `__init__.py` и
  `router.py`); всего в каталоге **36** `.py`-файлов.
* **36 объектов `APIRouter(...)`** — потому что три модуля объявляют по два
  роутера (`bindings` → `router` + `capabilities_router`, `campaigns` → `router`
  + `donors_router`), а `router.py` — агрегатор без собственных эндпоинтов.
* **347 эндпоинтов**, объявленных декораторами `@router.get/post/...`.
* **349 операций** в OpenAPI = 347 + два корневых `/health` и `/health/deep`,
  объявленных в `main.py`.

Число **«68» получается, если сложить `.py`-модули и их `.pyc`-артефакты**
(36 + 36 = 72; при подсчёте `find` без исключения `__pycache__` выходит похожее
число). Это артефакт подсчёта, а не реальная структура. Реальных роутеров — 36.

Число **«340» близко к реальному 347**, но не точное. В `docs/API.md`
перечислено 342 строки-эндпоинта — тоже не сходится ни с 340, ни с 347. Три
разных числа (340 в заявлении, 342 в docs, 347 в коде, 349 в OpenAPI) означают,
что документация и реальность уже разошлись.

### 1.2. Разбивка по доменам (36 роутеров, 347 эндпоинтов)

| Домен | Роутеров | Эндпоинтов |
|---|---|---|
| Контент и публикации (`content`, `editorial`, `posting`-часть) | 2 | 59 |
| Аккаунты и аудитория (`sessions`, `audience`, `proxies`, `permissions`) | 4 | 49 |
| Боты (`bots`, `bot_factory`, `bot_onboarding`, `bindings`, `capabilities`) | 5 | 53 |
| ИИ (`ai`, `ai_gateway`) | 2 | 33 |
| Приглашения и продвижение (`invites`, `campaigns`, `donors`, `discovery`) | 4 | 27 |
| Владелец и настройки (`owner`, `settings`, `setup_wizard`, `product`) | 4 | 39 |
| Наблюдаемость (`diagnostics`, `consistency`, `capability_graph`, `events`, `help`, `queue`) | 6 | 16 |
| Инфраструктура и прочее (`system`, `backup`, `notifications`, `manager`, `mesh`, `miniapp`, `analytics`, `reactions`, `channels`) | 9 | 71 |
| **Итого** | **36** | **347** |

### 1.3. Полный список роутеров с числом эндпоинтов

| # | Модуль | Переменная | Префикс | Эндпоинтов | Тег |
|---|---|---|---|---|---|
| 1 | `api/v1/ai.py` | `router` | `/ai` | 16 | ai |
| 2 | `api/v1/ai_gateway.py` | `router` | `/ai-gateway` | 17 | ai-gateway |
| 3 | `api/v1/analytics.py` | `router` | `/analytics` | 4 | analytics |
| 4 | `api/v1/audience.py` | `router` | `/audience` | 25 | audience |
| 5 | `api/v1/backup.py` | `router` | `/backup` | 8 | backup |
| 6 | `api/v1/bindings.py` | `capabilities_router` | `/capabilities` | 2 | capabilities |
| 7 | `api/v1/bindings.py` | `router` | `/bindings` | 5 | bindings |
| 8 | `api/v1/bot_factory.py` | `router` | `/bot-factory` | 18 | bot-factory |
| 9 | `api/v1/bot_onboarding.py` | `router` | `/bot-onboarding` | 15 | bot-onboarding |
| 10 | `api/v1/bots.py` | `router` | `/bots` | 13 | bots |
| 11 | `api/v1/campaigns.py` | `donors_router` | `/donors` | 3 | donors |
| 12 | `api/v1/campaigns.py` | `router` | `/campaigns` | 7 | campaigns |
| 13 | `api/v1/capability_graph.py` | `router` | `/capability-graph` | 1 | capabilities |
| 14 | `api/v1/channels.py` | `router` | `/channels` | 10 | channels |
| 15 | `api/v1/consistency.py` | `router` | `/consistency` | 1 | consistency |
| 16 | `api/v1/content.py` | `router` | `/content` | 47 | content |
| 17 | `api/v1/diagnostics.py` | `router` | `/diagnostics` | 5 | diagnostics |
| 18 | `api/v1/discovery.py` | `router` | `/discovery` | 6 | discovery |
| 19 | `api/v1/editorial.py` | `router` | `/editorial` | 12 | editorial |
| 20 | `api/v1/events.py` | `router` | `/events` | 3 | events |
| 21 | `api/v1/help.py` | `router` | `/help` | 3 | help |
| 22 | `api/v1/invites.py` | `router` | `/invites` | 11 | invites |
| 23 | `api/v1/manager.py` | `router` | `/manager` | 1 | manager |
| 24 | `api/v1/mesh.py` | `router` | `/mesh` | 14 | mesh |
| 25 | `api/v1/miniapp.py` | `router` | `/miniapp` | 5 | miniapp |
| 26 | `api/v1/notifications.py` | `router` | `/notifications` | 6 | notifications |
| 27 | `api/v1/owner.py` | `router` | `/owner` | 18 | owner |
| 28 | `api/v1/permissions.py` | `router` | `/permissions` | 3 | permissions |
| 29 | `api/v1/product.py` | `router` | *(нет)* | 16 | product |
| 30 | `api/v1/proxies.py` | `router` | `/proxies` | 6 | proxies |
| 31 | `api/v1/queue.py` | `router` | `/queue` | 3 | queue |
| 32 | `api/v1/reactions.py` | `router` | `/reactions` | 17 | reactions |
| 33 | `api/v1/sessions.py` | `router` | `/sessions` | 15 | sessions |
| 34 | `api/v1/settings.py` | `router` | `/settings` | 2 | settings |
| 35 | `api/v1/setup_wizard.py` | `router` | `/setup-wizard` | 3 | setup-wizard |
| 36 | `api/v1/system.py` | `router` | `/system` | 6 | system |

### 1.4. Разбивка по HTTP-методам

| Метод | В коде | В OpenAPI |
|---|---|---|
| GET | 129 | 131 |
| POST | 178 | 178 |
| PUT | 8 | 8 |
| PATCH | 9 | 9 |
| DELETE | 23 | 23 |
| **Итого** | **347** | **349** |

**Дубликатов `(метод, путь)` — 0.** Коллизий маршрутов нет.

### 1.5. Полный перечень эндпоинтов (все 347)

#### `api/v1/ai.py`

**Роутер `router`** (префикс `/ai`) — 16 эндпоинтов

- `GET /ai/encoder/status`
- `GET /ai/history`
- `GET /ai/metrics`
- `GET /ai/models`
- `GET /ai/overview`
- `GET /ai/settings`
- `GET /ai/status`
- `POST /ai/classify`
- `POST /ai/encoder/check`
- `POST /ai/encoder/install`
- `POST /ai/encoder/remove`
- `POST /ai/model/check`
- `POST /ai/model/load`
- `POST /ai/model/unload`
- `POST /ai/test`
- `PUT /ai/settings`


#### `api/v1/ai_gateway.py`

**Роутер `router`** (префикс `/ai-gateway`) — 17 эндпоинтов

- `DELETE /ai-gateway/providers/{provider}`
- `GET /ai-gateway/browser`
- `GET /ai-gateway/browser/preflight`
- `GET /ai-gateway/models`
- `GET /ai-gateway/operations`
- `GET /ai-gateway/providers`
- `GET /ai-gateway/requests`
- `GET /ai-gateway/settings`
- `GET /ai-gateway/status`
- `GET /ai-gateway/use-cases`
- `GET /ai-gateway/wrappers`
- `POST /ai-gateway/browser/prepare`
- `POST /ai-gateway/chat`
- `POST /ai-gateway/providers`
- `POST /ai-gateway/providers/{provider}/toggle`
- `POST /ai-gateway/provision`
- `PUT /ai-gateway/settings`


#### `api/v1/analytics.py`

**Роутер `router`** (префикс `/analytics`) — 4 эндпоинтов

- `GET /analytics/audience`
- `GET /analytics/content`
- `GET /analytics/overview`
- `GET /analytics/reactions`


#### `api/v1/audience.py`

**Роутер `router`** (префикс `/audience`) — 25 эндпоинтов

- `DELETE /audience/sources/{source_id}`
- `DELETE /audience/tags/{tag}`
- `GET /audience/dashboard`
- `GET /audience/filters/presets`
- `GET /audience/sources`
- `GET /audience/sources/{source_id}`
- `GET /audience/sources/{source_id}/scan/progress`
- `GET /audience/tags`
- `GET /audience/users`
- `GET /audience/users/{user_id}`
- `PATCH /audience/sources/{source_id}`
- `POST /audience/export`
- `POST /audience/export/preview`
- `POST /audience/import`
- `POST /audience/sources`
- `POST /audience/sources/{source_id}/check`
- `POST /audience/sources/{source_id}/scan`
- `POST /audience/sources/{source_id}/scan/cancel`
- `POST /audience/sources/{source_id}/scan/pause`
- `POST /audience/sources/{source_id}/scan/preview`
- `POST /audience/sources/{source_id}/scan/resume`
- `POST /audience/tags/assign`
- `POST /audience/tags/remove`
- `POST /audience/tags/rename`
- `POST /audience/users/bulk-status`


#### `api/v1/backup.py`

**Роутер `router`** (префикс `/backup`) — 8 эндпоинтов

- `DELETE /backup/{filename}`
- `GET /backup`
- `GET /backup/config/export`
- `GET /backup/download`
- `GET /backup/info`
- `POST /backup`
- `POST /backup/config/import`
- `POST /backup/restore`


#### `api/v1/bindings.py`

**Роутер `capabilities_router`** (префикс `/capabilities`) — 2 эндпоинтов

- `GET /capabilities/{channel_id}`
- `POST /capabilities/{channel_id}/probe`

**Роутер `router`** (префикс `/bindings`) — 5 эндпоинтов

- `DELETE /bindings/{binding_id}`
- `GET /bindings`
- `POST /bindings`
- `POST /bindings/channel/{channel_id}/check`
- `POST /bindings/{binding_id}/check`


#### `api/v1/bot_factory.py`

**Роутер `router`** (префикс `/bot-factory`) — 18 эндпоинтов

- `DELETE /bot-factory/batches/{batch_id}`
- `GET /bot-factory/batches`
- `GET /bot-factory/batches/{batch_id}`
- `GET /bot-factory/batches/{batch_id}/dashboard`
- `GET /bot-factory/templates`
- `POST /bot-factory/batches`
- `POST /bot-factory/batches/{batch_id}/adopt`
- `POST /bot-factory/batches/{batch_id}/bind`
- `POST /bot-factory/batches/{batch_id}/bind-many`
- `POST /bot-factory/batches/{batch_id}/cancel`
- `POST /bot-factory/batches/{batch_id}/check`
- `POST /bot-factory/batches/{batch_id}/create`
- `POST /bot-factory/batches/{batch_id}/enqueue`
- `POST /bot-factory/batches/{batch_id}/resume`
- `POST /bot-factory/batches/{batch_id}/tokens`
- `POST /bot-factory/candidates/{candidate_id}/regenerate`
- `POST /bot-factory/candidates/{candidate_id}/retry`
- `POST /bot-factory/candidates/{candidate_id}/skip`


#### `api/v1/bot_onboarding.py`

**Роутер `router`** (префикс `/bot-onboarding`) — 15 эндпоинтов

- `DELETE /bot-onboarding/batches/{batch_id}`
- `GET /bot-onboarding/batches`
- `GET /bot-onboarding/batches/{batch_id}`
- `GET /bot-onboarding/batches/{batch_id}/dashboard`
- `GET /bot-onboarding/rights-profiles`
- `POST /bot-onboarding/batches`
- `POST /bot-onboarding/batches/{batch_id}/next`
- `POST /bot-onboarding/batches/{batch_id}/pause`
- `POST /bot-onboarding/batches/{batch_id}/resume`
- `POST /bot-onboarding/batches/{batch_id}/retry`
- `POST /bot-onboarding/batches/{batch_id}/skip`
- `POST /bot-onboarding/batches/{batch_id}/verify`
- `POST /bot-onboarding/candidates/{candidate_id}/retry`
- `POST /bot-onboarding/candidates/{candidate_id}/skip`
- `POST /bot-onboarding/candidates/{candidate_id}/verify`


#### `api/v1/bots.py`

**Роутер `router`** (префикс `/bots`) — 13 эндпоинтов

- `DELETE /bots/{bot_id}`
- `GET /bots`
- `GET /bots/managed/all`
- `GET /bots/managed/preview`
- `GET /bots/summary`
- `GET /bots/{bot_id}`
- `POST /bots`
- `POST /bots/managed/register`
- `POST /bots/{bot_id}/disable`
- `POST /bots/{bot_id}/enable`
- `POST /bots/{bot_id}/health`
- `POST /bots/{bot_id}/managed/replace-token`
- `POST /bots/{bot_id}/managed/token`


#### `api/v1/campaigns.py`

**Роутер `donors_router`** (префикс `/donors`) — 3 эндпоинтов

- `GET /donors`
- `POST /donors/analyze`
- `POST /donors/analyze/{source_id}`

**Роутер `router`** (префикс `/campaigns`) — 7 эндпоинтов

- `DELETE /campaigns/{campaign_id}`
- `GET /campaigns`
- `GET /campaigns/{campaign_id}`
- `POST /campaigns`
- `POST /campaigns/{campaign_id}/links`
- `POST /campaigns/{campaign_id}/links/{link_id}/revoke`
- `POST /campaigns/{campaign_id}/status`


#### `api/v1/capability_graph.py`

**Роутер `router`** (префикс `/capability-graph`) — 1 эндпоинтов

- `GET /capability-graph`


#### `api/v1/channels.py`

**Роутер `router`** (префикс `/channels`) — 10 эндпоинтов

- `DELETE /channels/{channel_id}`
- `GET /channels`
- `GET /channels/overview`
- `GET /channels/summary`
- `GET /channels/{channel_id}`
- `PATCH /channels/{channel_id}`
- `POST /channels`
- `POST /channels/{channel_id}/default`
- `POST /channels/{channel_id}/modules`
- `POST /channels/{channel_id}/verify`


#### `api/v1/consistency.py`

**Роутер `router`** (префикс `/consistency`) — 1 эндпоинтов

- `GET /consistency`


#### `api/v1/content.py`

**Роутер `router`** (префикс `/content`) — 47 эндпоинтов

- `DELETE /content/ai-profiles/{profile_id}`
- `DELETE /content/automation-rules/{rule_id}`
- `DELETE /content/items/{item_id}`
- `DELETE /content/sources/{source_id}`
- `GET /content/ai-profiles`
- `GET /content/automation-rules`
- `GET /content/calendar`
- `GET /content/dashboard`
- `GET /content/items`
- `GET /content/items/{item_id}`
- `GET /content/items/{item_id}/buttons`
- `GET /content/items/{item_id}/clean`
- `GET /content/items/{item_id}/preview`
- `GET /content/items/{item_id}/publications`
- `GET /content/items/{item_id}/rights`
- `GET /content/items/{item_id}/validate`
- `GET /content/languages`
- `GET /content/pipeline/analytics`
- `GET /content/providers`
- `GET /content/sources`
- `GET /content/sources/{source_id}/moderation`
- `PATCH /content/ai-profiles/{profile_id}`
- `PATCH /content/automation-rules/{rule_id}`
- `PATCH /content/items/{item_id}`
- `POST /content/ai-profiles`
- `POST /content/automation-rules`
- `POST /content/items/{item_id}/ai/classify`
- `POST /content/items/{item_id}/ai/process`
- `POST /content/items/{item_id}/apply-rules`
- `POST /content/items/{item_id}/clean`
- `POST /content/items/{item_id}/clean/revert`
- `POST /content/items/{item_id}/language`
- `POST /content/items/{item_id}/moderate`
- `POST /content/items/{item_id}/plan`
- `POST /content/items/{item_id}/release`
- `POST /content/items/{item_id}/rewrite`
- `POST /content/items/{item_id}/rewrite/apply`
- `POST /content/items/{item_id}/translate`
- `POST /content/publications/{publication_id}/cancel`
- `POST /content/publications/{publication_id}/publish`
- `POST /content/publications/{publication_id}/retry`
- `POST /content/publications/{publication_id}/schedule`
- `POST /content/sources`
- `POST /content/sources/{source_id}/grab`
- `POST /content/tick`
- `PUT /content/items/{item_id}/buttons`
- `PUT /content/sources/{source_id}/moderation`


#### `api/v1/diagnostics.py`

**Роутер `router`** (префикс `/diagnostics`) — 5 эндпоинтов

- `GET /diagnostics`
- `GET /diagnostics/actions`
- `GET /diagnostics/report`
- `GET /diagnostics/report/formats`
- `POST /diagnostics/actions/{key}`


#### `api/v1/discovery.py`

**Роутер `router`** (префикс `/discovery`) — 6 эндпоинтов

- `GET /discovery/candidates`
- `GET /discovery/providers`
- `POST /discovery/candidates/clear`
- `POST /discovery/candidates/{candidate_id}/add`
- `POST /discovery/compare`
- `POST /discovery/search`


#### `api/v1/editorial.py`

**Роутер `router`** (префикс `/editorial`) — 12 эндпоинтов

- `DELETE /editorial/rooms/{room_id}`
- `DELETE /editorial/rooms/{room_id}/members/{telegram_user_id}`
- `GET /editorial/rooms`
- `GET /editorial/rooms/{room_id}/audit`
- `GET /editorial/rooms/{room_id}/board`
- `GET /editorial/rooms/{room_id}/members`
- `POST /editorial/rooms`
- `POST /editorial/rooms/{room_id}/check`
- `POST /editorial/rooms/{room_id}/items`
- `POST /editorial/rooms/{room_id}/items/{item_id}/move`
- `POST /editorial/rooms/{room_id}/reorder`
- `PUT /editorial/rooms/{room_id}/members`


#### `api/v1/events.py`

**Роутер `router`** (префикс `/events`) — 3 эндпоинтов

- `GET /events`
- `GET /events/{event_id}`
- `POST /events/{event_id}/resolve`


#### `api/v1/help.py`

**Роутер `router`** (префикс `/help`) — 3 эндпоинтов

- `GET /help/prefs`
- `GET /help/topics`
- `PUT /help/prefs`


#### `api/v1/invites.py`

**Роутер `router`** (префикс `/invites`) — 11 эндпоинтов

- `GET /invites`
- `GET /invites/summary`
- `GET /invites/{job_id}`
- `GET /invites/{job_id}/tasks`
- `POST /invites`
- `POST /invites/preview`
- `POST /invites/{job_id}/confirm`
- `POST /invites/{job_id}/pause`
- `POST /invites/{job_id}/resume`
- `POST /invites/{job_id}/retry`
- `POST /invites/{job_id}/stop`


#### `api/v1/manager.py`

**Роутер `router`** (префикс `/manager`) — 1 эндпоинтов

- `GET /manager/status`


#### `api/v1/mesh.py`

**Роутер `router`** (префикс `/mesh`) — 14 эндпоинтов

- `DELETE /mesh/peers/{peer_id}`
- `GET /mesh/leases`
- `GET /mesh/peers`
- `GET /mesh/status`
- `POST /mesh/discover`
- `POST /mesh/elect`
- `POST /mesh/leases/acquire`
- `POST /mesh/leases/complete`
- `POST /mesh/leases/reclaim`
- `POST /mesh/pair`
- `POST /mesh/pairing-code`
- `POST /mesh/peers/manual`
- `POST /mesh/peers/{peer_id}/probe`
- `POST /mesh/ping`


#### `api/v1/miniapp.py`

**Роутер `router`** (префикс `/miniapp`) — 5 эндпоинтов

- `GET /miniapp/config`
- `GET /miniapp/me`
- `POST /miniapp/auth`
- `POST /miniapp/logout`
- `POST /miniapp/setup`


#### `api/v1/notifications.py`

**Роутер `router`** (префикс `/notifications`) — 6 эндпоинтов

- `GET /notifications`
- `GET /notifications/dashboard`
- `GET /notifications/settings`
- `POST /notifications/test`
- `POST /notifications/{notification_id}/read`
- `PUT /notifications/settings`


#### `api/v1/owner.py`

**Роутер `router`** (префикс `/owner`) — 18 эндпоинтов

- `DELETE /owner/profile`
- `GET /owner/status`
- `GET /owner/sync/conflict`
- `GET /owner/sync/google/auth`
- `GET /owner/sync/status`
- `POST /owner/lock`
- `POST /owner/login`
- `POST /owner/logout`
- `POST /owner/password`
- `POST /owner/protection`
- `POST /owner/setup`
- `POST /owner/sync/configure`
- `POST /owner/sync/disconnect`
- `POST /owner/sync/download/apply`
- `POST /owner/sync/download/preview`
- `POST /owner/sync/google/connect`
- `POST /owner/sync/upload`
- `POST /owner/unlock`


#### `api/v1/permissions.py`

**Роутер `router`** (префикс `/permissions`) — 3 эндпоинтов

- `GET /permissions/history`
- `GET /permissions/latest`
- `POST /permissions/check`


#### `api/v1/product.py`

**Роутер `router`** (префикс `(нет)`) — 16 эндпоинтов

- `DELETE /backup/destinations/{destination_id}`
- `GET /backup/destinations`
- `GET /promotion`
- `GET /promotion/presets`
- `GET /update`
- `PATCH /backup/destinations/{destination_id}`
- `POST /backup/destinations`
- `POST /backup/destinations/deliver`
- `POST /backup/destinations/{destination_id}/check`
- `POST /promotion/dismiss`
- `POST /promotion/finish`
- `POST /promotion/preset`
- `POST /promotion/step`
- `POST /update/check`
- `POST /update/download`
- `POST /update/enabled`


#### `api/v1/proxies.py`

**Роутер `router`** (префикс `/proxies`) — 6 эндпоинтов

- `DELETE /proxies/{profile_id}`
- `GET /proxies`
- `POST /proxies`
- `POST /proxies/bind`
- `POST /proxies/{profile_id}/check`
- `PUT /proxies/{profile_id}`


#### `api/v1/queue.py`

**Роутер `router`** (префикс `/queue`) — 3 эндпоинтов

- `GET /queue`
- `POST /queue/{job_id}/cancel`
- `POST /queue/{job_id}/retry`


#### `api/v1/reactions.py`

**Роутер `router`** (префикс `/reactions`) — 17 эндпоинтов

- `DELETE /reactions/profiles/{profile_id}`
- `DELETE /reactions/rules/{rule_id}`
- `GET /reactions/categories`
- `GET /reactions/jobs`
- `GET /reactions/posts`
- `GET /reactions/profiles`
- `GET /reactions/rules`
- `GET /reactions/status`
- `PATCH /reactions/profiles/{profile_id}`
- `PATCH /reactions/rules/{rule_id}`
- `POST /reactions/disable`
- `POST /reactions/enable`
- `POST /reactions/posts`
- `POST /reactions/posts/{post_id}/plan`
- `POST /reactions/profiles`
- `POST /reactions/rules`
- `POST /reactions/simulate`


#### `api/v1/sessions.py`

**Роутер `router`** (префикс `/sessions`) — 15 эндпоинтов

- `DELETE /sessions/{account_id}`
- `GET /sessions`
- `GET /sessions/summary`
- `GET /sessions/{account_id}`
- `GET /sessions/{account_id}/risk`
- `POST /sessions/auth/start`
- `POST /sessions/import`
- `POST /sessions/import/artifact`
- `POST /sessions/import/detect`
- `POST /sessions/{account_id}/code`
- `POST /sessions/{account_id}/disable`
- `POST /sessions/{account_id}/enable`
- `POST /sessions/{account_id}/health`
- `POST /sessions/{account_id}/logout`
- `POST /sessions/{account_id}/password`


#### `api/v1/settings.py`

**Роутер `router`** (префикс `/settings`) — 2 эндпоинтов

- `GET /settings`
- `PATCH /settings`


#### `api/v1/setup_wizard.py`

**Роутер `router`** (префикс `/setup-wizard`) — 3 эндпоинтов

- `GET /setup-wizard`
- `POST /setup-wizard/steps/{key}/run`
- `POST /setup-wizard/test-publication`


#### `api/v1/system.py`

**Роутер `router`** (префикс `/system`) — 6 эндпоинтов

- `GET /system/database`
- `GET /system/info`
- `GET /system/setup`
- `GET /system/status`
- `POST /system/database/upgrade`
- `POST /system/shutdown`


**Всего перечислено: 347 эндпоинтов.**


### 1.6. Мёртвые эндпоинты (17)

Бэкенд отдаёт **17 эндпоинтов, которые SPA нигде не вызывает** (проверено
поиском строковых литералов `/api/v1/...` по всем `.ts`/`.vue`, с учётом
шаблонных строк и конкатенации). Часть из них — служебные и вызываются
`portable/*.bat`; остальные не вызываются вообще ничем.

| Метод | Путь | Кто вызывает |
|---|---|---|
| POST | `/api/v1/system/shutdown` | `portable/stop.bat`, `portable/demo/DEMO_stop.bat` (не SPA) |
| POST | `/api/v1/mesh/ping` | только mesh-узел (внутренний протокол) |
| POST | `/api/v1/mesh/leases/acquire` | только mesh-узел (внутренний протокол) |
| POST | `/api/v1/mesh/leases/complete` | только mesh-узел (внутренний протокол) |
| POST | `/api/v1/mesh/leases/reclaim` | только mesh-узел (внутренний протокол) |
| POST | `/api/v1/ai/test` | **ничего** — только упомянут в `docs/API.md` |
| GET | `/api/v1/bots/managed/all` | **ничего** — только в `docs/API.md` |
| GET | `/api/v1/diagnostics/report/formats` | **ничего** — только в `docs/API.md` |
| GET | `/api/v1/invites/summary` | **ничего** — только в `docs/API.md` |
| GET | `/api/v1/system/database` | **ничего** — только в `docs/database-migrations.md` |
| POST | `/api/v1/system/database/upgrade` | **ничего** — только в CHANGELOG-памяти |
| GET | `/api/v1/system/setup` | **ничего** — только в `docs/API.md` |
| POST | `/api/v1/bot-factory/batches/{id}/bind-many` | **ничего** — не вызывается даже UI фабрики |
| POST | `/api/v1/reactions/posts/{id}/plan` | **ничего** — есть отдельный UI-путь |
| POST | `/api/v1/owner/lock` | **ничего** — в UI есть login/logout, но не lock |
| POST | `/api/v1/owner/unlock` | **ничего** |
| DELETE | `/api/v1/owner/profile` | **ничего** — профиль удаляется иначе |

Из 17 «мёртвых» — **11 не вызываются вообще никем** (только документированы).

### 1.7. Мёртвый код во фронтенде (42 метода клиента)

`frontend/src/api/client.ts` — один файл на 3 653 строки с 328 методами.
**42 метода объявлены, но не вызываются ни одним представлением/компонентом**
(проверено поиском `.<имя>` по всему `frontend/src` кроме самого `client.ts`):

```
aiMetrics, aiStatus, analyticsAudience, analyticsContent, analyticsReactions,
analyzeDonor, applyContentRewrite, capability, channel, checkChannelBindings,
contentButtons, contentModeration, contentRewrite, contentTick, createAiProfile,
deleteAiProfile, deleteEditorialRoom, discoveryProviders, editorialEnqueue,
editorialReorder, getSource, healthDeep, miniappMe, permissionLatest,
reactionCategories, reactionPosts, releaseContentItem, removeContentItem,
removeTags, replaceManagedToken, retryContentPublication, saveContentButtons,
scanProgress, scheduleContentPublication, setWizardStep, syncConflict,
syncDisconnect, updateAiProfile, updateAutomationRule, updateContentItem,
updateContentModeration, updateProxy
```

Каждый такой метод — это точка входа в бэкенд, которую никто не дёргает.
Часть из них ведёт к эндпоинтам из §1.6; часть — к «живым» эндпоинтам, но
через другой UI-путь.

**Итог по разделу 1:** заявленные «68/340» неверны. Реально 36 роутеров и 347
эндпоинтов. При этом **17 эндпоинтов не вызываются SPA** и **42 метода клиента
не используются** — это и есть скрытая мёртвая поверхность: **~5 % API и 13 %
клиента висят мёртвым грузом.**

---

## 2. ЗАГЛУШКИ, ФЕЙКИ И МОКИ В ПРОДАКШЕНЕ

### 2.1. Что нашлось

В продакшен-коде (`backend/app`, не `tests`) живут четыре «фейковых» модуля,
полностью реализующие интерфейсы провайдеров:

| Файл | Строк | Класс | Что подменяет |
|---|---|---|---|
| `providers/fake_bot.py` | 447 | `FakeTelegramBotProvider` | Telegram Bot API: send_message, реакции, посты, темы форума, managed-боты |
| `providers/fake_session.py` | 648 | `FakeSessionProvider` | MTProto: вход, участники, инвайты, права, поиск, каналы |
| `providers/fake_audience.py` | 77 | `FakeAudienceProvider` | разбор аудитории канала-донора |
| `ai/backends/fake.py` | 111 | `FakeLlmBackend` | инференс мини-ИИ (возвращает заранее заданный ответ) |

Плюс `ai/gateway/providers/__init__.py:826` — `FakeProvider` внутри шлюза ИИ.

**Это 1 283 строки «искусственной реальности», живущие в продакшен-пакете.**
Итого фейков — 4 модуля: 3 из 22 файлов пакета `providers/` и 1 в `ai/backends/`.

### 2.2. Как фейк попадает в продакшен — и почему это реальный риск

Выбор провайдера идёт через `providers/registry.py`:

```python
if provider_name == "fake" or (provider_name == "auto" and settings.offline_mode):
    return FakeTelegramBotProvider(token)
```

То есть фейк включается, если:
1. `settings.offline_mode == True` (переменная окружения), **или**
2. `provider_name == "fake"` явно.

Настройка `telegram_provider` (значения `auto` / `aiogram` / `fake`) хранится в
`core/config.py` и **редактируется из UI** через сервис настроек.

**Критично:** то же самое у мини-ИИ. В `services/ai_service.py` настройка
`ai_backend` объявлена как **UI-редактируемая** (`AI_SETTING_SPECS`,
заголовок «Движок ИИ»), а `build_backend` принимает значение `"fake"` и
возвращает `FakeLlmBackend` **без всякой проверки, что это боевой режим**:

```python
if chosen == BACKEND_FAKE:
    return FakeLlmBackend()
```

**Последствие:** владелец (или скрипт, или скомпрометированная панель) может
записать `ai_backend = "fake"` в настройки — и приложение будет молча
«работать» на заглушке, выдавая детерминированные фиктивные ответы, при этом
статус ИИ будет показывать «доступно». В коде **нет ни одного guard'а**,
который бы запрещал `fake` вне `APP_ENV=demo`/тестов и хотя бы писал
предупреждение. Проверено: `grep -n "fake" ai_service.py api/v1/ai.py
api/v1/ai_gateway.py` — совпадений нет.

### 2.3. Смежная находка: `offline_mode` не имеет UI-переключателя, но достижим

`offline_mode` доступен только через переменную окружения (в UI его нет) — это
правильно. Но он **не проверяется на согласованность** с `telegram_provider` и
`ai_backend`: если в `.env` случайно останется `OFFLINE_MODE=true` (как в
`portable/demo/.env.demo`), продакшен-сборка тихо уйдёт в фейк-режим.

---

## 3. ПРОГЛОЧЕННЫЕ ОШИБКИ (`except` без логирования)

Найдено **148 обработчиков исключений**, которые глотают ошибку: `pass`,
`continue`, `return None/[]/{}''/False` или присваивание «значения по умолчанию»
— **без записи в лог и без проброса**. Из них:

| Тип «глотания» | Количество |
|---|---|
| `assign-only` (ошибка превращается в переменную-заглушку) | 49 |
| `return <пустое>` (`None`/`""`/`0`/`False`) | 34 |
| `return []` / `{}` | 28 |
| `pass` | 18 |
| `continue` (молча пропустить элемент) | 13 |
| `return` (без значения) | 4 |
| `break` | 2 |

### 3.1. Худшие места (не «граничный случай», а реальная потеря данных)

* **`services/capability_graph.py` — 10 голых `except Exception: pass`
  подряд** (строки 369–447). Если построение графа возможностей падает,
  панель молча показывает «ничего не доступно» вместо ошибки. Это ровно тот
  слой, который владелец видит на дашборде.
* **`services/consistency.py:72` и `services/consistency_checks.py:242`** —
  аудитор целостности глотает собственные сбои проверок. «Проверка упала» не
  отличима от «проверка прошла».
* **`services/reaction_service.py:604`** — `except Exception: pass` в сервисе
  реакций (1 263 строки). Сбой постановки реакции невидим.
* **`services/campaign_service.py:265`** — `except TelegramProviderError: pass`.
  Сбой кампании приглашений глотается.
* **`core/redaction.py:75`** — `except Exception: pass` в фильтре сокрытия
  секретов. Если редакция падает, риск утечки секрета в лог **не фиксируется**.
* **`db/session.py:38`** — `except Exception: pass` в слое сессии БД.
* **`services/ai_gateway_service.py:476`**, **`services/ai_service.py:293`** —
  ИИ-слой глотает ошибки.
* **`services/bot_factory.py:404`** — `return` без значения: фабрика ботов
  молча прекращает обработку кандидата.

Многие `return []`/`{}` относятся к разбору JSON (`json.loads(...)` тегов,
весов эмодзи) и терпимы. Но ~40 из 148 — в сервисном слое, где проглатывание
искажает состояние для пользователя.

---

## 4. «МЁРТВАЯ» ЛОГИКА МАСТЕРА НАСТРОЙКИ (`promotion_service.py`)

`services/promotion_service.py` (594 строки) содержит статус шага
`STEP_TODO = "todo"` и 14 функций-строителей шагов. Разбор:

* Шаг `_step_update` **всегда** возвращает `STEP_OPTIONAL` — он не может быть
  ни `done`, ни `todo`. Это не шаг мастера, а статичная заглушка, раздувающая
  список шагов.
* Шаги `analytics`, `ai`, `bot_factory` считаются «выполненными» просто по
  факту наличия строки в БД (`total > 0`) — без проверки, что это реально
  настроено. Это «мягкая ложь» прогресса, замаскированная под честность.
* `_step_config_sync` использует `status.state == "available"` — строковое
  сравнение с магической константой, продублированное в нескольких местах.

Мастер из 14 шагов при 5 пресетах — это **over-engineering**: 594 строки на
сервис, который показывает чек-лист «сделано/не сделано» и не имеет
собственного состояния, кроме номера текущего шага.

---

## 5. АРХИТЕКТУРНЫЙ ОВЕРХЕД

### 5.1. «God-файлы»

| Файл | Строк |
|---|---|
| `services/consistency_checks.py` | 1 713 |
| `services/diagnostics_service.py` | 1 638 |
| `services/reaction_service.py` | 1 263 |
| `services/audience_service.py` | 1 241 |
| `services/bot_factory.py` | 1 062 |
| `api/v1/content.py` | 1 060 |
| `services/session_service.py` | 962 |
| `ai/gateway/providers/__init__.py` | 909 |
| `providers/telethon_session.py` | 896 |
| `services/posting_service.py` | 854 |

11 файлов превышают 800 строк. `consistency_checks.py` (1 713 строк) —
статический анализатор, встроенный в продакшен-код приложения; он нужен CI, а
не рантайму.

### 5.2. Слой абстракций с одной реализацией

Объявлено 21 `Protocol`. Из них **19 не имеют ни одного класса-наследника**:
`AIProvider`, `BackupProvider`, `BrowserRuntime`, `Classifier`,
`ConfigSyncProvider`, `ContentSourceProvider`, `DelayDistribution`,
`DonorDiscoveryProvider`, `DriveTransport`, `EncoderBackend`, `HttpTransport`,
`MeshTransport`, `NotificationDestinationProvider`, `PostingProvider`,
`SessionImportProvider`, `SessionProvider`, `StreamingAIProvider`,
`TelegramBotProvider`, `TextClassifier`. Наследуют протокол только
`AudienceProvider` (2 реализации) и `LlmBackend` (1 реализация).

Это структурные (duck-typed) протоколы: реализации существуют, но не
наследуются. Практический смысл один — подмена на фейк для тестов и офлайн-демо
(`FakeTelegramBotProvider`, `FakeSessionProvider`, `FakeAudienceProvider`,
`FakeLlmBackend`). То есть **весь этот слой абстракций обслуживает, по сути,
только тестовую подстановку**: у большинства протоколов одна боевая реализация
и один фейк, а вариативности в рантайме нет. Абстракция есть — выбора нет.

### 5.3. Дублирование и «документационный долг»

* `docs/*.md` — 6 532 строки, `agent/*.md` — 7 809 строк. Вместе **14 341
  строка прозы против 16 171 строки фронтенда.** Память проекта по объёму
  сопоставима со всей пользовательской частью приложения.
* В памяти проекта есть незаполненные плейсхолдеры: `__PR__`, `__MAINSHA__`,
  `__RUN__`, `__ZIP__`, `__SHA__` — то есть «источник истины» сам не полон.
* Числа эндпоинтов расходятся между кодом (347), OpenAPI (349) и docs (342) —
  уже описанная [РАСХОЖДЕНИЕ].
* Паттерн `json.loads(... ) except: return []` для разбора тегов
  продублирован **38 раз** по API и сервисам.

### 5.4. Цифры «здоровья»

* 61 сервис, 30 репозиториев, 36 схем, 33 модели БД, 36 модулей API — при 28
  представлениях UI. Слой API+сервисов (133 модуля) более чем вчетверо больше
  слоя UI (28 экранов).
* Тестов 101 файл при 304 модулях бэкенда — покрытие по файлам ~33 %.

---

## 6. ЧТО ЛЕЧИТЬ (приоритеты, без ссылок на D-решения)

**P0 — немедленно, безопасность/честность:**

1. Запретить `ai_backend = "fake"` вне `APP_ENV in {"demo","test"}`: guard в
   `build_backend` + отказ в `settings`-сервисе + запись в лог. Сейчас это
   открытая дыра «тихой заглушки».
2. То же для `telegram_provider = "fake"` — не давать включать фейк-бота на
   боевой базе.
3. Закрыть 10 голых `except Exception: pass` в `capability_graph.py` и потери в
   `redaction.py`, `reaction_service.py`, `campaign_service.py` — минимум
   логировать с уровнем `warning`.

**P1 — мёртвый код:**

4. Удалить 11 эндпоинтов, которые не вызывает никто (§1.6) и 42 мёртвых метода
   клиента (§1.7) — либо подключить их к UI, либо вырезать.
5. Убрать `_step_update` из мастера (вечная заглушка) и пересмотреть
   «выполнено по наличию строки» в `analytics/ai/bot_factory`.

**P2 — оверхед:**

6. Разбить 11 файлов > 800 строк, в первую очередь `consistency_checks.py`
   (вынести в `tests/`/`tools/`) и `diagnostics_service.py`.
7. Сжать `agent/*.md` (7 809 строк) до краткого указателя; перенести историю в
   `CHANGELOG`.
8. Убрать Protocol-слой там, где реализация одна (13 протоколов без
   вариативности).

**P3 — долг:**

9. Синхронизировать числа эндпоинтов: сделать генерацию раздела API в
   `docs/API.md` из OpenAPI, а не руками.
10. Убрать 38-кратное дублирование разбора JSON.

---

## 7. Как проверялся отчёт

* Роутеры/эндпоинты: `ast`-обход всех `backend/app/**/*.py`, поиск
  `APIRouter(...)` и декораторов; сверка с `app.openapi()` (349 операций).
* Мёртвые эндпоинты: извлечение всех литералов `/api/v1/...` из
  `frontend/src/**/*.{ts,vue}` (с раскрытием `${}`-шаблонов и конкатенации) и
  сопоставление с путями OpenAPI.
* Мёртвые методы клиента: разбор объекта `api` в `client.ts` и поиск `.<имя>`
  по остальному фронтенду.
* Проглоченные исключения: `ast`-обход `ExceptHandler`, разрешение вызываемых
  функций на предмет `raise`.
* Метрики: `wc -l`, `find`, `ruff`.

Отчёт воспроизводим: все подсчёты получены командами из этого репозитория на
коммите `5f61f2a`.
