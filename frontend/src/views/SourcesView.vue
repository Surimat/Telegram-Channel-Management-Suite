<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  api,
  type AudienceDashboard,
  type AudienceSource,
  type CandidateList,
  type Channel,
  type DiscoveryCompare,
  type DonorCandidate,
  type ScanPreview,
  type ScanResult,
  type UserSession,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const sources = ref<AudienceSource[]>([])
const dashboard = ref<AudienceDashboard | null>(null)
const accounts = ref<UserSession[]>([])
const channels = ref<Channel[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busyId = ref('')

// Add form
const showAdd = ref(false)
const addBusy = ref(false)
const form = ref({
  reference: '',
  title: '',
  source_type: 'unknown',
  account_id: '',
  channel_id: '',
})

// Scan confirmation + preview
const previewFor = ref<AudienceSource | null>(null)
const preview = ref<ScanPreview | null>(null)
const previewBusy = ref(false)
const lastResult = ref<ScanResult | null>(null)

// Donor discovery (v1.1). Candidates are proposals; adding one to sources is
// always an explicit click.
const discovery = ref<CandidateList | null>(null)
const discoveryForm = ref({
  topic: '',
  min_subscribers: 0,
  max_subscribers: 0,
  active_only: false,
})
const discoveryBusy = ref(false)
const discoveryError = ref('')
const selectedCandidates = ref<string[]>([])
const compareResult = ref<DiscoveryCompare | null>(null)

async function loadDiscovery() {
  try {
    discovery.value = await api.discoveryCandidates()
  } catch {
    discovery.value = null
  }
}

async function runDiscovery() {
  discoveryBusy.value = true
  discoveryError.value = ''
  notice.value = ''
  compareResult.value = null
  selectedCandidates.value = []
  try {
    const result = await api.discoverySearch({
      topic: discoveryForm.value.topic,
      min_subscribers: Number(discoveryForm.value.min_subscribers) || 0,
      max_subscribers: Number(discoveryForm.value.max_subscribers) || 0,
      active_only: discoveryForm.value.active_only,
      providers: ['telegram'],
    })
    const failed = result.providers.filter((p) => !p.ok)
    notice.value = failed.length
      ? `Найдено кандидатов: ${result.stored}. ${failed[0].message}`
      : `Найдено кандидатов: ${result.stored}. Добавляйте в источники только вручную.`
    await loadDiscovery()
  } catch (e) {
    discoveryError.value = friendlyError(e)
  } finally {
    discoveryBusy.value = false
  }
}

async function addCandidate(candidate: DonorCandidate) {
  discoveryBusy.value = true
  discoveryError.value = ''
  try {
    await api.discoveryAdd(candidate.id)
    notice.value = `«${candidate.title || candidate.username}» добавлен в источники аудитории.`
    await loadDiscovery()
    await load(true)
  } catch (e) {
    discoveryError.value = friendlyError(e)
  } finally {
    discoveryBusy.value = false
  }
}

function toggleCandidate(id: string) {
  const i = selectedCandidates.value.indexOf(id)
  if (i >= 0) selectedCandidates.value.splice(i, 1)
  else selectedCandidates.value.push(id)
}

async function compareSelected() {
  if (selectedCandidates.value.length < 2) return
  discoveryBusy.value = true
  discoveryError.value = ''
  try {
    compareResult.value = await api.discoveryCompare(selectedCandidates.value)
  } catch (e) {
    discoveryError.value = friendlyError(e)
  } finally {
    discoveryBusy.value = false
  }
}

async function clearCandidates() {
  if (!confirm('Очистить список найденных кандидатов? Уже добавленные источники останутся.')) return
  discoveryBusy.value = true
  try {
    await api.discoveryClear()
    compareResult.value = null
    selectedCandidates.value = []
    await loadDiscovery()
  } catch (e) {
    discoveryError.value = friendlyError(e)
  } finally {
    discoveryBusy.value = false
  }
}

const SCAN_LABELS: Record<string, string> = {
  idle: 'Не сканировался',
  scanning: 'Сканирование…',
  paused: 'Пауза',
  completed: 'Завершено',
  failed: 'Ошибка',
  cancelled: 'Отменено',
}

const COMPLETENESS_LABELS: Record<string, string> = {
  unknown: 'Неизвестно',
  complete: 'Полный список',
  partial: 'Частичный список',
  hidden: 'Список скрыт',
}

const TYPE_LABELS: Record<string, string> = {
  channel: 'Канал',
  group: 'Группа',
  entity: 'Объект',
  unknown: 'Не определён',
}

function scanClass(status: string): string {
  if (status === 'completed') return 'status-ok'
  if (status === 'scanning') return 'status-ok'
  if (status === 'paused' || status === 'idle') return 'status-warning'
  if (status === 'failed' || status === 'cancelled') return 'status-error'
  return 'status-unknown'
}

const anyScanning = computed(() => sources.value.some((s) => s.scan_status === 'scanning'))

function friendlyError(e: unknown): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || 'Произошла ошибка.'
}

async function load(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [list, dash, sess, chans] = await Promise.all([
      api.audienceSources({ limit: '200' }),
      api.audienceDashboard(),
      api.sessions(),
      api.channels({ limit: '200' }),
    ])
    sources.value = list.items
    dashboard.value = dash
    accounts.value = sess
    channels.value = chans.items
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

async function submitAdd() {
  addBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.createSource({
      reference: form.value.channel_id ? undefined : form.value.reference,
      title: form.value.title,
      source_type: form.value.source_type,
      account_id: form.value.account_id || null,
      channel_id: form.value.channel_id || undefined,
    })
    notice.value = 'Источник добавлен. Теперь проверьте его доступность кнопкой «Проверить».'
    form.value = {
      reference: '',
      title: '',
      source_type: 'unknown',
      account_id: '',
      channel_id: '',
    }
    showAdd.value = false
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    addBusy.value = false
  }
}

async function withSource(id: string, fn: () => Promise<unknown>, silent = false) {
  busyId.value = id
  error.value = ''
  notice.value = ''
  try {
    await fn()
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
    if (!silent) loading.value = false
  }
}

const check = (s: AudienceSource) =>
  withSource(s.id, async () => {
    const res = await api.checkSource(s.id)
    notice.value = res.ok
      ? `Источник доступен: ${res.title || res.username || s.reference}. ${
          res.participants_count != null
            ? 'Участников: ' + res.participants_count + '.'
            : ''
        } ${COMPLETENESS_LABELS[res.completeness] ?? ''}`.trim()
      : res.message
  })

const toggle = (s: AudienceSource) =>
  withSource(s.id, () => api.updateSource(s.id, { enabled: !s.enabled }))

function remove(s: AudienceSource) {
  if (!confirm(`Удалить источник «${s.title || s.username || s.reference}»? Собранные участники останутся в базе.`))
    return
  return withSource(s.id, () => api.deleteSource(s.id))
}

async function openScan(s: AudienceSource) {
  previewFor.value = s
  preview.value = null
  lastResult.value = null
  previewBusy.value = true
  error.value = ''
  try {
    preview.value = await api.previewScan(s.id)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    previewBusy.value = false
  }
}

function closeScan() {
  previewFor.value = null
  preview.value = null
  lastResult.value = null
}

async function confirmScan() {
  const s = previewFor.value
  if (!s) return
  previewBusy.value = true
  error.value = ''
  try {
    lastResult.value = await api.startScan(s.id)
    notice.value = 'Сканирование запущено. Прогресс обновляется автоматически.'
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    previewBusy.value = false
  }
}

const pause = (s: AudienceSource) => withSource(s.id, () => api.pauseScan(s.id))
const resume = (s: AudienceSource) => withSource(s.id, () => api.resumeScan(s.id))
const cancel = (s: AudienceSource) => withSource(s.id, () => api.cancelScan(s.id))

let timer: number | undefined
onMounted(async () => {
  await load()
  loadDiscovery()
  timer = window.setInterval(() => {
    if (anyScanning.value) load(true)
  }, 4000)
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div>
    <h2 class="page-title">Источники аудитории <InfoHint topic="source" /></h2>
    <p class="page-subtitle">
      Источник — это канал, группа или объект Telegram, из которого система собирает
      участников. Сканирование никогда не обходит ограничения Telegram: если список
      скрыт или сработал лимит, система честно покажет это.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div v-if="dashboard" class="grid">
      <div class="card">
        <strong>Источников</strong>
        <p class="metric">{{ dashboard.sources_total }}</p>
        <p class="muted">Из них неполных: {{ dashboard.partial_sources }}</p>
      </div>
      <div class="card">
        <strong>Уникальных участников</strong>
        <p class="metric">{{ dashboard.unique_users }}</p>
        <p class="muted">Всего записей: {{ dashboard.total_records }}</p>
      </div>
      <div class="card">
        <strong>Новых за 7 дней</strong>
        <p class="metric">{{ dashboard.new_users_7d }}</p>
      </div>
      <div class="card">
        <strong>Ошибок сбора</strong>
        <p class="metric">{{ dashboard.errors_total }}</p>
      </div>
    </div>

    <div class="toolbar">
      <button class="primary" @click="showAdd = !showAdd">
        {{ showAdd ? 'Отмена' : '+ Добавить источник' }}
      </button>
      <button @click="load()">Обновить</button>
      <RouterLink to="/audience"><button>Перейти к базе участников →</button></RouterLink>
    </div>

    <div v-if="showAdd" class="card">
      <h3>Новый источник</h3>
      <p class="muted">
        Укажите @username, ссылку вида t.me/... или числовой Telegram ID. Для
        закрытых источников аккаунт должен уже состоять в них — иначе Telegram не
        отдаст список участников.
      </p>
      <label v-if="channels.length" class="field">
        <span>Канал из реестра (необязательно)</span>
        <select v-model="form.channel_id">
          <option value="">Указать вручную ниже</option>
          <option v-for="c in channels" :key="c.id" :value="c.id">
            {{ c.title || c.reference }}
          </option>
        </select>
      </label>
      <label v-if="!form.channel_id" class="field">
        <span>Ссылка, @username или ID</span>
        <input v-model="form.reference" placeholder="@channel или https://t.me/channel" />
      </label>
      <label class="field">
        <span>Название (необязательно)</span>
        <input v-model="form.title" placeholder="Понятное имя источника" />
      </label>
      <label class="field">
        <span>Тип источника</span>
        <select v-model="form.source_type">
          <option value="unknown">Определить автоматически</option>
          <option value="channel">Канал</option>
          <option value="group">Группа</option>
        </select>
      </label>
      <label class="field">
        <span>Аккаунт для сканирования (необязательно)</span>
        <select v-model="form.account_id">
          <option value="">Выбрать автоматически</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.display_name || a.username || a.phone_masked || a.id }}
          </option>
        </select>
      </label>
      <button
        class="primary"
        :disabled="addBusy || (!form.reference && !form.channel_id)"
        @click="submitAdd"
      >
        {{ addBusy ? 'Добавляем…' : 'Добавить источник' }}
      </button>
    </div>

    <!-- Scan confirmation -->
    <div v-if="previewFor" class="card">
      <div class="row-between">
        <h3>Проверка перед сканированием</h3>
        <button @click="closeScan">Закрыть</button>
      </div>
      <p v-if="previewBusy" class="muted">Готовим сводку…</p>
      <div v-else-if="preview">
        <p class="muted">{{ preview.notes.join(' ') }}</p>
        <div class="two-cols">
          <p><strong>Источник:</strong> {{ preview.title || preview.username || preview.reference }}</p>
          <p><strong>Тип:</strong> {{ TYPE_LABELS[preview.source_type] ?? preview.source_type }}</p>
          <p><strong>Аккаунт:</strong> {{ preview.account_label || preview.account_id || 'автоматически' }}</p>
          <p>
            <strong>Ожидается участников:</strong>
            {{ preview.estimated_total != null ? preview.estimated_total : 'неизвестно' }}
          </p>
          <p><strong>Режим:</strong> {{ preview.mode }}</p>
          <p><strong>Размер порции:</strong> {{ preview.chunk_size }}</p>
        </div>
        <p class="inline-note">
          Система обработает список порциями и сохранит прогресс. Сканирование можно
          поставить на паузу и продолжить позже; при перезапуске оно возобновится.
        </p>
        <button class="primary" :disabled="previewBusy" @click="confirmScan">
          Начать сканирование
        </button>
      </div>
      <p v-else class="muted">Не удалось построить сводку.</p>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="sources.length === 0" class="card empty">
      Пока нет источников. Нажмите «+ Добавить источник», чтобы указать канал или группу.
    </div>
    <table v-else class="table">
      <thead>
        <tr>
          <th>Источник</th>
          <th>Тип</th>
          <th>Сканирование</th>
          <th>Найдено</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sources" :key="s.id">
          <td>
            <strong>{{ s.title || (s.username ? '@' + s.username : s.reference) }}</strong>
            <div class="muted">
              {{ s.username ? '@' + s.username : '' }}
              <span v-if="s.telegram_id"> · ID {{ s.telegram_id }}</span>
              <span v-if="!s.enabled" class="badge warning">выключен</span>
            </div>
            <div v-if="s.last_error" class="muted error-text">{{ s.last_error }}</div>
          </td>
          <td>{{ TYPE_LABELS[s.source_type] ?? s.source_type }}</td>
          <td>
            <span class="status-dot" :class="scanClass(s.scan_status)"></span>
            {{ SCAN_LABELS[s.scan_status] ?? s.scan_status }}
            <div class="muted">{{ COMPLETENESS_LABELS[s.completeness] ?? s.completeness }}</div>
            <div class="muted">
              {{ s.last_scan_finished_at ? new Date(s.last_scan_finished_at).toLocaleString() : '—' }}
            </div>
          </td>
          <td>
            <div>Найдено: {{ s.discovered_count }}</div>
            <div class="muted">
              Новых: {{ s.new_count }} · Дублей: {{ s.duplicate_count }} · Ошибок: {{ s.error_count }}
            </div>
            <div v-if="s.reported_total != null" class="muted">Всего в Telegram: {{ s.reported_total }}</div>
          </td>
          <td>
            <div class="actions">
              <button :disabled="busyId === s.id" @click="check(s)">Проверить</button>
              <button
                v-if="s.scan_status !== 'scanning'"
                :disabled="busyId === s.id"
                @click="openScan(s)"
              >
                Сканировать
              </button>
              <button v-if="s.scan_status === 'scanning'" :disabled="busyId === s.id" @click="pause(s)">
                Пауза
              </button>
              <button v-if="s.scan_status === 'paused'" :disabled="busyId === s.id" @click="resume(s)">
                Продолжить
              </button>
              <button
                v-if="s.scan_status === 'scanning' || s.scan_status === 'paused'"
                :disabled="busyId === s.id"
                @click="cancel(s)"
              >
                Отменить
              </button>
              <button :disabled="busyId === s.id" @click="toggle(s)">
                {{ s.enabled ? 'Выключить' : 'Включить' }}
              </button>
              <button class="danger" :disabled="busyId === s.id" @click="remove(s)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Donor discovery (v1.1): proposals only, never automatic -->
    <div class="card" style="margin-top: 20px">
      <h3>Автопоиск доноров</h3>
      <p class="muted">
        Поиск каналов-доноров по теме. Найденные каналы — только <strong>кандидаты</strong>;
        в источники аудитории они попадают лишь после явного нажатия. Сбор метрик не обходит
        ограничения Telegram: если данные скрыты, это честно отмечено.
      </p>
      <div v-if="discoveryError" class="error-text">{{ discoveryError }}</div>

      <div v-if="discovery && !discovery.providers.some((p) => p.available)" class="muted">
        Поставщики поиска недоступны:
        <ul>
          <li v-for="p in discovery.providers" :key="p.name">{{ p.title }} — {{ p.message }}</li>
        </ul>
      </div>

      <div class="grid">
        <label class="field">
          <span>Тема или ключевые слова</span>
          <input v-model="discoveryForm.topic" placeholder="Например: новости, технологии" />
        </label>
        <label class="field">
          <span>Мин. подписчиков</span>
          <input v-model.number="discoveryForm.min_subscribers" type="number" placeholder="0" />
        </label>
        <label class="field">
          <span>Макс. подписчиков</span>
          <input v-model.number="discoveryForm.max_subscribers" type="number" placeholder="0" />
        </label>
        <label class="field">
          <span>Только активные</span>
          <input v-model="discoveryForm.active_only" type="checkbox" />
        </label>
      </div>
      <div class="toolbar">
        <button class="primary" :disabled="discoveryBusy || !discoveryForm.topic" @click="runDiscovery">
          {{ discoveryBusy ? 'Ищем…' : 'Найти доноров' }}
        </button>
        <button
          :disabled="discoveryBusy || selectedCandidates.length < 2"
          @click="compareSelected"
        >
          Сравнить выбранные ({{ selectedCandidates.length }})
        </button>
        <button :disabled="discoveryBusy" @click="clearCandidates">Очистить список</button>
      </div>

      <div v-if="compareResult" class="card">
        <strong>Лучший кандидат: {{ compareResult.best_title }}</strong>
        <p class="muted">{{ compareResult.best_reason }}</p>
      </div>

      <table v-if="discovery && discovery.items.length" class="table">
        <thead>
          <tr>
            <th></th>
            <th>Канал</th>
            <th>Подписчики</th>
            <th>Совпадение</th>
            <th>Данные</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in discovery.items" :key="c.id">
            <td>
              <input
                type="checkbox"
                :checked="selectedCandidates.includes(c.id)"
                @change="toggleCandidate(c.id)"
              />
            </td>
            <td>
              <strong>{{ c.title || c.username }}</strong>
              <div class="muted">@{{ c.username }}</div>
              <div v-if="c.summary" class="muted">{{ c.summary }}</div>
            </td>
            <td class="muted">{{ c.subscribers }}</td>
            <td>
              {{ c.fit_title }}
              <div class="muted">{{ Math.round(c.fit_score * 100) }}%</div>
            </td>
            <td class="muted">{{ c.confidence }}</td>
            <td>
              <button v-if="!c.added" :disabled="discoveryBusy" @click="addCandidate(c)">
                Добавить в источники
              </button>
              <span v-else class="badge ok">уже источник</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">Кандидатов пока нет. Задайте тему и нажмите «Найти доноров».</p>
    </div>
  </div>
</template>
