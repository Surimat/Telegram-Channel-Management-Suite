<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useHelpStore } from '@/stores/help'

// Reusable beginner explanation. Two ways to use it:
//   <InfoHint topic="manager_bot" />
//   <InfoHint title="Канал" what="..." why="..." effect="..." when-off="..." />
// Respects the "Показывать пояснения" preference (on by default): when the user
// turns explanations off, the hint renders nothing and the UI stays clean.
const props = defineProps<{
  topic?: string
  title?: string
  what?: string
  why?: string
  effect?: string
  whenOff?: string
  safeDefault?: string
  label?: string
}>()

const help = useHelpStore()
const { showExplanations } = storeToRefs(help)
const open = ref(false)

onMounted(() => {
  if (!help.loaded) help.load()
})

const data = computed(() => {
  if (props.topic) {
    const t = help.topic(props.topic)
    if (t) return t
  }
  if (props.what) {
    return {
      key: props.topic ?? 'inline',
      title: props.title ?? '',
      what: props.what,
      why: props.why ?? '',
      effect: props.effect ?? '',
      when_off: props.whenOff ?? '',
      safe_default: props.safeDefault ?? '',
    }
  }
  return null
})

const visible = computed(() => showExplanations.value && !!data.value?.what)
const label = computed(() => props.label ?? 'Что это?')
</script>

<template>
  <span v-if="visible" class="info-hint">
    <button
      type="button"
      class="info-hint-toggle"
      :aria-expanded="open"
      :title="label"
      @click="open = !open"
    >
      <span class="info-hint-icon" aria-hidden="true">?</span>
      <span class="info-hint-label">{{ label }}</span>
    </button>
    <span v-if="open && data" class="info-hint-body">
      <strong v-if="data.title">{{ data.title }}</strong>
      <span v-if="data.what" class="info-hint-row">{{ data.what }}</span>
      <span v-if="data.why" class="info-hint-row"><em>Зачем:</em> {{ data.why }}</span>
      <span v-if="data.effect" class="info-hint-row"><em>Что произойдёт:</em> {{ data.effect }}</span>
      <span v-if="data.when_off" class="info-hint-row">
        <em>Если выключить:</em> {{ data.when_off }}
      </span>
      <span v-if="data.safe_default" class="info-hint-row">
        <em>Безопасно по умолчанию:</em> {{ data.safe_default }}
      </span>
    </span>
  </span>
</template>

<style scoped>
.info-hint {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  vertical-align: middle;
}

.info-hint-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
}

.info-hint-toggle:hover {
  color: var(--primary);
  border-color: var(--primary);
}

.info-hint-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.info-hint-body {
  display: block;
  margin-top: 6px;
  padding: 10px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: var(--radius);
  max-width: 460px;
  font-size: 13px;
  line-height: 1.45;
}

.info-hint-row {
  display: block;
  margin-top: 4px;
}

.info-hint-row em {
  color: var(--text-muted);
  font-style: normal;
  font-weight: 600;
}
</style>
