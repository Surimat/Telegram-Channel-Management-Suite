<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type AiClassifyResult,
  type AiHistory,
  type AiModel,
  type AiModelCheck,
  type AiOverview,
  type AiSettingHelp,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

type Tab = 'overview' | 'model' | 'settings' | 'testing' | 'diagnostics'
const tab = ref<Tab>('overview')

const overview = ref<AiOverview | null>(null)
const settings = ref<AiSettingHelp[]>([])
const models = ref<AiModel[]>([])
const history = ref<AiHistory>({ items: [], total: 0 })
const loading = ref(true)
const error = ref('')
const notice = ref('')

const checkResult = ref<AiModelCheck | null>(null)
const checking = ref(false)

// Settings draft holds every edit until "Сохранить".
const draft = ref<Record<string, unknown>>({})
const saving = ref(false)

const testText = ref('Спасибо за донат, друзья!')
const testMode = ref<'auto' | 'rules' | 'ai'>('auto')
const testResult = ref<AiClassifyResult | null>(null)
const testing = ref(false)

const MODE_LABELS: Record<string, string> = {
  auto: 'Автоматически (правила → лёгкий определитель → мини-ИИ)',
  rules: 'Только обычные правила',
  encoder: 'Лёгкий определитель (без модели)',
  ai: 'Только мини-ИИ',
}

const SOURCE_LABELS: Record<string, string> = {
  rules: 'Обычные правила',
  llm: 'Мини-ИИ',
  manual: 'Вручную',
  fallback: 'Запасной вариант',
  default: 'По умолчанию',
}

const statusDot = computed(() => {
  const s = overview.value?.status
  if (!s) return 'status-unknown'
  if (!s.enabled) return 'status-unknown'
  return s.effective ? 'status-ok' : 'status-warning'
})

const statusLabel = computed(() => {
  const s = overview.value?.status
  if (!s) return 'Проверяем'
  if (!s.enabled) return 'Выключен (это нормально)'
  return s.effective ? 'Готов к работе' : 'Нужно настроить'
})

function pct(value: number) {
  return `${Math.round(value * 100)}%`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [o, s, m, h] = await Promise.all([
      api.aiOverview(),
      api.aiSettings(),
      api.aiModels(),
      api.aiHistory({ limit: '20' }),
    ])
    overview.value = o
    settings.value = s.items
    models.value = m
    history.value = h
    const d: Record<string, unknown> = {}
    for (const item of s.items) d[item.key] = coerce(item)
    draft.value = d
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить данные ИИ.'
  } finally {
    loading.value = false
  }
}

function coerce(item: AiSettingHelp): unknown {
  if (item.value_type === 'bool') return item.value === 'true'
  if (item.value_type === 'int') return Number(item.value || 0)
  if (item.value_type === 'float') return Number(item.value || 0)
  return item.value
}

function fieldValue(key: string): string {
  const v = draft.value[key]
  return v === undefined || v === null ? '' : String(v)
}

function setFieldValue(key: string, value: unknown) {
  draft.value = { ...draft.value, [key]: value }
}

async function saveSettings() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const resp = await api.aiUpdateSettings(draft.value)
    settings.value = resp.items
    const d: Record<string, unknown> = {}
    for (const item of resp.items) d[item.key] = coerce(item)
    draft.value = d
    notice.value = 'Настройки ИИ сохранены.'
    await refreshStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить настройки ИИ.'
  } finally {
    saving.value = false
  }
}

async function refreshStatus() {
  try {
    const o = await api.aiOverview()
    overview.value = o
  } catch {
    /* status refresh is best-effort */
  }
}

async function checkModel() {
  checking.value = true
  error.value = ''
  notice.value = ''
  checkResult.value = null
  try {
    checkResult.value = await api.aiCheckModel()
    await refreshStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось проверить модель.'
  } finally {
    checking.value = false
  }
}

async function loadModel() {
  checking.value = true
  error.value = ''
  try {
    checkResult.value = await api.aiLoadModel()
    await refreshStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить модель.'
  } finally {
    checking.value = false
  }
}

async function unloadModel() {
  try {
    await api.aiUnloadModel()
    notice.value = 'Модель выгружена из памяти.'
    await refreshStatus()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось выгрузить модель.'
  }
}

function useModel(path: string) {
  setFieldValue('ai_model_path', path)
  notice.value = `Модель «${path}» выбрана. Не забудьте сохранить настройки.`
}

async function runTest() {
  testing.value = true
  error.value = ''
  testResult.value = null
  try {
    testResult.value = await api.aiClassify({ text: testText.value, mode: testMode.value })
    await refreshStatus()
    const h = await api.aiHistory({ limit: '20' })
    history.value = h
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось выполнить проверку.'
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Мини-ИИ <InfoHint topic="tiny_ai" /></h2>
    <p class="page-subtitle">
      Локальный классификатор помогает определить категорию поста, когда обычных правил
      недостаточно. Работает полностью на вашем компьютере. Его можно выключить — система
      продолжит работать на правилах.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div class="toolbar">
      <button :class="{ primary: tab === 'overview' }" @click="tab = 'overview'">Обзор</button>
      <button :class="{ primary: tab === 'model' }" @click="tab = 'model'">Модель</button>
      <button :class="{ primary: tab === 'settings' }" @click="tab = 'settings'">Настройки</button>
      <button :class="{ primary: tab === 'testing' }" @click="tab = 'testing'">Проверка</button>
      <button :class="{ primary: tab === 'diagnostics' }" @click="tab = 'diagnostics'">
        Диагностика
      </button>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>

    <!-- Overview -->
    <template v-else-if="tab === 'overview'">
      <div v-if="overview" class="card">
        <h3>
          <span class="status-dot" :class="statusDot"></span>Состояние: {{ statusLabel }}
        </h3>
        <p>{{ overview.status.reason }}</p>
        <p v-if="overview.status.how_to_fix" class="muted">
          Что делать: {{ overview.status.how_to_fix }}
        </p>
        <p class="muted">
          Движок: <strong>{{ overview.status.backend }}</strong> ·
          модель: <strong>{{ overview.status.model_path || 'не выбрана' }}</strong>
          <span v-if="overview.status.model_exists">
            ({{ overview.status.model_size_human }})</span>
        </p>
      </div>

      <div v-if="overview" class="grid">
        <div class="card">
          <strong>Всего классификаций</strong>
          <p>{{ overview.metrics.total_classifications }}</p>
          <p class="muted">Пост обработан системой определения категории.</p>
        </div>
        <div class="card">
          <strong>Обычными правилами</strong>
          <p>{{ overview.metrics.rules_count }}</p>
          <p class="muted">ИИ не потребовался — это самый быстрый путь.</p>
        </div>
        <div class="card">
          <strong>С помощью мини-ИИ</strong>
          <p>{{ overview.metrics.ai_count }}</p>
          <p class="muted">Правила были неуверены, и ИИ помог с категорией.</p>
        </div>
        <div class="card">
          <strong>Запасной вариант</strong>
          <p>{{ overview.metrics.fallback_count }}</p>
          <p class="muted">Ни правила, ни ИИ не были уверены.</p>
        </div>
        <div class="card">
          <strong>Ошибки ИИ</strong>
          <p :class="{ 'error-text': overview.metrics.ai_error_count > 0 }">
            {{ overview.metrics.ai_error_count }}
          </p>
          <p class="muted">При ошибке система автоматически использует правила.</p>
        </div>
        <div class="card">
          <strong>Среднее время анализа</strong>
          <p>{{ overview.metrics.average_latency_ms }} мс</p>
          <p class="muted">Сколько в среднем длится один вызов мини-ИИ.</p>
        </div>
      </div>

      <div v-if="overview" class="card">
        <h3>Сегодня</h3>
        <p>
          Правилами: {{ overview.today.rules_count }} · ИИ: {{ overview.today.ai_count }} ·
          запасной вариант: {{ overview.today.fallback_count }} · ошибок:
          {{ overview.today.ai_error_count }}
        </p>
      </div>
    </template>

    <!-- Model -->
    <template v-else-if="tab === 'model'">
      <div v-if="overview" class="card">
        <h3>Текущая модель</h3>
        <p>
          Путь: <strong>{{ overview.status.model_path || 'не выбрана' }}</strong>
        </p>
        <p>
          Файл найден:
          <span class="badge" :class="overview.status.model_exists ? 'ok' : 'warning'">
            {{ overview.status.model_exists ? 'да' : 'нет' }}
          </span>
          · загружена в память:
          <span class="badge" :class="overview.status.model_loaded ? 'ok' : 'badge-muted'">
            {{ overview.status.model_loaded ? 'да' : 'нет' }}
          </span>
        </p>
        <div class="actions">
          <button class="primary" :disabled="checking" @click="checkModel">
            {{ checking ? 'Проверяем…' : 'Проверить модель' }}
          </button>
          <button :disabled="checking" @click="loadModel">Загрузить модель</button>
          <button :disabled="checking" @click="unloadModel">Выгрузить из памяти</button>
        </div>
        <div v-if="checkResult" class="inline-note">
          <p :class="checkResult.ok ? 'ok-text' : 'error-text'">{{ checkResult.message }}</p>
          <p v-if="checkResult.how_to_fix" class="muted">{{ checkResult.how_to_fix }}</p>
          <p v-if="checkResult.ok" class="muted">
            Размер: {{ Math.round(checkResult.size_bytes / 1024 / 1024 * 10) / 10 }} МБ ·
            загрузка заняла {{ checkResult.load_ms }} мс
          </p>
        </div>
      </div>

      <div class="card">
        <h3>Доступные файлы .gguf</h3>
        <p class="muted">
          Положите файл модели в папку «models» рядом с приложением. Модель не скачивается
          автоматически — вы выбираете её сами.
        </p>
        <div v-if="!models.length" class="empty">Файлы моделей не найдены.</div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>Файл</th>
              <th>Размер</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in models" :key="m.path">
              <td>{{ m.name }}</td>
              <td>{{ m.size_human }}</td>
              <td><button @click="useModel(m.path)">Выбрать</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Settings -->
    <template v-else-if="tab === 'settings'">
      <div class="card">
        <p class="muted">
          Для каждой настройки указано, зачем она нужна, что произойдёт при большом значении
          и безопасное значение. Изменения применяются после нажатия «Сохранить».
        </p>
      </div>
      <div v-for="item in settings" :key="item.key" class="card">
        <h3>{{ item.title }}</h3>
        <p>{{ item.what_it_does }}</p>
        <p class="muted">Зачем: {{ item.why }}</p>
        <p class="muted">При большом значении: {{ item.large_value_effect }}</p>
        <p class="muted">Безопасное значение: {{ item.safe_default }}</p>
        <label class="field">
          <span>Значение</span>
          <input
            v-if="item.value_type === 'bool'"
            type="checkbox"
            :checked="Boolean(draft[item.key])"
            @change="setFieldValue(item.key, ($event.target as HTMLInputElement).checked)"
          />
          <input
            v-else-if="item.value_type === 'int' || item.value_type === 'float'"
            type="number"
            :step="item.value_type === 'float' ? '0.01' : '1'"
            :value="fieldValue(item.key)"
            @input="setFieldValue(item.key, Number(($event.target as HTMLInputElement).value))"
          />
          <input
            v-else
            type="text"
            :value="fieldValue(item.key)"
            @input="setFieldValue(item.key, ($event.target as HTMLInputElement).value)"
          />
        </label>
        <p class="muted">По умолчанию: {{ item.default_value || '—' }}</p>
      </div>
      <div class="card">
        <button class="primary" :disabled="saving" @click="saveSettings">
          {{ saving ? 'Сохраняем…' : 'Сохранить настройки' }}
        </button>
      </div>
    </template>

    <!-- Testing -->
    <template v-else-if="tab === 'testing'">
      <div class="card">
        <h3>Проверка классификации</h3>
        <p class="muted">
          Проверка ничего не отправляет в Telegram. Она показывает, как система определит
          категорию для такого текста.
        </p>
        <label class="field">
          <span>Текст поста</span>
          <input v-model="testText" />
        </label>
        <label class="field">
          <span>Способ определения</span>
          <select v-model="testMode">
            <option value="auto">{{ MODE_LABELS.auto }}</option>
            <option value="rules">{{ MODE_LABELS.rules }}</option>
            <option value="encoder">{{ MODE_LABELS.encoder }}</option>
            <option value="ai">{{ MODE_LABELS.ai }}</option>
          </select>
        </label>
        <button class="primary" :disabled="testing" @click="runTest">
          {{ testing ? 'Считаем…' : 'Проверить' }}
        </button>
      </div>

      <div v-if="testResult" class="card">
        <h3>Результат</h3>
        <p>
          <strong>Категория:</strong> {{ testResult.category_title }}
          ({{ testResult.category }})
        </p>
        <p class="muted">
          уверенность: {{ pct(testResult.confidence) }} ·
          источник: {{ SOURCE_LABELS[testResult.source] ?? testResult.source }} ·
          модель: {{ testResult.model }} · {{ testResult.processing_time_ms }} мс
        </p>
        <p class="muted">
          ИИ вызывался: {{ testResult.ai_attempted ? 'да' : 'нет' }} ·
          ИИ использован: {{ testResult.ai_used ? 'да' : 'нет' }} ·
          запасной вариант: {{ testResult.fallback_used ? 'да' : 'нет' }}
        </p>
        <p v-if="testResult.ai_error" class="muted">Примечание ИИ: {{ testResult.ai_error }}</p>
      </div>
    </template>

    <!-- Diagnostics -->
    <template v-else>
      <div class="card">
        <h3>Последние записи</h3>
        <p class="muted">
          Здесь показаны последние результаты определения категории. Оригинальный текст постов
          не сохраняется.
        </p>
        <div v-if="!history.items.length" class="empty">Записей пока нет.</div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>Когда</th>
              <th>Источник</th>
              <th>Категория</th>
              <th>Уверенность</th>
              <th>Режим</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in history.items" :key="r.id">
              <td>{{ new Date(r.created_at).toLocaleString('ru-RU') }}</td>
              <td>{{ SOURCE_LABELS[r.source] ?? r.source }}</td>
              <td>{{ r.category }}</td>
              <td>{{ pct(r.confidence) }}</td>
              <td>{{ r.mode }}</td>
              <td>
                <span class="badge" :class="r.ok ? 'ok' : 'error'">
                  {{ r.ok ? 'успешно' : 'ошибка' }}
                </span>
                <span v-if="r.detail" class="muted"> · {{ r.detail }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
