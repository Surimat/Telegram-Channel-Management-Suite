<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type ReactionJob,
  type ReactionProfile,
  type ReactionRule,
  type ReactionStats,
  type SimulationResult,
} from '@/api/client'

type Tab = 'overview' | 'profiles' | 'rules' | 'simulation' | 'queue'
const tab = ref<Tab>('overview')

const stats = ref<ReactionStats | null>(null)
const profiles = ref<ReactionProfile[]>([])
const rules = ref<ReactionRule[]>([])
const jobs = ref<ReactionJob[]>([])
const jobFilter = ref('')
const loading = ref(true)
const error = ref('')
const notice = ref('')

const simulation = ref<SimulationResult | null>(null)
const simText = ref('Спасибо за донат, друзья!')
const simProfileId = ref('')
const simBotCount = ref(6)
const simSeed = ref<number | ''>(42)
const simulating = ref(false)

// Profile editor state.
const editingProfile = ref<Partial<ReactionProfile> | null>(null)
const emojiText = ref('')

// Rule editor state.
const editingRule = ref<Partial<ReactionRule> | null>(null)

const CATEGORY_HINTS: Record<string, string> = {
  donation: 'Донат / поддержка',
  news: 'Новость',
  funny: 'Смешное',
  sad: 'Грустное',
  angry: 'Злое / возмущение',
  cute: 'Милое',
  support: 'Поддержка',
  announcement: 'Анонс',
  neutral: 'Обычное',
}
const categories = ref(Object.keys(CATEGORY_HINTS))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, p, r, j] = await Promise.all([
      api.reactionStatus(),
      api.reactionProfiles(),
      api.reactionRules(),
      api.reactionJobs(),
    ])
    stats.value = s
    profiles.value = p
    rules.value = r
    jobs.value = j.items
    if (!simProfileId.value && p.length) {
      simProfileId.value = p.find((x) => x.is_default)?.id ?? p[0].id
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить данные реакций.'
  } finally {
    loading.value = false
  }
}

async function loadJobs() {
  const params: Record<string, string> = {}
  if (jobFilter.value) params.status = jobFilter.value
  const page = await api.reactionJobs(params)
  jobs.value = page.items
}

async function toggleSystem() {
  if (!stats.value) return
  const updated = stats.value.enabled ? await api.disableReactions() : await api.enableReactions()
  stats.value = updated
  notice.value = updated.enabled ? 'Система реакций включена.' : 'Система реакций выключена.'
}

function newProfile() {
  editingProfile.value = {
    name: 'Новый профиль',
    enabled: true,
    allowed_emoji: ['❤️', '👍', '🔥'],
    participation_probability: 0.7,
    skip_probability: 0.1,
    delay_min: 30,
    delay_max: 900,
    delay_preset: 'normal',
    max_bots_per_post: 0,
  }
  emojiText.value = '❤️ 👍 🔥'
}

function editProfile(p: ReactionProfile) {
  editingProfile.value = { ...p }
  emojiText.value = p.allowed_emoji.join(' ')
}

async function saveProfile() {
  if (!editingProfile.value) return
  const payload: Partial<ReactionProfile> = {
    ...editingProfile.value,
    allowed_emoji: emojiText.value.split(/\s+/).filter(Boolean),
  }
  try {
    if (editingProfile.value.id) {
      await api.updateProfile(editingProfile.value.id, payload)
    } else {
      await api.createProfile(payload)
    }
    editingProfile.value = null
    notice.value = 'Профиль сохранён.'
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить профиль.'
  }
}

async function removeProfile(id: string) {
  if (!confirm('Удалить этот профиль реакций?')) return
  await api.deleteProfile(id)
  await load()
}

function newRule() {
  editingRule.value = {
    name: 'Новое правило',
    category: 'neutral',
    enabled: true,
    priority: 0,
    manual_override: false,
    language: '',
    keywords: [],
    phrases: [],
    exclusions: [],
    allowed_reactions: [],
    forbidden_reactions: [],
    preferred_reactions: [],
    min_confidence: 0.3,
  }
}

function editRule(r: ReactionRule) {
  editingRule.value = { ...r }
}

async function saveRule() {
  if (!editingRule.value) return
  try {
    if (editingRule.value.id) {
      await api.updateRule(editingRule.value.id, editingRule.value)
    } else {
      await api.createRule(editingRule.value)
    }
    editingRule.value = null
    notice.value = 'Правило сохранено.'
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить правило.'
  }
}

async function removeRule(id: string) {
  if (!confirm('Удалить это правило?')) return
  await api.deleteRule(id)
  await load()
}

async function runSimulation() {
  simulating.value = true
  error.value = ''
  try {
    simulation.value = await api.simulate({
      text: simText.value,
      profile_id: simProfileId.value || undefined,
      bot_count: Number(simBotCount.value) || undefined,
      seed: simSeed.value === '' ? undefined : Number(simSeed.value),
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось выполнить симуляцию.'
  } finally {
    simulating.value = false
  }
}

async function ingestPost() {
  try {
    await api.createPost({ text: simText.value, plan: true })
    notice.value = 'Пост добавлен, реакции запланированы.'
    await load()
    tab.value = 'queue'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось добавить пост.'
  }
}

const percent = (v: number) => `${Math.round(v * 100)}%`
const queueCount = computed(() => stats.value?.queue_total ?? 0)

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Реакции</h2>
    <p class="page-subtitle">
      Автоматические реакции ботов на посты канала. Здесь можно настроить профили, правила
      классификации, посмотреть план в режиме симуляции и отслеживать очередь заданий.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card ok-text">{{ notice }}</div>

    <div class="toolbar">
      <button :class="{ primary: tab === 'overview' }" @click="tab = 'overview'">Обзор</button>
      <button :class="{ primary: tab === 'profiles' }" @click="tab = 'profiles'">Профили</button>
      <button :class="{ primary: tab === 'rules' }" @click="tab = 'rules'">Правила</button>
      <button :class="{ primary: tab === 'simulation' }" @click="tab = 'simulation'">
        Симуляция
      </button>
      <button :class="{ primary: tab === 'queue' }" @click="tab = 'queue'">Очередь</button>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>

    <!-- OVERVIEW -->
    <template v-else-if="tab === 'overview'">
      <div class="card">
        <h3>
          <span
            class="status-dot"
            :class="stats?.enabled ? 'status-ok' : 'status-warning'"
          ></span>
          Система: {{ stats?.enabled ? 'включена' : 'выключена' }}
        </h3>
        <p class="muted">
          {{
            stats?.enabled
              ? 'Система включена: боты ставят реакции автоматически по правилам и профилям.'
              : 'Пока система выключена, боты не ставят реакции автоматически. Правила и профили можно настроить заранее.'
          }}
        </p>
        <button class="primary" @click="toggleSystem">
          {{ stats?.enabled ? 'Выключить реакции' : 'Включить реакции' }}
        </button>
      </div>

      <div class="grid" v-if="stats">
        <div class="card">
          <strong>Боты</strong>
          <p>{{ stats.active_bots }} активных</p>
          <p class="muted">Боты, готовые ставить реакции.</p>
        </div>
        <div class="card">
          <strong>Очередь</strong>
          <p>{{ queueCount }} заданий</p>
          <p class="muted">Запланировано и ещё не выполнено.</p>
        </div>
        <div class="card">
          <strong>Сегодня</strong>
          <p>запланировано: {{ stats.planned_today }}</p>
          <p>выполнено: {{ stats.done_today }}</p>
          <p :class="{ 'error-text': stats.failed_today > 0 }">
            ошибок: {{ stats.failed_today }}
          </p>
        </div>
        <div class="card">
          <strong>Последний пост</strong>
          <template v-if="stats.last_post">
            <p>{{ stats.last_post.category_title }}</p>
            <p class="muted">реакций: {{ stats.last_post.reactions }}</p>
          </template>
          <p v-else class="muted">Постов ещё не было.</p>
        </div>
      </div>
    </template>

    <!-- PROFILES -->
    <template v-else-if="tab === 'profiles'">
      <div class="card">
        <button class="primary" @click="newProfile">Создать профиль</button>
      </div>

      <div v-if="editingProfile" class="card">
        <h3>{{ editingProfile.id ? 'Редактирование профиля' : 'Новый профиль' }}</h3>
        <label class="field">
          <span>Название</span>
          <input v-model="editingProfile.name" />
        </label>
        <label class="field">
          <span>Разрешённые emoji (через пробел)</span>
          <input v-model="emojiText" placeholder="❤️ 👍 🔥" />
        </label>
        <label class="field">
          <span>Вероятность участия бота ({{ percent(editingProfile.participation_probability ?? 0) }})</span>
          <input
            type="range" min="0" max="1" step="0.05"
            v-model.number="editingProfile.participation_probability"
          />
        </label>
        <p class="muted">
          Шанс, что каждый бот вообще участвует. 100% — участвуют все боты.
        </p>
        <label class="field">
          <span>Вероятность пропуска ({{ percent(editingProfile.skip_probability ?? 0) }})</span>
          <input
            type="range" min="0" max="1" step="0.05"
            v-model.number="editingProfile.skip_probability"
          />
        </label>
        <p class="muted">
          Даже если бот участвует, он может «передумать» с этой вероятностью — так реакции
          выглядят естественнее.
        </p>
        <div class="two-cols">
          <label class="field">
            <span>Минимальная задержка, сек</span>
            <input type="number" min="0" v-model.number="editingProfile.delay_min" />
          </label>
          <label class="field">
            <span>Максимальная задержка, сек</span>
            <input type="number" min="0" v-model.number="editingProfile.delay_max" />
          </label>
        </div>
        <label class="field">
          <span>Распределение задержек</span>
          <select v-model="editingProfile.delay_preset">
            <option value="early">Быстро — боты реагируют почти сразу</option>
            <option value="normal">Обычно — равномерно по времени</option>
            <option value="spread">Растянуто — по всему окну</option>
          </select>
        </label>
        <label class="field">
          <span>Максимум ботов на пост (0 = без ограничения)</span>
          <input type="number" min="0" v-model.number="editingProfile.max_bots_per_post" />
        </label>
        <label class="field-inline">
          <input type="checkbox" v-model="editingProfile.enabled" /> Профиль включён
        </label>
        <label class="field-inline">
          <input type="checkbox" v-model="editingProfile.is_default" /> Использовать по умолчанию
        </label>
        <div class="actions">
          <button class="primary" @click="saveProfile">Сохранить</button>
          <button @click="editingProfile = null">Отмена</button>
        </div>
      </div>

      <div v-if="!profiles.length && !editingProfile" class="card empty">
        Профилей пока нет. Создайте первый профиль реакций.
      </div>

      <div v-for="p in profiles" :key="p.id" class="card">
        <div class="row-between">
          <strong>
            {{ p.name }}
            <span v-if="p.is_default" class="badge">по умолчанию</span>
            <span v-if="!p.enabled" class="badge badge-muted">выключен</span>
          </strong>
          <div class="actions">
            <button @click="editProfile(p)">Изменить</button>
            <button class="danger" @click="removeProfile(p.id)">Удалить</button>
          </div>
        </div>
        <p>Emoji: {{ p.allowed_emoji.join(' ') || '—' }}</p>
        <p class="muted">
          Участие: {{ percent(p.participation_probability) }} · пропуск:
          {{ percent(p.skip_probability) }} · задержка {{ p.delay_min }}–{{ p.delay_max }} сек
        </p>
      </div>
    </template>

    <!-- RULES -->
    <template v-else-if="tab === 'rules'">
      <div class="card">
        <button class="primary" @click="newRule">Создать правило</button>
        <p class="muted" style="margin-top: 8px">
          Правила определяют категорию поста по словам и фразам. Категория задаёт, какие
          реакции допустимы.
        </p>
      </div>

      <div v-if="editingRule" class="card">
        <h3>{{ editingRule.id ? 'Редактирование правила' : 'Новое правило' }}</h3>
        <div class="two-cols">
          <label class="field">
            <span>Название</span>
            <input v-model="editingRule.name" />
          </label>
          <label class="field">
            <span>Категория</span>
            <select v-model="editingRule.category">
              <option v-for="c in categories" :key="c" :value="c">
                {{ CATEGORY_HINTS[c] }} ({{ c }})
              </option>
            </select>
          </label>
        </div>
        <label class="field">
          <span>Ключевые слова (через запятую)</span>
          <input
            :value="(editingRule.keywords || []).join(', ')"
            @input="editingRule.keywords = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
          />
        </label>
        <label class="field">
          <span>Фразы (через запятую)</span>
          <input
            :value="(editingRule.phrases || []).join(', ')"
            @input="editingRule.phrases = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
          />
        </label>
        <label class="field">
          <span>Исключения (если встречается — правило не сработает)</span>
          <input
            :value="(editingRule.exclusions || []).join(', ')"
            @input="editingRule.exclusions = ($event.target as HTMLInputElement).value.split(',').map(s => s.trim()).filter(Boolean)"
          />
        </label>
        <div class="two-cols">
          <label class="field">
            <span>Разрешённые реакции</span>
            <input
              :value="(editingRule.allowed_reactions || []).join(' ')"
              @input="editingRule.allowed_reactions = ($event.target as HTMLInputElement).value.split(/\s+/).filter(Boolean)"
              placeholder="❤️ 🙏 👍"
            />
          </label>
          <label class="field">
            <span>Запрещённые реакции</span>
            <input
              :value="(editingRule.forbidden_reactions || []).join(' ')"
              @input="editingRule.forbidden_reactions = ($event.target as HTMLInputElement).value.split(/\s+/).filter(Boolean)"
              placeholder="😂 💩 🤡"
            />
          </label>
        </div>
        <div class="two-cols">
          <label class="field">
            <span>Приоритет</span>
            <input type="number" v-model.number="editingRule.priority" />
          </label>
          <label class="field">
            <span>Минимальная уверенность ({{ percent(editingRule.min_confidence ?? 0) }})</span>
            <input type="range" min="0" max="1" step="0.05" v-model.number="editingRule.min_confidence" />
          </label>
        </div>
        <label class="field-inline">
          <input type="checkbox" v-model="editingRule.enabled" /> Правило включено
        </label>
        <label class="field-inline">
          <input type="checkbox" v-model="editingRule.manual_override" /> Ручное переопределение
          (всегда побеждает)
        </label>
        <div class="actions">
          <button class="primary" @click="saveRule">Сохранить</button>
          <button @click="editingRule = null">Отмена</button>
        </div>
      </div>

      <div v-for="r in rules" :key="r.id" class="card">
        <div class="row-between">
          <strong>
            {{ r.name || r.category }}
            <span class="badge">{{ CATEGORY_HINTS[r.category] || r.category }}</span>
            <span v-if="r.manual_override" class="badge">ручное</span>
            <span v-if="!r.enabled" class="badge badge-muted">выкл.</span>
          </strong>
          <div class="actions">
            <button @click="editRule(r)">Изменить</button>
            <button class="danger" @click="removeRule(r.id)">Удалить</button>
          </div>
        </div>
        <p class="muted">
          приоритет {{ r.priority }} · слова: {{ r.keywords.join(', ') || '—' }}
        </p>
        <p v-if="r.allowed_reactions.length">допустимо: {{ r.allowed_reactions.join(' ') }}</p>
        <p v-if="r.forbidden_reactions.length" class="error-text">
          запрещено: {{ r.forbidden_reactions.join(' ') }}
        </p>
      </div>
    </template>

    <!-- SIMULATION -->
    <template v-else-if="tab === 'simulation'">
      <div class="card">
        <h3>Симуляция реакций</h3>
        <p class="muted">
          Режим симуляции ничего не отправляет в Telegram. Он показывает, как система поступит с
          таким постом.
        </p>
        <label class="field">
          <span>Текст поста</span>
          <input v-model="simText" />
        </label>
        <div class="two-cols">
          <label class="field">
            <span>Профиль</span>
            <select v-model="simProfileId">
              <option value="">Автоматически</option>
              <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </label>
          <label class="field">
            <span>Ботов (если реальных нет)</span>
            <input type="number" min="1" max="50" v-model.number="simBotCount" />
          </label>
        </div>
        <label class="field">
          <span>Зерно (для повторяемого результата)</span>
          <input type="number" v-model.number="simSeed" />
        </label>
        <div class="actions">
          <button class="primary" :disabled="simulating" @click="runSimulation">
            {{ simulating ? 'Считаем…' : 'Запустить симуляцию' }}
          </button>
          <button @click="ingestPost">Добавить пост и запланировать</button>
        </div>
      </div>

      <div v-if="simulation" class="card">
        <h3>Результат</h3>
        <p><strong>Категория:</strong> {{ simulation.category_title }} ({{ simulation.category }})</p>
        <p class="muted">
          уверенность: {{ percent(simulation.confidence) }} · источник: {{ simulation.source }}
        </p>
        <p><strong>Разрешённые реакции:</strong> {{ simulation.allowed_reactions.join(' ') }}</p>
        <p v-if="simulation.preferred_reactions.length">
          <strong>Предпочтительные:</strong> {{ simulation.preferred_reactions.join(' ') }}
        </p>
        <p v-if="simulation.forbidden_reactions.length" class="error-text">
          <strong>Запрещённые:</strong> {{ simulation.forbidden_reactions.join(' ') }}
        </p>
        <p class="muted">
          Профиль «{{ simulation.profile_name }}» · ботов: {{ simulation.total_bots }} ·
          участвуют: {{ simulation.participating }} · пропуск: {{ simulation.skipped }}
        </p>

        <h4>План</h4>
        <table class="table">
          <thead>
            <tr><th>Бот</th><th>Реакция</th><th>Через</th><th>Статус</th></tr>
          </thead>
          <tbody>
            <tr v-for="(s, i) in simulation.steps" :key="i">
              <td>{{ s.bot_username }}</td>
              <td>{{ s.emoji || '—' }}</td>
              <td>{{ s.status === 'scheduled' ? s.delay_human : '—' }}</td>
              <td>
                <span class="badge" :class="{ 'badge-muted': s.status !== 'scheduled' }">
                  {{ s.status === 'scheduled' ? 'реакция' : 'пропуск' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- QUEUE -->
    <template v-else-if="tab === 'queue'">
      <div class="card">
        <label>
          Статус:
          <select v-model="jobFilter" @change="loadJobs">
            <option value="">Все</option>
            <option value="planned">Запланировано</option>
            <option value="scheduled">В очереди</option>
            <option value="running">Выполняется</option>
            <option value="done">Готово</option>
            <option value="failed">Ошибка</option>
            <option value="skipped">Пропущено</option>
            <option value="cancelled">Отменено</option>
          </select>
        </label>
      </div>

      <div v-if="!jobs.length" class="card empty">Заданий реакций пока нет.</div>
      <div v-for="j in jobs" :key="j.id" class="card">
        <div class="row-between">
          <strong>{{ j.reaction || '—' }}</strong>
          <span class="badge" :class="{ 'badge-muted': j.status !== 'done' }">{{ j.status }}</span>
        </div>
        <p class="muted">
          попыток: {{ j.attempts }} ·
          {{ j.scheduled_at ? new Date(j.scheduled_at).toLocaleString('ru-RU') : '—' }}
        </p>
        <p v-if="j.error" class="error-text">{{ j.error }}</p>
      </div>
    </template>
  </div>
</template>
