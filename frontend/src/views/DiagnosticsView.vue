<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type ConsistencyFinding,
  type ConsistencyReport,
  type DiagnosticsReport,
  type MaintenanceAction,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const report = ref<DiagnosticsReport | null>(null)
const actions = ref<MaintenanceAction[]>([])
const consistency = ref<ConsistencyReport | null>(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busyAction = ref('')
const reportBusy = ref(false)
const consistencyBusy = ref(false)
const showConfidence = ref(false)

const reportFormat = ref<'zip' | 'json' | 'txt'>('zip')

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await api.diagnostics()
    actions.value = await api.diagnosticActions()
    await loadConsistency()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось получить состояние системы.'
  } finally {
    loading.value = false
  }
}

async function loadConsistency() {
  consistencyBusy.value = true
  try {
    consistency.value = await api.consistency()
  } catch {
    consistency.value = null
  } finally {
    consistencyBusy.value = false
  }
}

const consistencyOverallLabel = computed(() => {
  const overall = consistency.value?.overall
  if (overall === 'pass') return 'Всё согласовано'
  if (overall === 'fail') return 'Есть ошибки'
  if (overall === 'warning') return 'Есть предупреждения'
  return 'Не проверено'
})

const consistencyOverallClass = computed(() => {
  const overall = consistency.value?.overall
  if (overall === 'pass') return 'ok'
  if (overall === 'fail') return 'error'
  return 'warning'
})

const consistencyCounts = computed(() => {
  const counts = consistency.value?.counts ?? {}
  return {
    errors: counts.error ?? 0,
    warnings: counts.warning ?? 0,
    info: counts.info ?? 0,
  }
})

// The panel shows errors and warnings by default; info (low-confidence noise)
// is hidden behind a toggle so the page never looks alarming for no reason.
const visibleFindings = computed<ConsistencyFinding[]>(() =>
  (consistency.value?.findings ?? []).filter(
    (f) => showConfidence.value || f.severity !== 'info',
  ),
)

function confidenceLabel(confidence: string): string {
  if (confidence === 'high') return 'уверенность: высокая'
  if (confidence === 'medium') return 'уверенность: средняя'
  return 'уверенность: низкая'
}

function severityLabel(severity: string): string {
  if (severity === 'error') return 'Ошибка'
  if (severity === 'warning') return 'Предупреждение'
  return 'К сведению'
}

function areaStatusClass(status: string): string {
  if (status === 'pass') return 'ok'
  if (status === 'fail') return 'error'
  if (status === 'not_tested') return 'badge-muted'
  return 'warning'
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
        <h3>Проверка целостности</h3>
        <p class="muted">
          Проверка ищет расхождения между модулями: база и миграции, маршруты API и экраны,
          задачи и обработчики, переводы и подсказки. Это не поиск вирусов, а контроль
          согласованности самой программы.
        </p>
        <div v-if="consistencyBusy && !consistency" class="muted">Проверяем…</div>
        <template v-else-if="consistency">
          <p>
            Итог:
            <span class="badge" :class="consistencyOverallClass">
              {{ consistencyOverallLabel }}
            </span>
            <span class="muted">
              · ошибок: {{ consistencyCounts.errors }} · предупреждений:
              {{ consistencyCounts.warnings }}
            </span>
          </p>
          <div class="consistency-areas">
            <span
              v-for="area in consistency.areas"
              :key="area.key"
              class="badge"
              :class="areaStatusClass(area.status)"
            >
              {{ area.label }}
            </span>
          </div>

          <p v-if="visibleFindings.length === 0" class="notice-text">
            Замечаний нет — всё согласовано.
          </p>
          <div v-else class="consistency-list">
            <div
              v-for="finding in visibleFindings"
              :key="finding.id"
              class="consistency-item"
            >
              <p>
                <span class="badge" :class="statusClass(finding.severity === 'error' ? 'error' : 'warning')">
                  {{ severityLabel(finding.severity) }}
                </span>
                <strong>{{ finding.title }}</strong>
                <span class="muted"> · {{ confidenceLabel(finding.confidence) }}</span>
              </p>
              <p class="muted">{{ finding.detail }}</p>
              <p v-if="finding.why" class="muted">Почему важно: {{ finding.why }}</p>
              <p v-if="finding.how_to_fix" class="muted">Что делать: {{ finding.how_to_fix }}</p>
            </div>
          </div>

          <div class="report-controls" style="margin-top: 12px">
            <label class="muted">
              <input v-model="showConfidence" type="checkbox" />
              Показывать замечания «к сведению» (низкая уверенность)
            </label>
            <button :disabled="consistencyBusy" @click="loadConsistency">
              {{ consistencyBusy ? 'Проверяем…' : 'Проверить снова' }}
            </button>
          </div>
        </template>
        <p v-else class="muted">
          Проверка недоступна. Это не влияет на работу программы.
        </p>
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
