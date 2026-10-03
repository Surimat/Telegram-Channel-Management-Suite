<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAppStore } from '@/stores/app'
import { api, type BotSummary, type ReactionStats, type SessionSummary } from '@/api/client'

const store = useAppStore()
const { status, loading, error } = storeToRefs(store)
const bots = ref<BotSummary | null>(null)
const reactions = ref<ReactionStats | null>(null)
const accounts = ref<SessionSummary | null>(null)

onMounted(async () => {
  if (!store.status) store.loadStatus()
  try {
    bots.value = await api.botsSummary()
  } catch {
    bots.value = null
  }
  try {
    reactions.value = await api.reactionStatus()
  } catch {
    reactions.value = null
  }
  try {
    accounts.value = await api.sessionsSummary()
  } catch {
    accounts.value = null
  }
})

const accountsLabel = (s: SessionSummary | null) => {
  if (!s || s.total === 0) return 'Пользовательские аккаунты ещё не добавлены.'
  if (s.online > 0) return `Готовых аккаунтов: ${s.online} из ${s.total}.`
  return `Аккаунтов: ${s.total}, ни один не авторизован.`
}

const overallLabel = (value: string | undefined) => {
  if (value === 'ok') return 'Всё в порядке'
  if (value === 'warning') return 'Требуется внимание'
  if (value === 'error') return 'Есть проблемы'
  return 'Проверяем…'
}

const managerLabel = (s: BotSummary | null) => {
  if (!s || !s.manager_connected) return 'Управляющий бот ещё не подключён.'
  if (s.manager_health === 'ok') return `Управляющий бот @${s.manager_username} работает.`
  return `Управляющий бот @${s.manager_username}: ${s.manager_health}.`
}
</script>

<template>
  <div>
    <h2 class="page-title">Панель управления</h2>
    <p class="page-subtitle">
      Краткая сводка о состоянии вашей системы. Здесь всё объясняется простыми словами.
    </p>

    <div v-if="loading" class="card">Загрузка состояния...</div>
    <div v-else-if="error" class="card error-text">{{ error }}</div>

    <template v-else-if="status">
      <div class="card">
        <h3>
          <span class="status-dot" :class="'status-' + status.overall"></span>
          {{ overallLabel(status.overall) }}
        </h3>
        <p class="muted">Версия {{ status.version }} · режим: {{ status.environment }}</p>
        <p>
          Ниже показано, что уже настроено, а что стоит доделать. Каждый пункт содержит
          подсказку «что сделать».
        </p>
      </div>

      <div class="grid">
        <div class="card">
          <div>
            <span class="status-dot" :class="'status-' + (bots?.manager_health ?? 'unknown')"></span>
            <strong>Telegram</strong>
          </div>
          <p>{{ managerLabel(bots) }}</p>
          <p v-if="bots" class="muted">
            Всего ботов: {{ bots.total }} · управляемых: {{ bots.by_kind['managed'] ?? 0 }}
          </p>
          <RouterLink to="/bots">Управление ботами →</RouterLink>
        </div>
        <div v-if="reactions" class="card">
          <div>
            <span
              class="status-dot"
              :class="reactions.enabled ? 'status-ok' : 'status-warning'"
            ></span>
            <strong>Реакции</strong>
          </div>
          <p>
            {{ reactions.enabled ? 'Автоматические реакции включены.' : 'Автоматические реакции выключены.' }}
          </p>
          <p class="muted">
            Ботов: {{ reactions.active_bots }} · в очереди: {{ reactions.queue_total }} ·
            сегодня выполнено: {{ reactions.done_today }}
          </p>
          <RouterLink to="/reactions">Настроить реакции →</RouterLink>
        </div>
        <div v-if="accounts" class="card">
          <div>
            <span
              class="status-dot"
              :class="accounts.online > 0 ? 'status-ok' : accounts.total > 0 ? 'status-warning' : 'status-unknown'"
            ></span>
            <strong>Аккаунты</strong>
          </div>
          <p>{{ accountsLabel(accounts) }}</p>
          <p class="muted">
            Авторизовано: {{ accounts.online }} · нужна авторизация: {{ accounts.auth_required }}
          </p>
          <RouterLink to="/sessions">Управление аккаунтами →</RouterLink>
        </div>
        <div v-for="check in status.checks" :key="check.key" class="card">
          <div>
            <span class="status-dot" :class="'status-' + check.status"></span>
            <strong>{{ check.title }}</strong>
          </div>
          <p>{{ check.meaning }}</p>
          <p v-if="check.how_to_fix" class="muted">{{ check.how_to_fix }}</p>
        </div>
      </div>

      <div class="card">
        <RouterLink to="/system">Открыть мастер настройки (Setup Wizard) →</RouterLink>
      </div>
    </template>
  </div>
</template>
