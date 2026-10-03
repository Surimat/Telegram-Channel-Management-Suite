<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  api,
  type AudienceDashboard,
  type AudienceSource,
  type ScanPreview,
  type ScanResult,
  type UserSession,
} from '@/api/client'

const sources = ref<AudienceSource[]>([])
const dashboard = ref<AudienceDashboard | null>(null)
const accounts = ref<UserSession[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busyId = ref('')

// Add form
const showAdd = ref(false)
const addBusy = ref(false)
const form = ref({ reference: '', title: '', source_type: 'unknown', account_id: '' })

// Scan confirmation + preview
const previewFor = ref<AudienceSource | null>(null)
const preview = ref<ScanPreview | null>(null)
const previewBusy = ref(false)
const lastResult = ref<ScanResult | null>(null)

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
    const [list, dash, sess] = await Promise.all([
      api.audienceSources({ limit: '200' }),
      api.audienceDashboard(),
      api.sessions(),
    ])
    sources.value = list.items
    dashboard.value = dash
    accounts.value = sess
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
      reference: form.value.reference,
      title: form.value.title,
      source_type: form.value.source_type,
      account_id: form.value.account_id || null,
    })
    notice.value = 'Источник добавлен. Теперь проверьте его доступность кнопкой «Проверить».'
    form.value = { reference: '', title: '', source_type: 'unknown', account_id: '' }
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
    <h2 class="page-title">Источники аудитории</h2>
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
      <label class="field">
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
      <button class="primary" :disabled="addBusy || !form.reference" @click="submitAdd">
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
  </div>
</template>
