<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const { status, loading } = storeToRefs(store)

onMounted(() => {
  store.loadStatus()
})

function statusLabel(s: string) {
  return s === 'ok' ? 'Готово' : s === 'warning' ? 'Нужно настроить' : s === 'error' ? 'Проблема' : 'Проверяем'
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
  </div>
</template>
