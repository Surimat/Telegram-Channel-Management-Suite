<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type DiagnosticsReport, type MaintenanceAction } from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const report = ref<DiagnosticsReport | null>(null)
const actions = ref<MaintenanceAction[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busyAction = ref('')
const reportBusy = ref(false)

const reportFormat = ref<'zip' | 'json' | 'txt'>('zip')

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await api.diagnostics()
    actions.value = await api.diagnosticActions()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось получить состояние системы.'
  } finally {
    loading.value = false
  }
}

function friendlyError(e: unknown): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || 'Произошла ошибка.'
}

function statusClass(status: string): string {
  if (status === 'ok') return 'ok'
  if (status === 'error') return 'error'
  if (status === 'not_configured') return 'badge-muted'
  return 'warning'
}

const overallLabel = computed(() => report.value?.overall_label || 'Проверяем…')
const overallClass = computed(() => statusClass(report.value?.overall || 'unknown'))

const okCount = computed(
  () => report.value?.items.filter((i) => i.status === 'ok').length || 0,
)
const attentionCount = computed(
  () =>
    report.value?.items.filter(
      (i) => i.status === 'warning' || i.status === 'error',
    ).length || 0,
)

async function runAction(action: MaintenanceAction) {
  if (
    action.requires_confirmation &&
    !confirm(`${action.title}\n\n${action.description}\n\nПродолжить?`)
  ) {
    return
  }
  busyAction.value = action.key
  notice.value = ''
  error.value = ''
  try {
    const result = await api.runDiagnosticAction(action.key)
    notice.value = result.ok
      ? result.message
      : `${result.message}${result.detail ? ' ' + result.detail : ''}`
    if (!result.ok) error.value = result.message
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyAction.value = ''
  }
}

async function downloadReport() {
  reportBusy.value = true
  notice.value = ''
  error.value = ''
  try {
    const response = await fetch(api.diagnosticsReportUrl(reportFormat.value))
    if (!response.ok) {
      throw new Error('Не удалось создать отчёт диагностики.')
    }
    const blob = await response.blob()
    const disposition = response.headers.get('content-disposition') || ''
    const match = /filename="?([^";]+)"?/.exec(disposition)
    const filename = match ? match[1] : `tcms-diagnostics.${reportFormat.value}`
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    notice.value = 'Отчёт безопасно очищен от секретов.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось создать отчёт.'
  } finally {
    reportBusy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Диагностика <InfoHint topic="update" /></h2>
    <p class="page-subtitle">
      Здесь видно состояние каждого компонента простыми словами. Если что-то не работает,
      создайте отчёт диагностики и покажите его разработчику — искать логи вручную не нужно.
    </p>

    <div v-if="loading" class="card">Проверка состояния...</div>
    <div v-else-if="error && !report" class="card error-text">{{ error }}</div>

    <template v-else-if="report">
      <div class="card">
        <p>
          Общее состояние:
          <span class="badge" :class="overallClass">{{ overallLabel }}</span>
          <span class="muted"> · версия {{ report.version }} · {{ report.environment }}</span>
        </p>
        <p class="muted">
          Готово: {{ okCount }} · требуют внимания: {{ attentionCount }}
        </p>
        <p v-if="notice" class="notice-text">{{ notice }}</p>
        <p v-if="error" class="error-text">{{ error }}</p>
      </div>

      <div class="card" style="margin-top: 20px">
        <table>
          <thead>
            <tr>
              <th>Компонент</th>
              <th>Статус</th>
              <th>Что это значит</th>
              <th>Что делать</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in report.items" :key="item.key">
              <td><strong>{{ item.title }}</strong></td>
              <td>
                <span class="badge" :class="statusClass(item.status)">{{ item.status_label }}</span>
              </td>
              <td>{{ item.meaning }}</td>
              <td class="muted">{{ item.how_to_fix || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <button style="margin-top: 12px" :disabled="loading" @click="load">Обновить</button>
      </div>

      <div class="card" style="margin-top: 20px">
        <h3>Отчёт диагностики</h3>
        <p class="muted">
          Отчёт собирает версию, систему, состояние базы, модулей, ботов, сессий, каналов,
          очереди и последние ошибки. Токены, ключи, данные сессий, номера телефонов, пароли
          и содержимое базы в отчёт <strong>не попадают</strong>.
        </p>
        <div class="report-controls">
          <label>
            Формат:
            <select v-model="reportFormat">
              <option value="zip">ZIP (report.json + report.txt)</option>
              <option value="json">JSON</option>
              <option value="txt">TXT</option>
            </select>
          </label>
          <button class="primary" :disabled="reportBusy" @click="downloadReport">
            {{ reportBusy ? 'Создаём…' : 'Создать отчёт диагностики' }}
          </button>
        </div>
        <p class="muted">
          Отчёт безопасно очищен от секретов. Перед экспортом выполняется автоматическая
          проверка на утечки.
        </p>
      </div>

      <div class="card" style="margin-top: 20px">
        <h3>Безопасные действия</h3>
        <p class="muted">
          Эти действия не удаляют ваши данные. Для действий, требующих подтверждения, будет
          задан вопрос.
        </p>
        <div v-for="action in actions" :key="action.key" class="action-row">
          <div>
            <strong>{{ action.title }}</strong>
            <p class="muted">{{ action.description }}</p>
          </div>
          <button
            :disabled="busyAction === action.key || !action.available"
            @click="runAction(action)"
          >
            {{ busyAction === action.key ? 'Выполняем…' : 'Выполнить' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.report-controls {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
  margin: 12px 0;
}
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid var(--border, #e5e7eb);
}
.action-row:first-of-type {
  border-top: none;
}
.action-row p {
  margin: 4px 0 0;
}
.notice-text {
  color: var(--ok, #1a7f4b);
}
</style>
