<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type ChannelOverview,
  type ChannelOverviewItem,
  type OverviewSection,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

// One read-only page: how each channel is doing across every module.
const SECTION_LABELS: Record<string, string> = {
  bindings: 'Боты',
  audience: 'Аудитория',
  invites: 'Приглашения',
  bots: 'Подготовка ботов',
  content: 'Контент',
  pipeline: 'Конвейер',
  queue: 'Очередь',
}

const overview = ref<ChannelOverview | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    overview.value = await api.channelOverview()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить сводку по каналам.'
  } finally {
    loading.value = false
  }
}

function attentionClass(level: string): string {
  if (level === 'ok') return 'status-ok'
  if (level === 'info') return 'status-info'
  if (level === 'warning') return 'status-warning'
  if (level === 'error') return 'status-error'
  return 'status-unknown'
}

function sections(item: ChannelOverviewItem): Array<{ name: string; title: string; section: OverviewSection }> {
  return Object.keys(SECTION_LABELS).map((name) => ({
    name,
    title: SECTION_LABELS[name],
    section: item[name as keyof ChannelOverviewItem] as OverviewSection,
  }))
}

function channelTitle(item: ChannelOverviewItem): string {
  return item.title || item.username || item.reference || item.id
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Сводка по каналам <InfoHint topic="channel" /></h2>
    <p class="page-subtitle">
      Один взгляд на состояние каждого канала: подключение ботов, аудитория, приглашения,
      публикации, конвейер и очередь. Страница только читает данные — ничего не меняет и не
      обходит ограничения Telegram.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="loading" class="card">Загружаем сводку…</div>

    <template v-else-if="overview">
      <div class="card">
        <p>
          <span class="status-dot" :class="attentionClass(overview.attention.level)"></span>
          {{ overview.attention.label }}
          <span class="muted">{{ overview.attention.reason }}</span>
        </p>
        <p class="muted">
          Требуют внимания: {{ overview.totals.needs_attention }} из {{ overview.totals.channels }}.
        </p>
        <p v-if="overview.events.status !== 'ok'" class="muted">
          Журнал каналов: {{ overview.events.label }}
        </p>
        <div class="toolbar">
          <button @click="load()">Обновить</button>
        </div>
      </div>

      <div v-if="overview.channels.length" class="overview-grid">
        <div v-for="item in overview.channels" :key="item.id" class="card overview-item">
          <div class="overview-head">
            <span class="status-dot" :class="attentionClass(item.attention.level)"></span>
            <strong>{{ channelTitle(item) }}</strong>
            <span v-if="item.is_default" class="badge">основной</span>
          </div>
          <p class="muted">{{ item.attention.reason }}</p>

          <div class="overview-sections">
            <div v-for="row in sections(item)" :key="row.name" class="overview-row">
              <span class="status-dot" :class="attentionClass(row.section.status)"></span>
              <span class="overview-name">{{ row.title }}</span>
              <span class="muted">{{ row.section.label }}</span>
            </div>
          </div>

          <p class="muted">
            Модули:
            {{ item.modules.filter((m) => m.enabled).map((m) => m.title).join(', ') || 'нет включённых' }}
          </p>
        </div>
      </div>
      <p v-else class="muted">Каналов пока нет — добавьте первый в разделе «Каналы».</p>
    </template>
  </div>
</template>

<style scoped>
.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 0.75rem;
}
.overview-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.overview-sections {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0.5rem 0;
}
.overview-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.overview-name {
  min-width: 8.5rem;
  font-weight: 600;
}
</style>
