<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <h1>Telegram Channel<br />Management Suite</h1>
      <nav>
        <RouterLink class="nav-item" to="/">Панель</RouterLink>
        <RouterLink class="nav-item" to="/bots">Боты</RouterLink>
        <RouterLink class="nav-item" to="/reactions">Реакции</RouterLink>
        <RouterLink class="nav-item" to="/system">Система</RouterLink>
        <RouterLink class="nav-item" to="/queue">Очередь</RouterLink>
        <RouterLink class="nav-item" to="/logs">Логи</RouterLink>
        <RouterLink class="nav-item" to="/settings">Настройки</RouterLink>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
