<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type InviteJob,
  type InvitePreview,
  type InviteTask,
  type UserSession,
} from '@/api/client'

const jobs = ref<InviteJob[]>([])
const sessions = ref<UserSession[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')

// Builder state.
const target = ref('')
const name = ref('')
const accountIds = ref<string[]>([])
const search = ref('')
const maxTotal = ref<number | ''>('')
const delayMin = ref<number>(20)
const delayMax = ref<number>(60)
const dryRun = ref(false)
const preview = ref<InvitePreview | null>(null)
const previewing = ref(false)
const creating = ref(false)

// Selected job detail.
const selected = ref<InviteJob | null>(null)
const tasks = ref<InviteTask[]>([])
const taskCounts = ref<Record<string, number>>({})

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  ready: 'Готово к запуску',
  running: 'Выполняется',
  paused: 'Пауза',
  completed: 'Завершено',
  stopped: 'Остановлено',
  failed: 'Ошибка',
}

const TASK_LABELS: Record<string, string> = {
  pending: 'Ожидает',
  running: 'В работе',
  invited: 'Приглашён',
  already_member: 'Уже состоял',
  skipped: 'Пропущен',
  privacy: 'Приватность',
  flood_wait: 'Ожидание',
  admin_required: 'Нужны права',
  failed: 'Ошибка',
}

function statusClass(status: string): string {
  if (status === 'completed') return 'status-ok'
  if (status === 'running' || status === 'ready') return 'status-ok'
  if (status === 'paused' || status === 'draft') return 'status-warning'
  if (status === 'failed' || status === 'stopped') return 'status-error'
  return 'status-unknown'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [list, sess] = await Promise.all([api.inviteJobs(), api.sessions()])
    jobs.value = list.items
    sessions.value = sess.filter((s) => s.enabled && s.status === 'online')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить приглашения.'
  } finally {
    loading.value = false
  }
}

async function doPreview() {
  previewing.value = true
  error.value = ''
  notice.value = ''
  try {
    const payload: Parameters<typeof api.invitePreview>[0] = { target: target.value }
    if (accountIds.value.length) payload.account_ids = accountIds.value
    const filters: Record<string, unknown> = {}
    if (search.value) filters.search = search.value
    if (Object.keys(filters).length) payload.filters = filters
    if (maxTotal.value !== '' && maxTotal.value > 0) payload.max_total = Number(maxTotal.value)
    preview.value = await api.invitePreview(payload)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось построить предпросмотр.'
  } finally {
    previewing.value = false
  }
}

async function createJob() {
  creating.value = true
  error.value = ''
  try {
    const payload: Parameters<typeof api.createInviteJob>[0] = {
      target: target.value,
      name: name.value,
      dry_run: dryRun.value,
      per_account_delay_min: delayMin.value,
      per_account_delay_max: delayMax.value,
    }
    if (accountIds.value.length) payload.account_ids = accountIds.value
    const filters: Record<string, unknown> = {}
    if (search.value) filters.search = search.value
    if (Object.keys(filters).length) payload.filters = filters
    if (maxTotal.value !== '' && maxTotal.value > 0) payload.max_total = Number(maxTotal.value)
    const job = await api.createInviteJob(payload)
    notice.value = 'Задание создано как черновик. Подтвердите сводку, чтобы запустить.'
    preview.value = null
    target.value = ''
    name.value = ''
    search.value = ''
    await load()
    await openJob(job.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось создать задание.'
  } finally {
    creating.value = false
  }
}

async function openJob(id: string) {
  selected.value = await api.getInviteJob(id)
  const page = await api.inviteTasks(id, { limit: '50' })
  tasks.value = page.items
  taskCounts.value = page.status_counts
}

async function confirmJob(id: string) {
  if (!window.confirm('Подтвердите запуск приглашений. Telegram может ограничить частоту.')) return
  await api.confirmInviteJob(id)
  notice.value = 'Задание запущено.'
  await load()
  await openJob(id)
}

async function action(fn: (id: string) => Promise<InviteJob>, id: string, label: string) {
  await fn(id)
  notice.value = label
  await load()
  await openJob(id)
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Приглашения</h2>
    <p class="page-subtitle">
      Приглашайте людей из аудитории в ваш канал. Перед запуском система показывает сводку:
      сколько человек, из каких источников и с каких аккаунтов. Ограничения Telegram (пауза
      FloodWait) соблюдаются — обходить их нельзя.
    </p>

    <div v-if="notice" class="card success-text">{{ notice }}</div>
    <div v-if="error" class="card error-text">{{ error }}</div>

    <div class="card">
      <h3>Новое приглашение</h3>
      <div class="grid">
        <label class="field">
          Целевой канал (username, ссылка или ID)
          <input v-model="target" placeholder="@my_channel" />
        </label>
        <label class="field">
          Название задания (необязательно)
          <input v-model="name" placeholder="Например: Приглашение из @source" />
        </label>
        <label class="field">
          Поиск по аудитории (необязательно)
          <input v-model="search" placeholder="Имя или username" />
        </label>
        <label class="field">
          Максимум приглашений (0 — без ограничения)
          <input v-model.number="maxTotal" type="number" min="0" />
        </label>
        <label class="field">
          Минимальная задержка, сек
          <input v-model.number="delayMin" type="number" min="1" />
        </label>
        <label class="field">
          Максимальная задержка, сек
          <input v-model.number="delayMax" type="number" min="1" />
        </label>
      </div>

      <label class="field">
        Аккаунты (не выбрано — любой доступный «онлайн»)
        <select v-model="accountIds" multiple size="3">
          <option v-for="s in sessions" :key="s.id" :value="s.id">
            {{ s.username || s.display_name || s.id }}
          </option>
        </select>
      </label>

      <label class="field-inline">
        <input v-model="dryRun" type="checkbox" />
        Пробный запуск (без реальных приглашений)
      </label>

      <div class="actions">
        <button :disabled="previewing || !target" @click="doPreview">
          {{ previewing ? 'Считаем…' : 'Предпросмотр' }}
        </button>
      </div>

      <div v-if="preview" class="inline-note">
        <p>{{ preview.explanation }}</p>
        <table>
          <thead>
            <tr>
              <th>Показатель</th>
              <th>Значение</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Источник</td><td>{{ preview.source_labels.join(', ') || 'вся аудитория' }}</td></tr>
            <tr><td>Целевой канал</td><td>{{ preview.target }}</td></tr>
            <tr><td>Пользователей под фильтр</td><td>{{ preview.total_candidates }}</td></tr>
            <tr><td>Аккаунтов</td><td>{{ preview.accounts_count }}</td></tr>
            <tr><td>Запланировано операций</td><td>{{ preview.planned_operations }}</td></tr>
          </tbody>
        </table>
        <p v-if="preview.sample.length" class="muted">
          Пример: {{ preview.sample.map((s) => s.username || s.display_name).join(', ') }}
        </p>
        <div class="actions">
          <button :disabled="creating" @click="createJob">
            {{ creating ? 'Создаём…' : 'Создать задание (черновик)' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="card">Загрузка...</div>
    <div v-else-if="!jobs.length" class="card empty">
      Заданий приглашений пока нет. Постройте предпросмотр и создайте задание.
    </div>

    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Название</th>
            <th>Целевой канал</th>
            <th>Статус</th>
            <th>Приглашено</th>
            <th>Прогресс</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td>{{ job.name }}</td>
            <td>{{ job.target }}</td>
            <td>
              <span class="badge" :class="statusClass(job.status)">
                {{ STATUS_LABELS[job.status] || job.status }}
              </span>
            </td>
            <td>{{ job.invited_count }}</td>
            <td>{{ job.processed_count }} / {{ job.total_tasks }}</td>
            <td class="actions">
              <button v-if="job.status === 'draft'" @click="confirmJob(job.id)">Подтвердить</button>
              <button v-else @click="openJob(job.id)">Открыть</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selected" class="card">
      <div class="row-between">
        <h3>{{ selected.name }}</h3>
        <span class="badge" :class="statusClass(selected.status)">
          {{ STATUS_LABELS[selected.status] || selected.status }}
        </span>
      </div>
      <p>{{ selected.explanation }}</p>
      <p v-if="selected.wait_until" class="status-warning">
        Ожидание до {{ selected.wait_until }} (ограничение Telegram).
      </p>

      <div class="grid">
        <div>Приглашено: <strong>{{ selected.invited_count }}</strong></div>
        <div>Уже состояли: <strong>{{ selected.already_count }}</strong></div>
        <div>Приватность: <strong>{{ selected.privacy_count }}</strong></div>
        <div>Ожидание: <strong>{{ selected.flood_count }}</strong></div>
        <div>Ошибок: <strong>{{ selected.error_count }}</strong></div>
      </div>

      <div class="actions">
        <button v-if="selected.status === 'running'" @click="action(api.pauseInviteJob, selected.id, 'Задание на паузе.')">
          Пауза
        </button>
        <button v-if="selected.status === 'paused'" @click="action(api.resumeInviteJob, selected.id, 'Задание продолжено.')">
          Продолжить
        </button>
        <button v-if="['running', 'paused'].includes(selected.status)" @click="action(api.stopInviteJob, selected.id, 'Задание остановлено.')">
          Остановить
        </button>
        <button @click="action(api.retryInviteJob, selected.id, 'Повтор неудачных запущен.')">
          Повторить неудачные
        </button>
      </div>

      <h4>Задачи</h4>
      <p class="muted">
        <span v-for="(count, status) in taskCounts" :key="status" class="badge badge-muted">
          {{ TASK_LABELS[status] || status }}: {{ count }}
        </span>
      </p>
      <table>
        <thead>
          <tr>
            <th>Telegram ID</th>
            <th>Статус</th>
            <th>Попытки</th>
            <th>Ошибка</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.id">
            <td>{{ task.telegram_user_id }}</td>
            <td>{{ TASK_LABELS[task.status] || task.status }}</td>
            <td>{{ task.attempts }}</td>
            <td class="muted">{{ task.error || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
