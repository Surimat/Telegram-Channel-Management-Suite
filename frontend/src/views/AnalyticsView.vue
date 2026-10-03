<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, type AnalyticsOverview } from '@/api/client'
import Sparkline from '@/components/Sparkline.vue'
import BarList from '@/components/BarList.vue'

const days = ref(30)
const data = ref<AnalyticsOverview | null>(null)
const loading = ref(false)
const error = ref('')

const periodOptions = [
  { value: 7, label: '7 дней' },
  { value: 14, label: '14 дней' },
  { value: 30, label: '30 дней' },
  { value: 90, label: '90 дней' },
  { value: 365, label: 'Год' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.analyticsOverview(days.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить аналитику.'
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)

function changeLabel(percent: number | null): string {
  if (percent === null) return 'нет данных для сравнения'
  if (percent === 0) return 'столько же, как раньше'
  const dir = percent > 0 ? 'больше' : 'меньше'
  return `${Math.abs(Math.round(percent))}% ${dir}, чем за прошлый период`
}

const categoryBars = computed(() =>
  (data.value?.content.by_category ?? []).map((c) => ({ label: c.title, value: c.count })),
)
const sourceBars = computed(() =>
  (data.value?.content.by_source ?? []).map((c) => ({ label: c.title, value: c.count })),
)
const emojiBars = computed(() =>
  (data.value?.reactions.by_emoji ?? []).map((e) => ({ label: e.reaction, value: e.count })),
)
const reactionCategoryBars = computed(() =>
  (data.value?.reactions.by_category ?? []).map((c) => ({ label: c.title, value: c.count })),
)
const sourceUserBars = computed(() =>
  (data.value?.audience.top_sources ?? []).map((s) => ({
    label: s.title || s.username,
    value: s.users,
  })),
)

function percent(value: number | null): string {
  if (value === null) return '—'
  return `${Math.round(value * 100)}%`
}

function audienceStatusCount(key: string): number {
  return data.value?.audience.by_status.find((s) => s.key === key)?.count ?? 0
}
</script>

<template>
  <div>
    <h2 class="page-title">Аналитика</h2>
    <p class="page-subtitle">
      Простые графики и пояснения: сколько вы публикуете, как реагируют боты и как растёт аудитория.
    </p>

    <div class="toolbar">
      <label class="field" style="margin: 0">
        <span>Период</span>
        <select v-model.number="days" @change="load">
          <option v-for="opt in periodOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </label>
      <button :disabled="loading" @click="load">
        {{ loading ? 'Загружаем…' : 'Обновить' }}
      </button>
    </div>

    <div v-if="loading && !data" class="card">Загрузка аналитики…</div>
    <div v-else-if="error" class="card error-text">{{ error }}</div>

    <template v-else-if="data">
      <div class="card">
        <h3>Кратко о главном</h3>
        <p v-for="(note, i) in data.summary" :key="i" class="summary-note">{{ note }}</p>
      </div>

      <div class="grid">
        <div class="card">
          <div class="muted">Постов всего</div>
          <div class="metric">{{ data.headline.posts_total }}</div>
          <p class="muted">
            За {{ data.days }} дн.: {{ data.headline.posts_window }} —
            {{ changeLabel(data.headline.posts_change_percent) }}.
          </p>
          <RouterLink to="/reactions">Посты и реакции →</RouterLink>
        </div>
        <div class="card">
          <div class="muted">Реакций запланировано</div>
          <div class="metric">{{ data.headline.reactions_total }}</div>
          <p class="muted">
            Успешность:
            {{ data.headline.reaction_success_rate === null ? '—' : percent(data.headline.reaction_success_rate) }}
          </p>
          <RouterLink to="/reactions">Настроить реакции →</RouterLink>
        </div>
        <div class="card">
          <div class="muted">Аудитория</div>
          <div class="metric">{{ data.headline.audience_total }}</div>
          <p class="muted">Новых за 7 дней: {{ data.headline.audience_new_7d }}</p>
          <RouterLink to="/invites">Приглашения →</RouterLink>
        </div>
        <div class="card">
          <div class="muted">Источников аудитории</div>
          <div class="metric">{{ data.headline.sources_total }}</div>
          <p class="muted">Связей «источник ↔ пользователь»: {{ data.audience.links_total }}</p>
        </div>
      </div>

      <div class="card">
        <Sparkline :points="data.content.per_day" label="Публикации по дням" />
        <p class="muted">
          В среднем {{ data.content.average_per_day }} постов в день за период.
        </p>
      </div>

      <div class="two-cols">
        <div class="card">
          <h3>Категории постов</h3>
          <p class="muted">Как система классифицировала публикации.</p>
          <BarList :items="categoryBars" empty-text="Постов пока нет." />
        </div>
        <div class="card">
          <h3>Кто определял категорию</h3>
          <p class="muted">Обычные правила или Мини-ИИ.</p>
          <BarList :items="sourceBars" empty-text="Нет данных." />
        </div>
      </div>

      <div class="card">
        <Sparkline :points="data.reactions.per_day" label="Реакции: запланировано по дням" color="var(--warning)" />
      </div>
      <div class="card">
        <Sparkline
          :points="data.reactions.completed_per_day"
          label="Реакции: выполнено по дням"
          color="var(--ok)"
        />
      </div>

      <div class="two-cols">
        <div class="card">
          <h3>Популярные реакции</h3>
          <BarList :items="emojiBars" empty-text="Реакций пока не было." />
        </div>
        <div class="card">
          <h3>Реакции по категориям</h3>
          <BarList :items="reactionCategoryBars" empty-text="Нет данных." />
        </div>
      </div>

      <div class="card">
        <Sparkline :points="data.audience.per_day" label="Новые пользователи по дням" color="var(--primary-dark)" />
      </div>

      <div class="two-cols">
        <div class="card">
          <h3>Крупнейшие источники</h3>
          <p class="muted">Сколько пользователей пришло из каждого источника.</p>
          <BarList :items="sourceUserBars" empty-text="Источники ещё не сканировались." />
        </div>
        <div class="card">
          <h3>Состояние аудитории</h3>
          <ul class="plain-list">
            <li>Активные: {{ audienceStatusCount('active') }}</li>
            <li>Неактивные: {{ audienceStatusCount('inactive') }}</li>
            <li>Удалённые: {{ audienceStatusCount('deleted') }}</li>
            <li>Заблокированные: {{ audienceStatusCount('blocked') }}</li>
            <li>Неизвестные: {{ audienceStatusCount('unknown') }}</li>
          </ul>
          <p class="muted">
            Приглашено: {{ data.audience.invites['invited'] ?? 0 }} ·
            уже были в канале: {{ data.audience.invites['already_member'] ?? 0 }} ·
            из-за приватности: {{ data.audience.invites['privacy'] ?? 0 }}
          </p>
        </div>
      </div>

      <div class="card">
        <h3>Эффективность сканирования источников</h3>
        <p class="muted">Сколько найдено, сколько новых и сколько дублей.</p>
        <div v-if="!data.audience.source_effectiveness.length" class="empty">Нет данных.</div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>Источник</th>
              <th>Найдено</th>
              <th>Новых</th>
              <th>Дублей</th>
              <th>Ошибок</th>
              <th>Полнота</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in data.audience.source_effectiveness" :key="s.id">
              <td>{{ s.title || s.username }}</td>
              <td>{{ s.discovered }}</td>
              <td>{{ s.new }}</td>
              <td>{{ s.duplicates }}</td>
              <td>{{ s.errors }}</td>
              <td>{{ s.completeness }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
