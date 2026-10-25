<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type SetupStep, type SetupWizardState } from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

// One guided flow: from a fresh install to a working channel. Each step is the
// stored result of a *real* server check — opening this page never marks a step
// done. The only action that touches Telegram is the explicitly-confirmed test
// publication.
const state = ref<SetupWizardState | null>(null)
const loading = ref(true)
const error = ref('')
const busyKey = ref('')
const accountId = ref('')
const publishing = ref(false)
const publishResult = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    state.value = await api.setupWizard()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить мастер настройки.'
  } finally {
    loading.value = false
  }
}

async function run(key: string) {
  busyKey.value = key
  error.value = ''
  try {
    state.value = await api.runSetupStep(key, accountId.value.trim())
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Проверка шага не удалась.'
  } finally {
    busyKey.value = ''
  }
}

async function runAll() {
  if (!state.value) return
  for (const step of state.value.steps) {
    await run(step.key)
  }
}

async function testPublication() {
  if (!state.value?.test_publication_available) return
  publishing.value = true
  error.value = ''
  publishResult.value = ''
  try {
    const result = await api.setupTestPublication(true)
    publishResult.value = result.ok
      ? `Опубликовано в «${result.channel_label}».`
      : `${result.message} ${result.how_to_fix}`
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Тестовая публикация не удалась.'
  } finally {
    publishing.value = false
  }
}

function statusClass(step: SetupStep): string {
  if (step.status === 'verified') return 'status-ok'
  if (step.status === 'failed') return 'status-error'
  if (step.status === 'pending') return 'status-warning'
  return 'status-unknown'
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Мастер настройки
      <InfoHint
        title="Мастер настройки"
        what="Пошаговый путь от первого запуска до рабочего канала: программа, канал, бот и права, модули, контент-процесс, очередь и итоговая проверка."
        why="Чтобы не собирать рабочий канал вслепую по разным разделам."
        effect="Каждый шаг проверяется на сервере по реальным данным. Шаг «Проверено» появляется только после настоящей проверки."
        when-off="Если ничего не настраивать, канал просто не будет считаться готовым."
      />
    </h2>
    <p class="page-subtitle">
      Пройдите шаги по порядку. Открытие страницы ничего не отмечает выполненным — шаг
      становится «Проверено» только после реальной проверки. Мастер ничего не создаёт в
      Telegram сам по себе.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="loading" class="card">Загружаем мастер…</div>

    <template v-else-if="state">
      <div class="card">
        <p>
          <strong>Прогресс:</strong> {{ state.completed_steps }} из {{ state.total_steps }}
          ({{ state.progress_percent }}%)
        </p>
        <p v-if="state.ready" class="status-ok">Канал готов к работе.</p>
        <p v-else class="muted">
          Текущий шаг: {{ state.steps.find((s) => s.key === state!.current_step)?.title }}
        </p>
        <p v-for="note in state.notes" :key="note" class="muted">{{ note }}</p>
        <div class="toolbar">
          <button @click="load()">Обновить</button>
          <button :disabled="busyKey !== ''" @click="runAll()">Проверить все шаги</button>
        </div>
        <label class="muted">
          Аккаунт для проверки канала (необязательно):
          <input v-model="accountId" placeholder="ID аккаунта" />
        </label>
      </div>

      <div class="setup-steps">
        <div v-for="(step, index) in state.steps" :key="step.key" class="card setup-step">
          <div class="setup-head">
            <span class="status-dot" :class="statusClass(step)"></span>
            <strong>{{ index + 1 }}. {{ step.title }}</strong>
            <span class="badge">{{ step.status_title }}</span>
          </div>
          <p class="muted">{{ step.description }}</p>
          <p v-if="step.message">{{ step.message }}</p>
          <p v-if="step.how_to_fix && !step.verified" class="muted">
            Что сделать: {{ step.how_to_fix }}
          </p>
          <p v-if="step.verified_at" class="muted">
            Проверено: {{ new Date(step.verified_at).toLocaleString() }}
          </p>
          <div class="toolbar">
            <button :disabled="busyKey === step.key" @click="run(step.key)">
              {{ busyKey === step.key ? 'Проверяем…' : 'Проверить шаг' }}
            </button>
            <RouterLink v-if="step.route" class="nav-item" :to="step.route">
              Перейти
            </RouterLink>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Тестовая публикация</h3>
        <p class="muted">{{ state.test_publication_hint }}</p>
        <p class="muted">
          Это единственное действие мастера, которое обращается к Telegram. Оно выполняется
          только по вашему явному нажатию и берёт уже подготовленный материал.
        </p>
        <div class="toolbar">
          <button
            :disabled="!state.test_publication_available || publishing"
            @click="testPublication()"
          >
            {{ publishing ? 'Публикуем…' : 'Опубликовать тестовое сообщение' }}
          </button>
        </div>
        <p v-if="publishResult">{{ publishResult }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.setup-steps {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0.75rem 0;
}
.setup-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
