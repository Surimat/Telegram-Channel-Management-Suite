<script setup lang="ts">
// Horizontal bar list for titled counts (categories, emoji, sources…).
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    items: { label: string; value: number; hint?: string }[]
    emptyText?: string
  }>(),
  { emptyText: 'Нет данных.' },
)

const max = computed(() => Math.max(1, ...props.items.map((i) => i.value)))
</script>

<template>
  <div>
    <div v-if="!items.length" class="empty">{{ emptyText }}</div>
    <div v-for="item in items" :key="item.label" class="bar-row">
      <div class="row-between">
        <span>{{ item.label }}</span>
        <span class="muted">{{ item.value }}{{ item.hint ? ' · ' + item.hint : '' }}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" :style="{ width: (item.value / max) * 100 + '%' }"></div>
      </div>
    </div>
  </div>
</template>
