<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import {
  api,
  ApiError,
  type ManagerStatus,
  type UpdateStatus,
  type WizardPreset,
  type WizardState,
} from '@/api/client'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const { status, loading } = storeToRefs(store)

const manager = ref<ManagerStatus | null>(null)
const wizard = ref<WizardState | null>(null)
const presets = ref<WizardPreset[]>([])
const update = ref<UpdateStatus | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')

onMounted(async () => {
  store.loadStatus()
  try {
    manager.value = await api.managerStatus()
  } catch {
    manager.value = null
  }
  try {
    const [w, p, u] = await Promise.all([
      api.wizardState(),
      api.wizardPresets(),
      api.updateStatus(),
    ])
    wizard.value = w
    presets.value = p
    update.value = u
  } catch {
    wizard.value = null
  }
})

function statusLabel(s: string) {
  return s === 'ok' ? 'Готово' : s === 'warning' ? 'Нужно настроить' : s === 'error' ? 'Проблема' : 'Проверяем'
}

function friendly(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.hint ? `${e.message} ${e.hint}` : e.message
  return e instanceof Error ? e.message : fallback
}

function stepClass(step: string): string {
  if (step === 'done') return 'ok'
  if (step === 'optional') return 'muted'
  if (step === 'error') return 'error'
  return 'warning'
}

const progressPercent = computed(() => {
  if (!wizard.value || wizard.value.total_steps === 0) return 0
  return Math.round((wizard.value.completed_steps / wizard.value.total_steps) * 100)
})

async function choosePreset(id: string) {
  busy.value = true
  error.value = ''
  try {
    wizard.value = await api.setWizardPreset(id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось выбрать набор настроек.')
  } finally {
    busy.value = false
  }
}

async function finishWizard() {
  busy.value = true
  try {
    wizard.value = await api.finishWizard()
    notice.value = 'Настройка отмечена как завершённая.'
  } catch (e) {
    error.value = friendly(e, 'Не удалось завершить настройку.')
  } finally {
    busy.value = false
  }
}

async function dismissWizard() {
  busy.value = true
  try {
    wizard.value = await api.dismissWizard()
  } catch (e) {
    error.value = friendly(e, 'Не удалось скрыть мастер настройки.')
  } finally {
    busy.value = false
  }
}

async function toggleUpdate() {
  if (!update.value) return
  busy.value = true
  error.value = ''
  try {
    update.value = await api.setUpdateEnabled(!update.value.enabled)
  } catch (e) {
    error.value = friendly(e, 'Не удалось изменить режим обновлений.')
  } finally {
    busy.value = false
  }
}

async function checkUpdate() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    update.value = await api.checkUpdate()
    notice.value = update.value.message || 'Проверка обновлений завершена.'
  } catch (e) {
    error.value = friendly(e, 'Не удалось проверить обновления.')
  } finally {
    busy.value = false
  }
}

async function downloadUpdate() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    update.value = await api.downloadUpdate()
    notice.value = update.value.message || 'Обновление скачано.'
  } catch (e) {
    error.value = friendly(e, 'Не удалось скачать обновление.')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <h2 class="page-title">Система</h2>
    <p class="page-subtitle">
      Мастер настройки проверяет каждый компонент и объясняет, что делать, простыми словами.
    </p>

    <div v-if="loading" class="card">Проверка...</div>
    <div v-else-if="status" class="card">
      <p>
        Общее состояние:
        <span class="badge" :class="status.overall">{{ statusLabel(status.overall) }}</span>
      </p>
      <table>
        <thead>
          <tr>
            <th>Пункт</th>
            <th>Статус</th>
            <th>Что это значит</th>
            <th>Что нужно сделать</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="check in status.checks" :key="check.key">
            <td><strong>{{ check.title }}</strong></td>
            <td><span class="badge" :class="check.status">{{ statusLabel(check.status) }}</span></td>
            <td>{{ check.meaning }}</td>
            <td class="muted">{{ check.how_to_fix || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="wizard" class="card" style="margin-top: 20px">
      <div class="row space-between">
        <h3>Мастер первой настройки</h3>
        <button v-if="!wizard.dismissed" @click="dismissWizard">Скрыть</button>
      </div>
      <p class="muted">{{ wizard.preset_description }}</p>
      <div class="progress">
        <div class="progress-bar" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <p class="muted">
        Готово шагов: {{ wizard.completed_steps }} из {{ wizard.total_steps }}
        <span v-if="!wizard.has_session"> · без аккаунта Telegram доступен режим «только бот»</span>
      </p>

      <div v-if="wizard.session_optional_note" class="inline-note">
        <strong>Аккаунт Telegram необязателен</strong>
        <p class="muted">{{ wizard.session_optional_note }}</p>
      </div>
      <div v-if="wizard.session_risk_note" class="inline-note risk">
        <strong>Риск ограничений</strong>
        <p class="muted">{{ wizard.session_risk_note }}</p>
      </div>

      <div class="preset-row">
        <button
          v-for="p in presets"
          :key="p.id"
          :class="{ primary: wizard.preset === p.id }"
          :disabled="busy"
          @click="choosePreset(p.id)"
        >
          {{ p.title }}
        </button>
      </div>

      <div v-for="step in wizard.steps" :key="step.key" class="step-row">
        <span class="badge" :class="stepClass(step.status)">{{ step.status_title }}</span>
        <div>
          <strong>{{ step.title }}</strong>
          <p class="muted">{{ step.description }}</p>
          <p v-if="step.how_to_fix" class="muted">{{ step.how_to_fix }}</p>
        </div>
        <RouterLink v-if="step.route" :to="step.route">
          <button>Перейти</button>
        </RouterLink>
      </div>

      <button class="primary" :disabled="busy || wizard.completed" @click="finishWizard">
        {{ wizard.completed ? 'Настройка завершена' : 'Отметить настройку завершённой' }}
      </button>
    </div>

    <div v-if="manager" class="card" style="margin-top: 20px">
      <h3>Управляющий бот</h3>
      <p>
        <span
          class="badge"
          :class="manager.connected ? 'ok' : 'warning'"
        >{{ manager.status_label }}</span>
      </p>
      <ul class="muted">
        <li>Бот: {{ manager.username ? '@' + manager.username : 'не указан' }}</li>
        <li>Владельцев (админов): {{ manager.admin_count }}</li>
        <li>Уведомления: {{ manager.notifications_enabled ? 'включены' : 'выключены' }}</li>
        <li v-if="manager.pending_notifications">
          В ожидании: {{ manager.pending_notifications }}
        </li>
      </ul>
      <p v-if="!manager.connected && manager.how_to_fix" class="muted">
        Как исправить: {{ manager.how_to_fix }}
      </p>
    </div>

    <div v-if="update" class="card" style="margin-top: 20px">
      <h3>Обновления</h3>
      <p v-if="error" class="error-text">{{ error }}</p>
      <p v-if="notice" class="notice-text">{{ notice }}</p>
      <p>
        Текущая версия: <strong>{{ update.current_version }}</strong>
        <span v-if="update.latest_version" class="muted">
          · доступна: {{ update.latest_version }}
        </span>
      </p>
      <p class="muted">{{ update.message }}</p>
      <label class="checkbox">
        <input type="checkbox" :checked="update.enabled" :disabled="busy" @change="toggleUpdate" />
        Разрешить проверку обновлений
      </label>
      <p class="muted">
        Обновления никогда не устанавливаются автоматически без вашего действия. Приложение
        только проверяет и скачивает проверенный файл.
      </p>
      <div class="row">
        <button :disabled="busy" @click="checkUpdate">Проверить обновления</button>
        <button
          v-if="update.update_available"
          class="primary"
          :disabled="busy"
          @click="downloadUpdate"
        >
          Скачать обновление
        </button>
        <a v-if="update.release_url" :href="update.release_url" target="_blank" rel="noopener">
          <button>Открыть страницу релиза</button>
        </a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.space-between {
  justify-content: space-between;
}
.checkbox {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.5rem;
}
.progress {
  height: 8px;
  border-radius: 999px;
  background: rgba(120, 120, 120, 0.2);
  overflow: hidden;
  margin: 0.5rem 0;
}
.progress-bar {
  height: 100%;
  background: #2ea043;
}
.preset-row {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin: 0.5rem 0;
}
.step-row {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.6rem 0;
  border-top: 1px solid var(--border, #e5e7eb);
}
.step-row p {
  margin: 0.2rem 0 0;
}
.badge {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  white-space: nowrap;
}
.badge.ok {
  background: rgba(46, 160, 67, 0.15);
}
.badge.warning {
  background: rgba(210, 153, 34, 0.2);
}
.badge.error {
  background: rgba(180, 35, 24, 0.15);
}
.badge.muted {
  background: rgba(120, 120, 120, 0.15);
}
.notice-text {
  color: #17663a;
}
</style>
