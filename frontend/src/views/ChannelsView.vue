<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  api,
  type Binding,
  type Bot,
  type Capability,
  type Channel,
  type ChannelSummary,
  type UserSession,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const channels = ref<Channel[]>([])
const summary = ref<ChannelSummary | null>(null)
const accounts = ref<UserSession[]>([])
const bindings = ref<Binding[]>([])
const bots = ref<Bot[]>([])
const capabilities = ref<Record<string, Capability>>({})
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busyId = ref('')
const bindForm = ref<Record<string, string>>({})

const showAdd = ref(false)
const addBusy = ref(false)
const form = ref({ reference: '', title: '', make_default: false, note: '' })

const verifyAccount = ref('')

const MODULE_LABELS: Record<string, string> = {
  reactions: 'Реакции',
  audience: 'Аудитория',
  invites: 'Приглашения',
  analytics: 'Аналитика',
}
const MODULE_KEYS = Object.keys(MODULE_LABELS)

const STATUS_LABELS: Record<string, string> = {
  new: 'Не проверен',
  verified: 'Проверен',
  warning: 'С ограничениями',
  error: 'Ошибка',
  disabled: 'Отключён',
}

const KIND_LABELS: Record<string, string> = {
  channel: 'Канал',
  group: 'Группа',
  supergroup: 'Супергруппа',
  unknown: 'Не определён',
}

function statusClass(status: string): string {
  if (status === 'verified') return 'status-ok'
  if (status === 'warning' || status === 'new') return 'status-warning'
  if (status === 'error') return 'status-error'
  return 'status-unknown'
}

const anyDefault = computed(() => channels.value.some((c) => c.is_default))

function friendlyError(e: unknown): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || 'Произошла ошибка.'
}

async function load(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [list, sum, sess] = await Promise.all([
      api.channels({ limit: '200' }),
      api.channelsSummary(),
      api.sessions(),
    ])
    channels.value = list.items
    summary.value = sum
    accounts.value = sess
    if (!verifyAccount.value && sess.length) verifyAccount.value = sess[0].id
    try {
      const [bind, botList] = await Promise.all([api.bindings(), api.bots()])
      bindings.value = bind.items
      bots.value = botList
    } catch {
      bindings.value = []
      bots.value = []
    }
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function bindingsFor(channelId: string): Binding[] {
  return bindings.value.filter((b) => b.channel_id === channelId)
}

function botLabel(botId: string): string {
  const bot = bots.value.find((b) => b.id === botId)
  return bot ? bot.username ? '@' + bot.username : bot.title || bot.id : botId
}

async function connectBot(channel: Channel) {
  const botId = bindForm.value[channel.id]
  if (!botId) {
    error.value = 'Выберите бота для подключения.'
    return
  }
  busyId.value = channel.id
  error.value = ''
  notice.value = ''
  try {
    const binding = await api.connectBinding({ bot_id: botId, channel_id: channel.id })
    notice.value = binding.invite_link
      ? `Бот подключён. Добавьте его в канал по ссылке: ${binding.invite_link}`
      : 'Бот подключён. Нажмите «Проверить права».'
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

async function checkBinding(binding: Binding) {
  busyId.value = binding.channel_id
  error.value = ''
  notice.value = ''
  try {
    const result = await api.checkBinding(binding.id)
    notice.value = result.message
    if (!result.present && result.how_to_fix) notice.value += ' ' + result.how_to_fix
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

async function removeBinding(binding: Binding) {
  if (!confirm(`Отключить бота ${botLabel(binding.bot_id)} от канала?`)) return
  busyId.value = binding.channel_id
  try {
    await api.removeBinding(binding.id)
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

async function probeCapabilities(channel: Channel) {
  busyId.value = channel.id
  error.value = ''
  notice.value = ''
  try {
    const view = await api.probeCapability(channel.id)
    capabilities.value = { ...capabilities.value, [channel.id]: view }
    notice.value = view.message
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

async function submitAdd() {
  addBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.addChannel({
      reference: form.value.reference,
      title: form.value.title,
      make_default: form.value.make_default,
      note: form.value.note,
    })
    notice.value = 'Канал добавлен. Теперь проверьте его кнопкой «Проверить».'
    form.value = { reference: '', title: '', make_default: false, note: '' }
    showAdd.value = false
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    addBusy.value = false
  }
}

async function withChannel(id: string, fn: () => Promise<unknown>) {
  busyId.value = id
  error.value = ''
  notice.value = ''
  try {
    await fn()
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

const verify = (c: Channel) => {
  if (!verifyAccount.value) {
    error.value = 'Сначала добавьте Telegram-аккаунт в разделе «Аккаунты» и выберите его.'
    return
  }
  return withChannel(c.id, async () => {
    const res = await api.verifyChannel(c.id, verifyAccount.value)
    notice.value = res.found
      ? `Канал доступен: ${res.title || res.username || c.reference}. ${res.message}`.trim()
      : res.message || 'Не удалось проверить канал.'
  })
}

const makeDefault = (c: Channel) => withChannel(c.id, () => api.setChannelDefault(c.id))

const toggleModule = (c: Channel, key: string) =>
  withChannel(c.id, () =>
    api.setChannelModules(c.id, { ...c.modules, [key]: !c.modules[key] }),
  )

function remove(c: Channel) {
  if (!confirm(`Удалить канал «${c.title || c.reference}» из списка? Данные модулей останутся.`))
    return
  return withChannel(c.id, () => api.removeChannel(c.id))
}

onMounted(() => load())
</script>

<template>
  <div>
    <h2 class="page-title">Каналы <InfoHint topic="channel" /></h2>
    <p class="page-subtitle">
      Здесь хранится один список ваших каналов и групп. Добавьте канал один раз — и
      выбирайте его в реакциях, аудитории и приглашениях, не вводя заново. Проверка
      использует обычный аккаунт Telegram и никогда не обходит его ограничения.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div v-if="summary" class="grid">
      <div class="card">
        <strong>Всего каналов</strong>
        <p class="metric">{{ summary.total }}</p>
      </div>
      <div class="card">
        <strong>Проверено</strong>
        <p class="metric">{{ summary.verified }}</p>
      </div>
      <div class="card">
        <strong>С ограничениями</strong>
        <p class="metric">{{ summary.with_warning }}</p>
      </div>
      <div class="card">
        <strong>С ошибками</strong>
        <p class="metric">{{ summary.with_error }}</p>
      </div>
      <div class="card">
        <strong>Основной канал</strong>
        <p class="metric">{{ summary.default_channel_label || 'не выбран' }}</p>
        <p class="muted">Подставляется по умолчанию в остальных разделах</p>
      </div>
    </div>

    <div class="toolbar">
      <button class="primary" @click="showAdd = !showAdd">
        {{ showAdd ? 'Отмена' : '+ Добавить канал' }}
      </button>
      <button @click="load()">Обновить</button>
      <RouterLink to="/invites"><button>Приглашения →</button></RouterLink>
      <RouterLink to="/reactions"><button>Реакции →</button></RouterLink>
    </div>

    <div v-if="showAdd" class="card">
      <h3>Новый канал</h3>
      <p class="muted">
        Укажите @username, ссылку вида t.me/... или числовой Telegram ID (например
        -1001234567890). Для закрытого канала аккаунт должен уже состоять в нём.
      </p>
      <label class="field">
        <span>Ссылка, @username или ID</span>
        <input v-model="form.reference" placeholder="@channel или https://t.me/channel" />
      </label>
      <label class="field">
        <span>Название (необязательно)</span>
        <input v-model="form.title" placeholder="Понятное имя канала" />
      </label>
      <label class="field">
        <span>Заметка (необязательно)</span>
        <input v-model="form.note" placeholder="Например: основной новостной канал" />
      </label>
      <label class="toggle-row">
        <input v-model="form.make_default" type="checkbox" />
        <span>Сделать основным каналом</span>
      </label>
      <p class="inline-note">
        Основной канал подставляется по умолчанию в реакциях, приглашениях и аналитике.
        Его можно изменить в любой момент.
      </p>
      <button class="primary" :disabled="addBusy || !form.reference" @click="submitAdd">
        {{ addBusy ? 'Добавляем…' : 'Добавить канал' }}
      </button>
    </div>

    <div class="card">
      <label class="field">
        <span>Аккаунт для проверки каналов</span>
        <select v-model="verifyAccount">
          <option value="">— выберите аккаунт —</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.display_name || a.username || a.phone_masked || a.id }}
          </option>
        </select>
      </label>
      <p v-if="accounts.length === 0" class="muted">
        Нет аккаунтов. Добавьте Telegram-аккаунт в разделе «Аккаунты», чтобы проверять каналы.
      </p>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="channels.length === 0" class="card empty">
      Пока нет каналов. Нажмите «+ Добавить канал», чтобы указать ваш канал или группу.
    </div>
    <table v-else class="table">
      <thead>
        <tr>
          <th>Канал</th>
          <th>Тип</th>
          <th>Состояние</th>
          <th>Участников</th>
          <th>Модули</th>
          <th>Бот и реакции</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in channels" :key="c.id">
          <td>
            <strong>{{ c.title || c.reference }}</strong>
            <span v-if="c.is_default" class="badge">основной</span>
            <div class="muted">
              {{ c.username ? '@' + c.username : c.reference }}
              <span v-if="c.telegram_id"> · ID {{ c.telegram_id }}</span>
            </div>
            <div v-if="c.note" class="muted">{{ c.note }}</div>
          </td>
          <td>{{ KIND_LABELS[c.kind] ?? c.kind }}</td>
          <td>
            <span class="status-dot" :class="statusClass(c.status)"></span>
            {{ STATUS_LABELS[c.status] ?? c.status }}
            <div v-if="c.verification_message" class="muted">{{ c.verification_message }}</div>
            <div v-if="c.verification_hint" class="muted">{{ c.verification_hint }}</div>
            <div class="muted">
              {{ c.last_verified_at ? new Date(c.last_verified_at).toLocaleString() : 'не проверялся' }}
            </div>
          </td>
          <td>{{ c.participants_count != null ? c.participants_count : '—' }}</td>
          <td>
            <label v-for="key in MODULE_KEYS" :key="key" class="toggle-row">
              <input
                type="checkbox"
                :checked="!!c.modules[key]"
                :disabled="busyId === c.id"
                @change="toggleModule(c, key)"
              />
              <span>{{ MODULE_LABELS[key] }}</span>
            </label>
          </td>
          <td>
            <div v-if="bindingsFor(c.id).length" class="binding-list">
              <div v-for="b in bindingsFor(c.id)" :key="b.id" class="binding-row">
                <span>{{ botLabel(b.bot_id) }}</span>
                <span class="badge" :class="statusClass(b.status === 'ready' ? 'verified' : 'warning')">
                  {{ b.status_label }}
                </span>
                <button :disabled="busyId === c.id" @click="checkBinding(b)">Проверить права</button>
                <button class="danger" :disabled="busyId === c.id" @click="removeBinding(b)">
                  Отключить
                </button>
              </div>
            </div>
            <div v-else class="muted">Бот не подключён</div>

            <div class="binding-add">
              <select v-model="bindForm[c.id]">
                <option value="">— выбрать бота —</option>
                <option v-for="bot in bots" :key="bot.id" :value="bot.id">
                  {{ bot.username ? '@' + bot.username : bot.title || bot.id }}
                </option>
              </select>
              <button :disabled="busyId === c.id || !bindForm[c.id]" @click="connectBot(c)">
                Подключить бота
              </button>
            </div>

            <div v-if="capabilities[c.id]" class="muted">
              Реакции канала: {{ capabilities[c.id].available.join(' ') || 'нет данных' }}
            </div>
            <button :disabled="busyId === c.id" @click="probeCapabilities(c)">
              Проверить реакции
            </button>
          </td>
          <td>
            <div class="actions">
              <button :disabled="busyId === c.id" @click="verify(c)">Проверить</button>
              <button
                v-if="!c.is_default"
                :disabled="busyId === c.id"
                @click="makeDefault(c)"
              >
                Сделать основным
              </button>
              <button class="danger" :disabled="busyId === c.id" @click="remove(c)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <p v-if="!anyDefault && channels.length > 0" class="inline-note">
      Основной канал не выбран. Нажмите «Сделать основным» у нужного канала.
    </p>
  </div>
</template>

<style scoped>
.binding-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
}
.binding-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.binding-add {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-bottom: 0.4rem;
}
.badge {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
}
</style>
