<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type Bot,
  type Channel,
  type FactoryBatch,
  type FactoryBatchDetail,
  type FactoryDashboard,
  type FactoryTemplate,
  type UserSession,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const batches = ref<FactoryBatch[]>([])
const templates = ref<FactoryTemplate[]>([])
const bots = ref<Bot[]>([])
const channels = ref<Channel[]>([])
const accounts = ref<UserSession[]>([])

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const selectedId = ref('')
const detail = ref<FactoryBatchDetail | null>(null)
const dashboard = ref<FactoryDashboard | null>(null)

const form = ref({
  title: '',
  prefix: '',
  count: 5,
  topic: '',
  style: 'index',
  manager_bot_id: '',
  account_id: '',
  channel_id: '',
})

const managers = computed(() => bots.value.filter((b) => b.kind === 'manager'))
const limitNote = computed(
  () => dashboard.value?.limit_note || detail.value?.batch.limit_note || '',
)
const candidates = computed(() => detail.value?.candidates ?? [])

const STATUS_CLASS: Record<string, string> = {
  available: 'status-ok',
  ready: 'status-ok',
  token_imported: 'status-ok',
  created: 'status-ok',
  occupied: 'status-error',
  invalid: 'status-error',
  failed: 'status-error',
  generated: 'status-unknown',
  checking: 'status-warning',
  creating: 'status-warning',
}

function friendly(e: unknown, fallback: string): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [list, tpl] = await Promise.all([api.factoryBatches(), api.factoryTemplates()])
    batches.value = list.items
    templates.value = tpl
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить пакеты ботов.')
  } finally {
    loading.value = false
  }
  try {
    const [botList, channelList, accountList] = await Promise.all([
      api.bots(),
      api.channels(),
      api.sessions({ enabled: 'true' }),
    ])
    bots.value = botList
    channels.value = channelList.items
    accounts.value = accountList
  } catch {
    bots.value = []
    channels.value = []
    accounts.value = []
  }
}

async function openBatch(id: string) {
  selectedId.value = id
  busy.value = true
  error.value = ''
  try {
    detail.value = await api.factoryBatch(id)
    dashboard.value = await api.factoryDashboard(id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось открыть пакет.')
  } finally {
    busy.value = false
  }
}

async function createBatch() {
  if (!form.value.prefix.trim()) {
    error.value = 'Укажите префикс (латинские буквы, цифры, подчёркивание).'
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await api.createFactoryBatch({
      prefix: form.value.prefix.trim(),
      count: form.value.count,
      title: form.value.title || undefined,
      topic: form.value.topic || undefined,
      style: form.value.style || undefined,
      manager_bot_id: form.value.manager_bot_id || undefined,
      account_id: form.value.account_id || undefined,
      channel_id: form.value.channel_id || undefined,
    })
    detail.value = created
    selectedId.value = created.batch.id
    dashboard.value = await api.factoryDashboard(created.batch.id)
    notice.value = `Пакет создан: ${created.candidates.length} кандидат(ов). Проверьте имена перед созданием.`
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось создать пакет.')
  } finally {
    busy.value = false
  }
}

async function withBatch(fn: () => Promise<unknown>, message = '') {
  if (!selectedId.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await fn()
    detail.value = await api.factoryBatch(selectedId.value)
    dashboard.value = await api.factoryDashboard(selectedId.value)
    if (message) notice.value = message
    await load()
  } catch (e) {
    error.value = friendly(e, 'Операция не выполнена.')
  } finally {
    busy.value = false
  }
}

const checkNames = () =>
  withBatch(() => api.checkFactoryBatch(selectedId.value), 'Проверка имён завершена.')

const createNative = () =>
  withBatch(
    () => api.createFactoryBots(selectedId.value, false),
    'Создание ботов завершено. При необходимости получите токены.',
  )

const createDeepLinks = () =>
  withBatch(
    () => api.createFactoryBots(selectedId.value, true),
    'Ссылки готовы. Откройте их в Telegram и подтвердите создание.',
  )

const fetchTokens = () =>
  withBatch(
    () => api.registerFactoryTokens(selectedId.value),
    'Токены созданных ботов получены и сохранены в зашифрованном виде.',
  )

const regenerate = (candidateId: string) =>
  withBatch(() => api.regenerateFactoryCandidate(candidateId), 'Имя перегенерировано.')

async function bindToChannel() {
  if (!form.value.channel_id) {
    error.value = 'Выберите канал, к которому подключить созданных ботов.'
    return
  }
  await withBatch(
    () =>
      api.bindFactoryBots(selectedId.value, {
        channel_id: form.value.channel_id,
        function: 'reactions',
      }),
    'Боты подключены к каналу. Проверьте права в разделе «Боты».',
  )
}

const queueProgress = computed(() => dashboard.value?.queue ?? null)
const queueBusy = computed(
  () =>
    !!queueProgress.value &&
    (queueProgress.value.queued > 0 || queueProgress.value.running > 0),
)

const startQueue = () =>
  withBatch(
    () => api.factoryEnqueue(selectedId.value, !form.value.account_id),
    'Операции поставлены в очередь. Программа выполнит их по одной — очередь переживёт перезапуск.',
  )

const cancelQueue = () =>
  withBatch(
    () => api.factoryCancel(selectedId.value),
    'Очередь остановлена. Уже созданные боты сохранены.',
  )

const resumeQueue = () =>
  withBatch(() => api.factoryResume(selectedId.value), 'Очередь снова запущена.')

const retryCandidate = (id: string) =>
  withBatch(() => api.factoryRetryCandidate(id), 'Операция снова в очереди.')

const skipCandidate = (id: string) =>
  withBatch(() => api.factorySkipCandidate(id), 'Операция пропущена.')

async function removeBatch(id: string) {
  if (!confirm('Удалить пакет и его кандидатов? Уже созданные боты останутся в списке ботов.')) return
  busy.value = true
  try {
    await api.deleteFactoryBatch(id)
    if (selectedId.value === id) {
      selectedId.value = ''
      detail.value = null
      dashboard.value = null
    }
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось удалить пакет.')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Фабрика ботов <InfoHint topic="bot_factory" /></h2>
    <p class="page-subtitle">
      Подготовка управляемых ботов пачкой: сгенерировать имена, проверить их
      доступность, создать ботов официальным способом Telegram и получить токены.
      Suite не обходит ограничения Telegram и не создаёт ботов без вашего действия.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>
    <div v-if="limitNote" class="card inline-note">
      <b>Важно.</b> {{ limitNote }}
    </div>

    <div class="card">
      <h3>Новый пакет</h3>
      <div class="grid">
        <label class="field">
          <span>Префикс (латиница, цифры, _)</span>
          <input v-model="form.prefix" placeholder="MixMedia" />
        </label>
        <label class="field">
          <span>Сколько ботов (1–50)</span>
          <input v-model.number="form.count" type="number" min="1" max="50" />
        </label>
        <label class="field">
          <span>Тематика (необязательно)</span>
          <input v-model="form.topic" placeholder="новости" />
        </label>
        <label class="field">
          <span>Стиль имён</span>
          <select v-model="form.style">
            <option v-for="t in templates" :key="t.key" :value="t.key">
              {{ t.name_template }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Управляющий бот</span>
          <select v-model="form.manager_bot_id">
            <option value="">— не выбран —</option>
            <option v-for="m in managers" :key="m.id" :value="m.id">
              @{{ m.username || m.title }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Аккаунт для создания (необязательно)</span>
          <select v-model="form.account_id">
            <option value="">— создать по ссылкам —</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">
              {{ a.display_name || a.username || a.telegram_user_id }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Канал для подключения (необязательно)</span>
          <select v-model="form.channel_id">
            <option value="">— не подключать сейчас —</option>
            <option v-for="c in channels" :key="c.id" :value="c.id">
              {{ c.title || c.username || c.reference }}
            </option>
          </select>
        </label>
      </div>
      <button class="primary" :disabled="busy" @click="createBatch">
        {{ busy ? 'Готовим…' : 'Создать пакет' }}
      </button>
    </div>

    <h3>Пакеты</h3>
    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="batches.length === 0" class="card empty">
      Пока нет пакетов. Создайте первый выше.
    </div>
    <table v-else>
      <thead>
        <tr>
          <th>Пакет</th>
          <th>Запрошено</th>
          <th>Создано</th>
          <th>Статус</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in batches" :key="b.id">
          <td>
            <strong>{{ b.title || b.prefix }}</strong>
            <div class="muted">{{ b.prefix }}</div>
          </td>
          <td>{{ b.requested_count }}</td>
          <td>{{ b.created_count }} <span v-if="b.failed_count" class="badge warning">ошибок: {{ b.failed_count }}</span></td>
          <td>{{ b.status_label }}</td>
          <td>
            <div class="actions">
              <button :disabled="busy" @click="openBatch(b.id)">Открыть</button>
              <button class="danger" :disabled="busy" @click="removeBatch(b.id)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="detail" class="card">
      <h3>Пакет: {{ detail.batch.title || detail.batch.prefix }}</h3>
      <div v-if="dashboard" class="muted">
        Свободно: {{ dashboard.counts.available }} ·
        Занято: {{ dashboard.counts.occupied }} ·
        Создано: {{ dashboard.counts.created }} ·
        Токены: {{ dashboard.counts.tokens }}
      </div>
      <div class="toolbar">
        <button :disabled="busy" @click="checkNames">Проверить имена</button>
        <button :disabled="busy" @click="createNative">Создать ботов</button>
        <button :disabled="busy" @click="createDeepLinks">Создать по ссылкам</button>
        <button :disabled="busy" @click="fetchTokens">Получить токены</button>
        <button :disabled="busy || !form.channel_id" @click="bindToChannel">Подключить к каналу</button>
      </div>

      <div class="card inline-note">
        <b>Очередь создания.</b> Программа выполняет операции по одной через
        планировщик, поэтому можно закрыть страницу, а при перезапуске очередь
        продолжится. Уже созданные боты не откатываются.
      </div>
      <div class="toolbar">
        <button class="primary" :disabled="busy" @click="startQueue">Запустить очередь</button>
        <button v-if="queueBusy" class="danger" :disabled="busy" @click="cancelQueue">
          Остановить очередь
        </button>
        <button v-else-if="detail.batch.queue_cancelled" :disabled="busy" @click="resumeQueue">
          Продолжить очередь
        </button>
      </div>
      <div v-if="queueProgress" class="muted">
        Очередь: всего {{ queueProgress.total }} ·
        в очереди {{ queueProgress.queued }} ·
        выполняется {{ queueProgress.running }} ·
        готово {{ queueProgress.success }} ·
        с ошибкой {{ queueProgress.failed }} ·
        пропущено {{ queueProgress.skipped }}
        <span v-if="detail.batch.queue_cancelled"> · остановлена</span>
      </div>

      <p class="muted">
        «Создать ботов» работает через официальный метод Telegram и требует
        подключённого аккаунта. «Создать по ссылкам» открывает t.me/newbot — бот
        создаётся вручную, токен потом запрашивается управляющим ботом.
        «Запустить очередь» обрабатывает все свободные операции по одной.
      </p>

      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Имя</th>
            <th>@username</th>
            <th>Статус</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in candidates" :key="c.id">
            <td>{{ c.index }}</td>
            <td>{{ c.suggested_name }}</td>
            <td>
              <code>{{ c.suggested_username }}</code>
              <div v-if="c.username_message" class="muted">{{ c.username_message }}</div>
            </td>
            <td>
              <span class="status-dot" :class="STATUS_CLASS[c.creation_status] || 'status-unknown'"></span>
              {{ c.creation_status_label }}
              <div class="muted">
                Очередь: {{ c.queue_state_label }}
                <span v-if="c.attempts"> · попыток: {{ c.attempts }}</span>
              </div>
              <div v-if="c.token_mask" class="muted">Токен: {{ c.token_mask }}</div>
              <div v-if="c.error" class="muted">{{ c.error }}</div>
            </td>
            <td>
              <div class="actions">
                <button :disabled="busy" @click="regenerate(c.id)">Перегенерировать</button>
                <button
                  v-if="c.queue_state === 'failed' || c.queue_state === 'cancelled'"
                  :disabled="busy"
                  @click="retryCandidate(c.id)"
                >
                  Повторить
                </button>
                <button
                  v-if="['pending', 'queued', 'failed'].includes(c.queue_state)"
                  :disabled="busy"
                  @click="skipCandidate(c.id)"
                >
                  Пропустить
                </button>
                <a v-if="c.deep_link" :href="c.deep_link" target="_blank" rel="noopener">
                  Открыть в Telegram
                </a>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
