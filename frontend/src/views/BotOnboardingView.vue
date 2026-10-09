<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type Bot,
  type Channel,
  type OnboardingBatch,
  type OnboardingBatchDetail,
  type OnboardingDashboard,
  type OnboardingRightsProfile,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const batches = ref<OnboardingBatch[]>([])
const profiles = ref<OnboardingRightsProfile[]>([])
const bots = ref<Bot[]>([])
const channels = ref<Channel[]>([])

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const selectedId = ref('')
const detail = ref<OnboardingBatchDetail | null>(null)
const dashboard = ref<OnboardingDashboard | null>(null)
const selectedBotIds = ref<string[]>([])

const form = ref({
  channel_id: '',
  rights_profile: 'reactions',
})

const readyBots = computed(() =>
  bots.value.filter((b) => b.kind !== 'manager' && !!(b.username || b.title)),
)
const candidates = computed(() => detail.value?.candidates ?? [])
const progress = computed(() => dashboard.value?.progress ?? null)
const queueActive = computed(() => (progress.value?.active ?? 0) > 0)

const STATUS_CLASS: Record<string, string> = {
  ready: 'status-ok',
  queued: 'status-unknown',
  waiting_confirmation: 'status-warning',
  verifying: 'status-warning',
  needs_permission: 'status-warning',
  failed: 'status-error',
  skipped: 'status-unknown',
}

function friendly(e: unknown, fallback: string): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [list, prof] = await Promise.all([
      api.onboardingBatches(),
      api.onboardingRightsProfiles(),
    ])
    batches.value = list.items
    profiles.value = prof
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить очереди подключения.')
  } finally {
    loading.value = false
  }
  try {
    const [botList, channelList] = await Promise.all([api.bots(), api.channels()])
    bots.value = botList
    channels.value = channelList.items
  } catch {
    bots.value = []
    channels.value = []
  }
}

async function openBatch(id: string) {
  selectedId.value = id
  busy.value = true
  error.value = ''
  try {
    detail.value = await api.onboardingBatch(id)
    dashboard.value = await api.onboardingDashboard(id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось открыть очередь.')
  } finally {
    busy.value = false
  }
}

function toggleBot(id: string) {
  const set = new Set(selectedBotIds.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  selectedBotIds.value = [...set]
}

async function createBatch() {
  if (!form.value.channel_id) {
    error.value = 'Выберите канал, к которому подключать ботов.'
    return
  }
  if (selectedBotIds.value.length === 0) {
    error.value = 'Отметьте хотя бы одного бота.'
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await api.createOnboardingBatch({
      bot_ids: selectedBotIds.value,
      channel_id: form.value.channel_id,
      rights_profile: form.value.rights_profile,
    })
    detail.value = created
    selectedId.value = created.batch.id
    dashboard.value = await api.onboardingDashboard(created.batch.id)
    notice.value = `Очередь создана: ${created.candidates.length} бот(ов). Откройте ссылки по одному и подтвердите в Telegram.`
    selectedBotIds.value = []
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось создать очередь.')
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
    detail.value = await api.onboardingBatch(selectedId.value)
    dashboard.value = await api.onboardingDashboard(selectedId.value)
    if (message) notice.value = message
    await load()
  } catch (e) {
    error.value = friendly(e, 'Операция не выполнена.')
  } finally {
    busy.value = false
  }
}

const nextBot = () =>
  withBatch(
    () => api.onboardingNext(selectedId.value),
    'Обработан следующий бот очереди.',
  )

const verifyAll = () =>
  withBatch(
    () => api.onboardingVerifyAll(selectedId.value),
    'Права всех ботов проверены по ответу Telegram.',
  )

const retryFailed = () =>
  withBatch(
    () => api.onboardingRetryFailed(selectedId.value),
    'Неудачные операции снова в очереди.',
  )

const skipRemaining = () =>
  withBatch(() => api.onboardingSkipRemaining(selectedId.value), 'Ожидающие боты пропущены.')

const pauseQueue = () =>
  withBatch(
    () => api.onboardingPause(selectedId.value),
    'Очередь приостановлена. Уже подключённые боты сохранены.',
  )

const resumeQueue = () =>
  withBatch(() => api.onboardingResume(selectedId.value), 'Очередь снова запущена.')

const verifyCandidate = (id: string) =>
  withBatch(() => api.onboardingVerifyCandidate(id), 'Подключение проверено.')

const retryCandidate = (id: string) =>
  withBatch(() => api.onboardingRetryCandidate(id), 'Бот снова в очереди.')

const skipCandidate = (id: string) =>
  withBatch(() => api.onboardingSkipCandidate(id), 'Бот пропущен.')

async function removeBatch(id: string) {
  if (!confirm('Удалить очередь подключения? Уже подключённые боты останутся в канале.')) return
  busy.value = true
  try {
    await api.deleteOnboardingBatch(id)
    if (selectedId.value === id) {
      selectedId.value = ''
      detail.value = null
      dashboard.value = null
    }
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось удалить очередь.')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Подключение ботов к каналу <InfoHint topic="bot_onboarding" /></h2>
    <p class="page-subtitle">
      Массовое подключение уже созданных ботов к каналу. Suite готовит официальную
      ссылку Telegram <code>t.me/&lt;бот&gt;?startchannel&amp;admin=…</code> на каждого
      бота; вы подтверждаете каждого в Telegram, а Suite проверяет, какие права
      Telegram действительно выдал. Очередь выполняет по одному боту за шаг и
      переживает перезапуск. Ограничения Telegram не обходятся.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div class="card">
      <h3>Новая очередь</h3>
      <div class="grid">
        <label class="field">
          <span>Канал</span>
          <select v-model="form.channel_id">
            <option value="">— выберите канал —</option>
            <option v-for="c in channels" :key="c.id" :value="c.id">
              {{ c.title || c.username || c.reference }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Профиль прав</span>
          <select v-model="form.rights_profile">
            <option v-for="p in profiles" :key="p.key" :value="p.key">
              {{ p.title_ru }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="profiles.length" class="muted">
        {{ profiles.find((p) => p.key === form.rights_profile)?.description_ru }}
      </p>

      <h4>Боты ({{ selectedBotIds.length }} выбрано, до 50)</h4>
      <div v-if="readyBots.length === 0" class="card empty">
        Нет ботов. Создайте их в «Фабрике ботов», затем вернитесь сюда.
      </div>
      <div v-else class="chip-list">
        <label v-for="b in readyBots" :key="b.id" class="chip">
          <input
            type="checkbox"
            :checked="selectedBotIds.includes(b.id)"
            @change="toggleBot(b.id)"
          />
          @{{ b.username || b.title }}
        </label>
      </div>

      <button class="primary" :disabled="busy" @click="createBatch">
        {{ busy ? 'Готовим…' : 'Создать очередь' }}
      </button>
    </div>

    <h3>Очереди</h3>
    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="batches.length === 0" class="card empty">
      Пока нет очередей подключения. Создайте первую выше.
    </div>
    <table v-else>
      <thead>
        <tr>
          <th>Канал</th>
          <th>Профиль</th>
          <th>Запрошено</th>
          <th>Готово</th>
          <th>Статус</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in batches" :key="b.id">
          <td>
            <strong>{{ b.channel_label || b.channel_id }}</strong>
          </td>
          <td>{{ b.rights_profile_title }}</td>
          <td>{{ b.requested_count }}</td>
          <td>
            {{ b.ready_count }}
            <span v-if="b.permission_count" class="badge warning">нет прав: {{ b.permission_count }}</span>
            <span v-if="b.failed_count" class="badge warning">ошибок: {{ b.failed_count }}</span>
          </td>
          <td>
            <span v-if="b.completed" class="status-ok">Завершено</span>
            <span v-else-if="b.queue_paused" class="status-warning">Пауза</span>
            <span v-else class="status-unknown">В работе</span>
          </td>
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
      <h3>Очередь: {{ detail.batch.channel_label || detail.batch.channel_id }}</h3>
      <div v-if="progress" class="muted">
        Всего {{ progress.total }} ·
        в очереди {{ progress.queued }} ·
        ожидают подтверждения {{ progress.waiting }} ·
        проверка {{ progress.verifying }} ·
        готово {{ progress.ready }} ·
        нет прав {{ progress.needs_permission }} ·
        ошибок {{ progress.failed }} ·
        пропущено {{ progress.skipped }}
        <span v-if="detail.batch.queue_paused"> · пауза</span>
        <span v-else-if="detail.batch.completed"> · завершено</span>
      </div>

      <div class="toolbar">
        <button :disabled="busy" @click="nextBot">Следующий бот</button>
        <button :disabled="busy" @click="verifyAll">Проверить подключение</button>
        <button :disabled="busy" @click="retryFailed">Повторить ошибки</button>
        <button :disabled="busy" @click="skipRemaining">Пропустить ожидающих</button>
        <button v-if="!detail.batch.queue_paused && queueActive" class="danger" :disabled="busy" @click="pauseQueue">
          Пауза
        </button>
        <button v-else class="primary" :disabled="busy" @click="resumeQueue">Продолжить</button>
      </div>

      <div class="card inline-note">
        <b>Как подключить.</b> Нажмите «Открыть в Telegram» у бота — откроется
        официальное окно добавления бота в канал с запрошенными правами.
        Подтвердите добавление. Затем «Проверить подключение»: Suite прочитает у
        Telegram, какие права выданы на самом деле, и отметит бота «Готов» или
        «Нужны права».
      </div>

      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>@username</th>
            <th>Статус</th>
            <th>Ссылка</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in candidates" :key="c.id">
            <td>{{ c.index }}</td>
            <td>
              <code>{{ c.bot_username }}</code>
              <div v-if="c.bot_title" class="muted">{{ c.bot_title }}</div>
            </td>
            <td>
              <span class="status-dot" :class="STATUS_CLASS[c.status] || 'status-unknown'"></span>
              {{ c.status_label }}
              <span v-if="c.attempts"> · попыток: {{ c.attempts }}</span>
              <div v-if="c.last_error" class="muted">{{ c.last_error }}</div>
            </td>
            <td>
              <a v-if="c.deep_link" :href="c.deep_link" target="_blank" rel="noopener">
                Открыть в Telegram
              </a>
            </td>
            <td>
              <div class="actions">
                <button :disabled="busy" @click="verifyCandidate(c.id)">Проверить</button>
                <button
                  v-if="c.status === 'failed' || c.status === 'needs_permission'"
                  :disabled="busy"
                  @click="retryCandidate(c.id)"
                >
                  Повторить
                </button>
                <button
                  v-if="c.status !== 'ready' && c.status !== 'skipped'"
                  :disabled="busy"
                  @click="skipCandidate(c.id)"
                >
                  Пропустить
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>