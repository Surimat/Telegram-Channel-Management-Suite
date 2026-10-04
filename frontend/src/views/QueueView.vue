<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type Job } from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const jobs = ref<Job[]>([])
const loading = ref(true)
const error = ref('')
const statusFilter = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {}
    if (statusFilter.value) params.status = statusFilter.value
    const page = await api.jobs(params)
    jobs.value = page.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Ошибка загрузки очереди.'
  } finally {
    loading.value = false
  }
}

async function retry(id: string) {
  await api.retryJob(id)
  await load()
}

async function cancel(id: string) {
  await api.cancelJob(id)
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Очередь заданий <InfoHint topic="queue" /></h2>
    <p class="page-subtitle">
      Здесь выполняются запланированные действия (реакции, приглашения, сканирование). Задания
      сохраняются и продолжаются даже после перезапуска программы.
    </p>

    <div class="card">
      <label>
        Статус:
        <select v-model="statusFilter" @change="load">
          <option value="">Все</option>
          <option value="pending">Ожидает</option>
          <option value="scheduled">Запланировано</option>
          <option value="running">Выполняется</option>
          <option value="done">Готово</option>
          <option value="failed">Ошибка</option>
          <option value="cancelled">Отменено</option>
        </select>
      </label>
    </div>

    <div v-if="loading" class="card">Загрузка...</div>
    <div v-else-if="error" class="card error-text">{{ error }}</div>
    <div v-else-if="!jobs.length" class="card empty">
      Очередь пуста. Задания появятся, когда вы запустите реакции или приглашения.
    </div>

    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Тип</th>
            <th>Статус</th>
            <th>Попытки</th>
            <th>Запланировано</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td>{{ job.kind }}</td>
            <td>{{ job.status }}</td>
            <td>{{ job.attempts }} / {{ job.max_attempts }}</td>
            <td class="muted">{{ job.scheduled_at || '—' }}</td>
            <td>
              <button @click="retry(job.id)">Повторить</button>
              <button @click="cancel(job.id)">Отменить</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
