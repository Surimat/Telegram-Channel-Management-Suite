<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { api, type ManagerStatus } from '@/api/client'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const { status, loading } = storeToRefs(store)

const manager = ref<ManagerStatus | null>(null)

onMounted(async () => {
  store.loadStatus()
  try {
    manager.value = await api.managerStatus()
  } catch {
    manager.value = null
  }
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
  </div>
</template>
