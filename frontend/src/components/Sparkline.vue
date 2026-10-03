<script setup lang="ts">
// Lightweight inline-SVG chart. No charting dependency (portable/low-end PCs).
import { computed } from 'vue'
import type { DayPoint } from '@/api/client'

const props = withDefaults(
  defineProps<{
    points: DayPoint[]
    height?: number
    color?: string
    label?: string
    unit?: string
  }>(),
  { height: 140, color: 'var(--primary)', label: 'Показатель', unit: '' },
)

const width = 720
const padX = 8
const padY = 12

const maxCount = computed(() => Math.max(1, ...props.points.map((p) => p.count)))
const total = computed(() => props.points.reduce((sum, p) => sum + p.count, 0))

const coords = computed(() =>
  props.points.map((p, i) => {
    const n = Math.max(props.points.length - 1, 1)
    const x = padX + (i / n) * (width - padX * 2)
    const y = padY + (1 - p.count / maxCount.value) * (props.height - padY * 2)
    return { x, y, ...p }
  }),
)

const linePath = computed(() =>
  coords.value.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' '),
)

const areaPath = computed(() => {
  if (!coords.value.length) return ''
  const first = coords.value[0]
  const last = coords.value[coords.value.length - 1]
  const base = props.height - padY
  return `${linePath.value} L${last.x.toFixed(1)},${base} L${first.x.toFixed(1)},${base} Z`
})

const firstDate = computed(() => props.points[0]?.date ?? '')
const lastDate = computed(() => props.points[props.points.length - 1]?.date ?? '')
</script>

<template>
  <div class="chart">
    <div class="row-between">
      <strong>{{ label }}</strong>
      <span class="muted">Всего за период: {{ total }}{{ unit ? ' ' + unit : '' }}</span>
    </div>
    <div v-if="!points.length" class="empty">Нет данных за выбранный период.</div>
    <template v-else>
      <svg
        class="chart-svg"
        :viewBox="`0 0 ${width} ${height}`"
        preserveAspectRatio="none"
        role="img"
        :aria-label="label"
      >
        <path :d="areaPath" :fill="color" opacity="0.12" />
        <path :d="linePath" :stroke="color" stroke-width="2" fill="none" />
        <circle
          v-for="c in coords"
          :key="c.date"
          :cx="c.x"
          :cy="c.y"
          r="2"
          :fill="color"
        />
      </svg>
      <div class="row-between muted chart-axis">
        <span>{{ firstDate }}</span>
        <span>{{ lastDate }}</span>
      </div>
    </template>
  </div>
</template>
