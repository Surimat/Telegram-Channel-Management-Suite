<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type EventItem } from '@/api/client'

const events = ref<EventItem[]>([])
const loading = ref(true)
const error = ref('')
const levelFilter = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {}
    if (levelFilter.value) params.level = levelFilter.value
    const page = await api.events(params)
    events.value = page.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Ошибка загрузки журнала.'
  } finally {
    loading.value = false
  }
}

async function resolve(id: string) {
  try {
    await api.resolveEvent(id)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось отметить событие.'
  }
}

onMounted(load)

function badgeClass(level: string) {
  if (level === 'ERROR' || level === 'CRITICAL') return 'error'
  if (level === 'WARNING') return 'warning'
  return 'ok'
}
</script>

<template>
  <div>
    <h2 class="page-title">Логи и ошибки</h2>
    <p class="page-subtitle">
      Здесь собраны все важные события. Для каждой ошибки есть объяснение и подсказка, как исправить.
    </p>

    <div class="card">
      <label>
        Уровень:
        <select v-model="levelFilter" @change="load">
          <option value="">Все</option>
          <option value="INFO">Информация</option>
          <option value="WARNING">Предупреждение</option>
          <option value="ERROR">Ошибка</option>
          <option value="CRITICAL">Критично</option>
        </select>
      </label>
    </div>

    <div v-if="loading" class="card">Загрузка...</div>
    <div v-else-if="error" class="card error-text">{{ error }}</div>
    <div v-else-if="!events.length" class="card empty">Пока событий нет. Это хороший знак.</div>

    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Уровень</th>
            <th>Модуль</th>
            <th>Что произошло?</th>
            <th>Как исправить?</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ev in events" :key="ev.id">
            <td><span class="badge" :class="badgeClass(ev.level)">{{ ev.level }}</span></td>
            <td>{{ ev.module }}</td>
            <td>{{ ev.message }}</td>
            <td class="muted">{{ ev.how_to_fix || '—' }}</td>
            <td>
              <button v-if="!ev.resolved" @click="resolve(ev.id)">Отметить как решённое</button>
              <span v-else class="muted">решено</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
