<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type NotificationDashboard,
  type NotificationItem,
  type NotificationSettings,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const settings = ref<NotificationSettings | null>(null)
const dashboard = ref<NotificationDashboard | null>(null)
const items = ref<NotificationItem[]>([])
const total = ref(0)

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const filter = ref({ category: '', priority: '', status: '' })
const testCategory = ref('system')
const testPriority = ref('info')

const PRIORITY_CLASS: Record<string, string> = {
  info: 'status-unknown',
  warning: 'status-warning',
  error: 'status-error',
  critical: 'status-error',
}

function friendly(e: unknown, fallback: string): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, d] = await Promise.all([api.notificationSettings(), api.notificationDashboard()])
    settings.value = s
    dashboard.value = d
    await loadHistory()
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить центр уведомлений.')
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  const params: Record<string, string> = {}
  if (filter.value.category) params.category = filter.value.category
  if (filter.value.priority) params.priority = filter.value.priority
  if (filter.value.status) params.status = filter.value.status
  const page = await api.notifications(params)
  items.value = page.items
  total.value = page.total
}

async function run(fn: () => Promise<unknown>, message = '') {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await fn()
    if (message) notice.value = message
    await load()
  } catch (e) {
    error.value = friendly(e, 'Операция не выполнена.')
  } finally {
    busy.value = false
  }
}

const saveSettings = () =>
  settings.value &&
  run(
    () =>
      api.updateNotificationSettings({
        enabled: settings.value!.enabled,
        categories: Object.fromEntries(
          settings.value!.categories.map((c) => [c.key, c.enabled]),
        ),
        quiet_hours_enabled: settings.value!.quiet_hours_enabled,
        quiet_hours_start: settings.value!.quiet_hours_start,
        quiet_hours_end: settings.value!.quiet_hours_end,
        quiet_hours_tz: settings.value!.quiet_hours_tz,
        aggregation_enabled: settings.value!.aggregation_enabled,
      }),
    'Настройки уведомлений сохранены.',
  )

const sendTest = () =>
  run(
    () =>
      api.sendTestNotification({
        category: testCategory.value,
        priority: testPriority.value,
      }),
    'Тестовое уведомление отправлено.',
  )

const markRead = (id: string) =>
  run(() => api.markNotificationRead(id), 'Отмечено как прочитанное.')

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Центр уведомлений
      <InfoHint topic="notification_center" />
    </h2>
    <p class="page-subtitle">
      Единая история важных событий: что произошло, насколько срочно, куда отправлено
      и что делать. Доставка идёт в личку владельцу, в группу уведомлений или во
      всплывающее окно Windows.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card muted">{{ notice }}</div>
    <div v-if="loading" class="card">Загрузка…</div>

    <template v-else>
      <div v-if="dashboard" class="card">
        <h3>Состояние</h3>
        <p>
          Уведомления:
          <strong :class="dashboard.enabled ? 'status-ok' : 'status-unknown'">
            {{ dashboard.enabled ? 'включены' : 'выключены' }}
          </strong>
          · в очереди: {{ dashboard.pending }} · с ошибкой: {{ dashboard.failed }}
        </p>
        <p v-if="dashboard.in_quiet_hours" class="muted">
          Сейчас тихие часы — несрочные уведомления отложены.
        </p>
        <p class="muted">
          Отправлено: {{ dashboard.status_counts['sent'] || 0 }} ·
          отложено: {{ dashboard.status_counts['postponed'] || 0 }} ·
          пропущено: {{ dashboard.status_counts['skipped'] || 0 }}
        </p>
      </div>

      <div v-if="settings" class="card">
        <h3>Категории и тихие часы</h3>
        <label class="toggle-row">
          <input v-model="settings.enabled" type="checkbox" />
          <span><strong>Присылать уведомления</strong> — общий выключатель</span>
        </label>
        <div v-if="settings.enabled" class="two-cols">
          <label v-for="c in settings.categories" :key="c.key" class="toggle-row">
            <input v-model="c.enabled" type="checkbox" />
            <span>{{ c.label }}</span>
          </label>
        </div>
        <label class="toggle-row">
          <input v-model="settings.quiet_hours_enabled" type="checkbox" />
          <span><strong>Тихие часы</strong> — несрочные уведомления ждут утра</span>
        </label>
        <div v-if="settings.quiet_hours_enabled" class="grid">
          <label class="field">
            <span>Начало (час, 0–23)</span>
            <input v-model.number="settings.quiet_hours_start" type="number" min="0" max="23" />
          </label>
          <label class="field">
            <span>Конец (час, 0–23)</span>
            <input v-model.number="settings.quiet_hours_end" type="number" min="0" max="23" />
          </label>
          <label class="field">
            <span>Часовой пояс</span>
            <input v-model="settings.quiet_hours_tz" type="text" />
          </label>
        </div>
        <label class="toggle-row">
          <input v-model="settings.aggregation_enabled" type="checkbox" />
          <span><strong>Объединять похожие</strong> — не спамить одним и тем же</span>
        </label>
        <p>
          <button class="primary" :disabled="busy" @click="saveSettings">Сохранить</button>
        </p>
      </div>

      <div class="card">
        <h3>Проверка</h3>
        <p class="muted">Отправить тестовое уведомление в выбранную категорию.</p>
        <div class="grid">
          <label class="field">
            <span>Категория</span>
            <select v-model="testCategory">
              <option v-for="c in settings?.categories || []" :key="c.key" :value="c.key">
                {{ c.label }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>Срочность</span>
            <select v-model="testPriority">
              <option value="info">Информация</option>
              <option value="warning">Предупреждение</option>
              <option value="error">Ошибка</option>
            </select>
          </label>
        </div>
        <p>
          <button class="primary" :disabled="busy" @click="sendTest">Отправить тест</button>
        </p>
      </div>

      <div class="card">
        <h3>История ({{ total }})</h3>
        <div class="grid">
          <label class="field">
            <span>Категория</span>
            <select v-model="filter.category" @change="loadHistory">
              <option value="">Все</option>
              <option v-for="c in settings?.categories || []" :key="c.key" :value="c.key">
                {{ c.label }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>Статус</span>
            <select v-model="filter.status" @change="loadHistory">
              <option value="">Все</option>
              <option value="sent">Отправлено</option>
              <option value="pending">В очереди</option>
              <option value="postponed">Отложено</option>
              <option value="skipped">Пропущено</option>
              <option value="failed">Ошибка</option>
              <option value="aggregated">Объединено</option>
            </select>
          </label>
        </div>
        <p v-if="!items.length" class="muted">Уведомлений пока нет.</p>
        <ul v-else class="notif-list">
          <li v-for="item in items" :key="item.id" class="notif-row">
            <span :class="PRIORITY_CLASS[item.priority] || 'status-unknown'">
              {{ item.priority_label }}
            </span>
            <span class="muted">{{ item.category_label }}</span>
            <span>{{ item.message }}</span>
            <span class="muted">{{ item.status_label }}</span>
            <span v-if="item.how_to_fix" class="muted">→ {{ item.how_to_fix }}</span>
            <button v-if="!item.read" class="small" :disabled="busy" @click="markRead(item.id)">
              Прочитано
            </button>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.notif-list {
  list-style: none;
  padding: 0;
}
.notif-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  padding: 6px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.15);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
