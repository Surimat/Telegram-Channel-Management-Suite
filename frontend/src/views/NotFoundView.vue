<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div>
    <h2 class="page-title">Страница не найдена</h2>
    <p class="page-subtitle">Такого раздела нет. Возможно, ссылка устарела.</p>
    <div class="card">
      <RouterLink to="/">Вернуться на панель управления →</RouterLink>
    </div>
  </div>
</template>
