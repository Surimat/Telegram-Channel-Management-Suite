<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type GatewayBrowserPreflight,
  type GatewayBrowserStatus,
  type GatewayChatResult,
  type GatewayModelCapability,
  type GatewayOperationAvailability,
  type GatewayProvider,
  type GatewayProviderList,
  type GatewayRequestRecord,
  type GatewaySettings,
  type GatewayStatus,
  type GatewayUseCase,
  type GatewayWrapper,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

type Tab = 'providers' | 'routing' | 'wrappers' | 'testing' | 'observability'

const tab = ref<Tab>('providers')

const status = ref<GatewayStatus | null>(null)
const providers = ref<GatewayProviderList>({ items: [], kinds: [], strategies: [] })
const settings = ref<GatewaySettings | null>(null)
const wrappers = ref<GatewayWrapper[]>([])
const browser = ref<GatewayBrowserStatus | null>(null)
const useCases = ref<GatewayUseCase[]>([])
const history = ref<GatewayRequestRecord[]>([])
const models = ref<GatewayModelCapability[]>([])
const operations = ref<GatewayOperationAvailability[]>([])
const preflight = ref<GatewayBrowserPreflight | null>(null)
const preparing = ref(false)

const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref(false)

// New provider draft. The API key is write-only: it is sent once and never read
// back — the provider list only ever shows `has_key`.
const draft = ref({
  provider: '',
  kind: 'openai_compatible',
  model: '',
  base_url: '',
  api_key: '',
  cost: 'standard',
  priority: 0,
  enabled: true,
  wrapper_id: '',
  note: '',
})

const testText = ref('Напиши короткое приветствие для канала о путешествиях.')
const testProvider = ref('')
const testStrategy = ref('')
const testResult = ref<GatewayChatResult | null>(null)
const testing = ref(false)

const STATUS_LABELS: Record<string, string> = {
  available: 'Готов',
  unavailable: 'Недоступен',
  needs_setup: 'Нужна настройка',
  auth_required: 'Нужен вход',
  rate_limited: 'Ограничение провайдера',
  network_error: 'Нет сети',
  region_blocked: 'Недоступен в регионе',
  error: 'Ошибка',
  unknown: 'Не проверен',
}

function providerStatusClass(p: GatewayProvider) {
  if (!p.enabled) return 'badge-muted'
  if (p.status === 'available') return 'badge ok'
  if (p.status === 'unknown') return 'badge warning'
  return 'badge danger'
}

function providerStatusLabel(p: GatewayProvider) {
  if (!p.enabled) return 'Выключен'
  return STATUS_LABELS[p.status] ?? p.status
}

function costLabel(cost: string) {
  if (cost === 'free') return 'Бесплатный'
  if (cost === 'cheap') return 'Недорогой'
  if (cost === 'premium') return 'Платный'
  return 'Обычный'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, p, st, w, b, u, m, o] = await Promise.all([
      api.gatewayStatus(),
      api.gatewayProviders(),
      api.gatewaySettings(),
      api.gatewayWrappers(),
      api.gatewayBrowser(),
      api.gatewayUseCases(),
      api.gatewayModels(),
      api.gatewayOperations(),
    ])
    status.value = s
    providers.value = p
    settings.value = st
    wrappers.value = w.items
    browser.value = b
    useCases.value = u.items
    models.value = m.items
    operations.value = o.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить данные шлюза.'
  } finally {
    loading.value = false
  }
}

async function loadPreflight() {
  try {
    preflight.value = await api.gatewayBrowserPreflight()
  } catch {
    preflight.value = null
  }
}

async function prepareBrowser() {
  error.value = ''
  notice.value = ''
  preparing.value = true
  try {
    preflight.value = await api.gatewayBrowserPrepare()
    if (preflight.value.available) {
      notice.value = 'Браузерный движок готов.'
    } else {
      notice.value = 'Браузерный движок недоступен — обычные API-провайдеры работают и без него.'
    }
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось проверить браузер.'
  } finally {
    preparing.value = false
  }
}

async function provisionFree() {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const res = await api.gatewayProvision()
    notice.value = res.message
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось добавить бесплатных провайдеров.'
  } finally {
    busy.value = false
  }
}

function authLabel(auth: string) {
  if (auth === 'no_auth') return 'Без ключа'
  if (auth === 'browser_session') return 'Браузерная сессия'
  return 'Ключ API'
}

function prepClass(status: string) {
  if (status === 'ok') return 'badge ok'
  if (status === 'missing') return 'badge danger'
  return 'badge-muted'
}

async function loadHistory() {
  try {
    history.value = (await api.gatewayRequests()).items
  } catch {
    history.value = []
  }
}

async function addProvider() {
  error.value = ''
  notice.value = ''
  if (!draft.value.provider.trim()) {
    error.value = 'Укажите имя провайдера (например, my-openai).'
    return
  }
  busy.value = true
  try {
    await api.gatewayUpsertProvider({
      provider: draft.value.provider.trim(),
      kind: draft.value.kind,
      model: draft.value.model,
      base_url: draft.value.base_url,
      api_key: draft.value.api_key,
      cost: draft.value.cost,
      priority: Number(draft.value.priority) || 0,
      enabled: draft.value.enabled,
      wrapper_id: draft.value.wrapper_id,
      note: draft.value.note,
    })
    draft.value.api_key = ''
    notice.value = 'Провайдер сохранён. Ключ хранится зашифрованным и больше не показывается.'
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить провайдера.'
  } finally {
    busy.value = false
  }
}

async function toggle(p: GatewayProvider) {
  busy.value = true
  error.value = ''
  try {
    await api.gatewayToggleProvider(p.provider, !p.enabled)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось переключить провайдера.'
  } finally {
    busy.value = false
  }
}

async function remove(p: GatewayProvider) {
  if (!window.confirm(`Удалить провайдера «${p.provider}»?`)) return
  busy.value = true
  error.value = ''
  try {
    await api.gatewayRemoveProvider(p.provider)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось удалить провайдера.'
  } finally {
    busy.value = false
  }
}

async function saveSetting(key: string, value: unknown) {
  error.value = ''
  notice.value = ''
  try {
    settings.value = await api.gatewaySetSetting(key, value)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить настройку.'
  }
}

async function runTest() {
  error.value = ''
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await api.gatewayChat({
      text: testText.value,
      provider: testProvider.value,
      strategy: testStrategy.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Запрос не выполнен.'
  } finally {
    testing.value = false
  }
}

onMounted(async () => {
  await load()
  await loadHistory()
  await loadPreflight()
})
</script>

<template>
  <div>
    <h2 class="page-title">Центр ИИ <InfoHint topic="ai_gateway" /></h2>
    <p class="page-subtitle">
      Единый доступ к ИИ: официальные и OpenAI-совместимые API, бесплатные провайдеры,
      локальные модели и Web-обёртки через вашу собственную браузерную сессию. Шлюз
      автоматически переключается при сбое провайдера.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>
    <div v-if="loading" class="card">Загрузка…</div>

    <template v-else>
      <!-- Summary -->
      <div class="card">
        <h3>Состояние шлюза</h3>
        <p v-if="status">
          Провайдеров: <strong>{{ status.providers }}</strong> ·
          включено: <strong>{{ status.enabled_providers }}</strong> ·
          доступно: <strong>{{ status.available_providers }}</strong>
        </p>
        <p v-if="status" class="muted">
          Браузер для Web-обёрток:
          <span :class="status.browser_available ? 'badge ok' : 'badge-muted'">
            {{ status.browser_available ? 'доступен' : 'недоступен' }}
          </span>
        </p>
        <p v-if="status" class="muted">{{ status.note }}</p>
        <button class="btn" :disabled="busy" @click="provisionFree">
          Добавить бесплатные провайдеры
        </button>
        <p class="muted">
          Бесплатный текстовый доступ без ключа и без браузера. Уже настроенные
          провайдеры не перезаписываются.
        </p>
      </div>

      <div class="tabs">
        <button :class="{ active: tab === 'providers' }" @click="tab = 'providers'">Провайдеры</button>
        <button :class="{ active: tab === 'routing' }" @click="tab = 'routing'">Маршрутизация</button>
        <button :class="{ active: tab === 'wrappers' }" @click="tab = 'wrappers'">Web-обёртки</button>
        <button :class="{ active: tab === 'testing' }" @click="tab = 'testing'">Проверка</button>
        <button :class="{ active: tab === 'observability' }" @click="tab = 'observability'">Журнал</button>
      </div>

      <!-- Providers -->
      <template v-if="tab === 'providers'">
        <div class="card">
          <h3>Добавить провайдера</h3>
          <p class="muted">
            Ключ доступа отправляется один раз и хранится зашифрованным. Он никогда не
            возвращается в интерфейс и не попадает в журналы.
          </p>
          <div class="grid">
            <label class="field">
              <span>Имя (уникальное)</span>
              <input v-model="draft.provider" placeholder="my-openai" />
            </label>
            <label class="field">
              <span>Тип</span>
              <select v-model="draft.kind">
                <option v-for="k in providers.kinds" :key="k.value" :value="k.value">
                  {{ k.label }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>Модель</span>
              <input v-model="draft.model" placeholder="gpt-4o-mini" />
            </label>
            <label class="field">
              <span>Базовый URL (необязательно)</span>
              <input v-model="draft.base_url" placeholder="https://api.example.com/v1" />
            </label>
            <label class="field">
              <span>Ключ доступа (необязательно для локальных)</span>
              <input v-model="draft.api_key" type="password" autocomplete="off" />
            </label>
            <label class="field">
              <span>Стоимость</span>
              <select v-model="draft.cost">
                <option value="free">Бесплатный</option>
                <option value="cheap">Недорогой</option>
                <option value="standard">Обычный</option>
                <option value="premium">Платный</option>
              </select>
            </label>
            <label class="field">
              <span>Приоритет (меньше — раньше)</span>
              <input v-model="draft.priority" type="number" />
            </label>
            <label class="field">
              <span>Web-обёртка (для типа «Web UI»)</span>
              <input v-model="draft.wrapper_id" placeholder="generic" />
            </label>
          </div>
          <label class="checkbox">
            <input v-model="draft.enabled" type="checkbox" />
            <span>Включить сразу</span>
          </label>
          <button class="primary" :disabled="busy" @click="addProvider">
            {{ busy ? 'Сохраняем…' : 'Сохранить провайдера' }}
          </button>
        </div>

        <div class="card">
          <h3>Настроенные провайдеры</h3>
          <p v-if="!providers.items.length" class="muted">
            Пока ни одного провайдера. Добавьте хотя бы один, чтобы шлюз заработал.
          </p>
          <table v-else class="table">
            <thead>
              <tr>
                <th>Провайдер</th>
                <th>Тип</th>
                <th>Стоимость</th>
                <th>Ключ</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in providers.items" :key="p.provider">
                <td>
                  <strong>{{ p.provider }}</strong>
                  <div class="muted">{{ p.model || '—' }}</div>
                </td>
                <td>{{ p.kind_label }}</td>
                <td>{{ costLabel(p.cost) }}</td>
                <td>{{ p.has_key ? 'задан' : '—' }}</td>
                <td>
                  <span :class="providerStatusClass(p)">{{ providerStatusLabel(p) }}</span>
                  <div v-if="p.status_detail" class="muted">{{ p.status_detail }}</div>
                </td>
                <td class="actions">
                  <button @click="toggle(p)">{{ p.enabled ? 'Выключить' : 'Включить' }}</button>
                  <button class="danger" @click="remove(p)">Удалить</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <h3>Матрица моделей и операций</h3>
          <p class="muted">
            «Проверено» означает, что операция реально выполнялась здесь, а не только
            заявлена. «Ключ API» / «Браузерная сессия» — что нужно для работы.
          </p>
          <table v-if="operations.length" class="table">
            <thead>
              <tr><th>Операция</th><th>Готовые провайдеры</th></tr>
            </thead>
            <tbody>
              <tr v-for="op in operations" :key="op.operation">
                <td>{{ op.title }}</td>
                <td>
                  <span v-if="op.providers.length">{{ op.providers.join(', ') }}</span>
                  <span v-else class="muted">нет настроенных — добавьте провайдера</span>
                </td>
              </tr>
            </tbody>
          </table>
          <table class="table">
            <thead>
              <tr>
                <th>Модель</th>
                <th>Операции</th>
                <th>Доступ</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in models" :key="m.provider + m.model">
                <td>
                  <strong>{{ m.provider }}</strong>
                  <div class="muted">{{ m.model }}</div>
                </td>
                <td>
                  <span
                    v-for="op in m.operations"
                    :key="op"
                    class="badge-muted"
                    style="margin-right: 4px"
                  >{{ op }}</span>
                </td>
                <td>{{ authLabel(m.auth) }}<div class="muted">{{ costLabel(m.cost) }}</div></td>
                <td>
                  <span :class="m.verified ? 'badge ok' : 'badge warning'">
                    {{ m.verified ? 'Проверено' : 'Заявлено' }}
                  </span>
                  <div v-if="m.note" class="muted">{{ m.note }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- Routing -->
      <div v-if="tab === 'routing' && settings" class="card">
        <h3>Маршрутизация и лимиты</h3>
        <label class="checkbox">
          <input
            type="checkbox"
            :checked="settings.enabled"
            @change="saveSetting('ai_gateway_enabled', ($event.target as HTMLInputElement).checked)"
          />
          <span>Шлюз включён</span>
        </label>
        <label class="field">
          <span>Стратегия выбора</span>
          <select
            :value="settings.strategy"
            @change="saveSetting('ai_gateway_strategy', ($event.target as HTMLSelectElement).value)"
          >
            <option value="auto">Автоматически</option>
            <option value="free_first">Сначала бесплатные</option>
            <option value="cheapest">Самые дешёвые</option>
            <option value="fastest">Самые быстрые</option>
            <option value="best_quality">Лучшее качество</option>
            <option value="manual">Только вручную</option>
          </select>
        </label>
        <label class="checkbox">
          <input
            type="checkbox"
            :checked="settings.allow_paid"
            @change="saveSetting('ai_gateway_allow_paid', ($event.target as HTMLInputElement).checked)"
          />
          <span>Разрешить платные провайдеры</span>
        </label>
        <label class="checkbox">
          <input
            type="checkbox"
            :checked="settings.web_enabled"
            @change="saveSetting('ai_gateway_web_enabled', ($event.target as HTMLInputElement).checked)"
          />
          <span>Разрешить Web-обёртки</span>
        </label>
        <p class="muted">
          Таймаут {{ settings.timeout_seconds }} с · повторов {{ settings.max_retries }} ·
          записей журнала {{ settings.history_limit }}
        </p>
      </div>

      <!-- Wrappers -->
      <template v-if="tab === 'wrappers'">
        <div class="card">
          <h3>Web-обёртки <InfoHint topic="ai_gateway_wrapper" /></h3>
          <p class="muted">
            Обёртка работает через вашу собственную браузерную сессию и не пытается обходить
            вход, CAPTCHA или проверки. Если сайт требует вход, обёртка честно сообщает
            «Нужен вход» и останавливается.
          </p>
          <p v-if="browser" class="muted">
            Браузерный движок: {{ browser.runtime }} · {{ browser.detail }}
          </p>
          <p v-if="browser" class="muted">{{ browser.docker_note }}</p>
          <div class="actions">
            <button :disabled="preparing" @click="prepareBrowser">
              {{ preparing ? 'Проверка…' : 'Подготовить браузер' }}
            </button>
          </div>
          <template v-if="preflight">
            <p class="muted">{{ preflight.detail }}</p>
            <table class="table">
              <thead>
                <tr><th>Шаг</th><th>Статус</th></tr>
              </thead>
              <tbody>
                <tr v-for="s in preflight.steps" :key="s.id">
                  <td>{{ s.title }}<div class="muted">{{ s.detail }}</div></td>
                  <td>
                    <span :class="prepClass(s.status)">
                      {{ s.status === 'ok' ? 'готово' : s.status === 'missing' ? 'нет' : 'необязательно' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="!preflight.available" class="muted">
              Установить браузер можно так:
              <code>pip install playwright &amp;&amp; playwright install chromium</code>.
              {{ preflight.api_works_without_browser ? 'Обычные API-провайдеры работают и без него.' : '' }}
            </p>
          </template>
          <table class="table">
            <thead>
              <tr><th>Обёртка</th><th>Сайт</th><th>Стоимость</th><th>Статус</th></tr>
            </thead>
            <tbody>
              <tr v-for="w in wrappers" :key="w.id">
                <td><strong>{{ w.name }}</strong><div class="muted">{{ w.note }}</div></td>
                <td>{{ w.website }}</td>
                <td>{{ costLabel(w.cost) }}</td>
                <td>
                  <span :class="w.enabled ? 'badge ok' : 'badge-muted'">
                    {{ w.enabled ? 'Включена' : 'Выключена' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- Testing -->
      <template v-if="tab === 'testing'">
        <div class="card">
          <h3>Проверить запрос</h3>
          <label class="field">
            <span>Текст</span>
            <textarea v-model="testText" rows="3"></textarea>
          </label>
          <label class="field">
            <span>Провайдер (необязательно)</span>
            <select v-model="testProvider">
              <option value="">Автоматически</option>
              <option v-for="p in providers.items" :key="p.provider" :value="p.provider">
                {{ p.provider }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>Стратегия (необязательно)</span>
            <select v-model="testStrategy">
              <option value="">По умолчанию</option>
              <option value="free_first">Сначала бесплатные</option>
              <option value="cheapest">Самые дешёвые</option>
              <option value="fastest">Самые быстрые</option>
            </select>
          </label>
          <button class="primary" :disabled="testing" @click="runTest">
            {{ testing ? 'Выполняем…' : 'Выполнить' }}
          </button>

          <div v-if="testResult" class="result">
            <p>
              <span :class="testResult.ok ? 'badge ok' : 'badge danger'">
                {{ testResult.ok ? 'Успех' : 'Не выполнено' }}
              </span>
              <span v-if="testResult.provider_used" class="muted">
                · {{ testResult.provider_used }} · {{ testResult.latency_ms }} мс
              </span>
              <span v-if="testResult.fallback_used" class="muted"> · запасной провайдер</span>
            </p>
            <pre v-if="testResult.text" class="output">{{ testResult.text }}</pre>
            <p v-if="testResult.error" class="error-text">{{ testResult.error }}</p>
            <ul v-if="testResult.attempts.length > 1" class="muted">
              <li v-for="(a, i) in testResult.attempts" :key="i">
                {{ a.provider }} — {{ a.ok ? 'ок' : a.status }}
              </li>
            </ul>
          </div>
        </div>

        <div class="card">
          <h3>Матрица возможностей</h3>
          <table class="table">
            <thead>
              <tr><th>Задача</th><th>Тип</th><th>Провайдеры</th><th>Доступно</th></tr>
            </thead>
            <tbody>
              <tr v-for="u in useCases" :key="u.group + u.id">
                <td>{{ u.group }}</td>
                <td>{{ u.modality }}</td>
                <td>{{ u.providers.join(', ') || '—' }}</td>
                <td>
                  <span :class="u.available ? 'badge ok' : 'badge-muted'">
                    {{ u.available ? 'Да' : 'Нет' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- Observability -->
      <div v-if="tab === 'observability'" class="card">
        <h3>Журнал запросов</h3>
        <p class="muted">Хранятся только метаданные: провайдер, статус, задержка. Текст
          запроса не сохраняется.</p>
        <button @click="loadHistory">Обновить</button>
        <table v-if="history.length" class="table">
          <thead>
            <tr><th>Время</th><th>Провайдер</th><th>Источник</th><th>Статус</th><th>мс</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in history" :key="r.request_id">
              <td>{{ r.at }}</td>
              <td>{{ r.provider }}</td>
              <td>{{ r.source }}</td>
              <td>
                <span :class="r.ok ? 'badge ok' : 'badge danger'">
                  {{ r.ok ? 'ок' : r.status }}
                </span>
                <span v-if="r.fallback_used" class="muted"> · запасной</span>
              </td>
              <td>{{ r.latency_ms }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">Записей пока нет.</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 12px 0;
}

.tabs button {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-muted);
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
}

.tabs button.active {
  border-color: var(--primary);
  color: var(--primary);
  font-weight: 600;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.result {
  margin-top: 12px;
}

.output {
  white-space: pre-wrap;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  font-size: 13px;
}
</style>
