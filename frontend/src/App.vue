<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useMiniAppStore } from '@/stores/miniapp'
import { useHelpStore } from '@/stores/help'

const mini = useMiniAppStore()
const { inTelegram, loading, authenticated, error, hint, user } = storeToRefs(mini)
const help = useHelpStore()

// Shown at the bottom inside Telegram (mobile-first). The desktop sidebar keeps
// the full list; the Mini App shows the sections required by the brief.
const mobileNav = [
  { to: '/', label: 'Панель' },
  { to: '/bots', label: 'Боты' },
  { to: '/sessions', label: 'Аккаунты' },
  { to: '/audience', label: 'Аудитория' },
  { to: '/reactions', label: 'Реакции' },
  { to: '/queue', label: 'Очередь' },
  { to: '/analytics', label: 'Аналитика' },
  { to: '/diagnostics', label: 'Диагностика' },
  { to: '/system', label: 'Система' },
  { to: '/settings', label: 'Настройки' },
]

onMounted(() => {
  mini.bootstrap()
  help.load()
})
</script>

<template>
  <div v-if="inTelegram && loading" class="miniapp-gate">
    <div class="card">Проверяем вход через Telegram…</div>
  </div>

  <div v-else-if="inTelegram && error" class="miniapp-gate">
    <div class="card">
      <h3>Вход не выполнен</h3>
      <p>{{ error }}</p>
      <p v-if="hint" class="muted">{{ hint }}</p>
    </div>
  </div>

  <div v-else class="layout" :class="{ 'is-mobile': inTelegram && authenticated }">
    <aside class="sidebar">
      <h1>Telegram Channel<br />Management Suite</h1>
      <nav>
        <RouterLink class="nav-item" to="/">Панель</RouterLink>
        <RouterLink class="nav-item" to="/bots">Боты</RouterLink>
        <RouterLink class="nav-item" to="/channels">Каналы</RouterLink>
        <RouterLink class="nav-item" to="/sessions">Аккаунты</RouterLink>
        <RouterLink class="nav-item" to="/sources">Источники</RouterLink>
        <RouterLink class="nav-item" to="/audience">Аудитория</RouterLink>
        <RouterLink class="nav-item" to="/invites">Приглашения</RouterLink>
        <RouterLink class="nav-item" to="/campaigns">Кампании</RouterLink>
        <RouterLink class="nav-item" to="/reactions">Реакции</RouterLink>
        <RouterLink class="nav-item" to="/ai">Мини-ИИ</RouterLink>
        <RouterLink class="nav-item" to="/analytics">Аналитика</RouterLink>
        <RouterLink class="nav-item" to="/system">Система</RouterLink>
        <RouterLink class="nav-item" to="/diagnostics">Диагностика</RouterLink>
        <RouterLink class="nav-item" to="/backup">Резервные копии</RouterLink>
        <RouterLink class="nav-item" to="/queue">Очередь</RouterLink>
        <RouterLink class="nav-item" to="/logs">Логи</RouterLink>
        <RouterLink class="nav-item" to="/settings">Настройки</RouterLink>
      </nav>
    </aside>
    <main class="content">
      <p v-if="inTelegram && user" class="miniapp-user muted">
        Вы вошли как {{ user.display_name }}
      </p>
      <RouterView />
    </main>

    <nav v-if="inTelegram && authenticated" class="mobile-nav">
      <RouterLink
        v-for="item in mobileNav"
        :key="item.to"
        class="mobile-nav-item"
        :to="item.to"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
  </div>
</template>
