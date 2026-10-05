<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type Binding,
  type Bot,
  type BotSummary,
  type Channel,
  type ManagedBotPreview,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const bots = ref<Bot[]>([])
const summary = ref<BotSummary | null>(null)
const channels = ref<Channel[]>([])
const bindings = ref<Binding[]>([])
const loading = ref(true)
const busyId = ref('')
const error = ref('')
const notice = ref('')

// Add-bot form
const showAdd = ref(false)
const token = ref('')
const kind = ref('ordinary')
const addBusy = ref(false)

// Managed-bots workflow
const showManaged = ref(false)
const managedUsername = ref('')
const managedName = ref('')
const managedPreview = ref<ManagedBotPreview | null>(null)
const managedRegistration = ref({ user_id: '', username: '', title: '' })

// Which channel to connect a managed bot to (bot id → channel id).
const bindChannel = ref<Record<string, string>>({})

const kindLabel = (k: string) =>
  k === 'manager' ? 'Управляющий' : k === 'managed' ? 'Управляемый' : 'Обычный'

const healthLabel = (h: string) =>
  h === 'ok' ? 'Работает' : h === 'warning' ? 'Нужно внимание' : h === 'error' ? 'Ошибка' : 'Не проверялся'

const healthClass = (h: string) =>
  h === 'ok' ? 'status-ok' : h === 'warning' ? 'status-warning' : h === 'error' ? 'status-error' : 'status-unknown'

//: Plain-language explanation of every bot type (product requirement).
const botTypes = [
  {
    kind: 'manager',
    title: 'Управляющий бот',
    what: 'Главный бот системы. Через него вы управляете Suite из Telegram.',
    why: 'Связывает приложение с вашим Telegram, чтобы отдавать команды и видеть статус.',
    can: [
      'Принимает команды владельца',
      'Показывает состояние системы',
      'Создаёт управляемых ботов (официальный режим Telegram)',
    ],
    cannot: ['Не ставит реакции в канале за вас', 'Не выполняет массовые приглашения'],
    addToChannel: 'Добавлять в канал не нужно — он работает в личном чате с вами.',
  },
  {
    kind: 'managed',
    title: 'Управляемый бот',
    what: 'Бот, которого Suite создаёт и которым управляет для автоматических действий.',
    why: 'Используется Suite для выполнения автоматических действий, например реакций.',
    can: [
      'Ставить реакции на сообщения канала',
      'Выполнять другие автоматические действия, если есть права',
    ],
    cannot: ['Не работает, пока не добавлен в канал', 'Не может нарушить ограничения Telegram'],
    addToChannel:
      'Чтобы он мог реагировать на сообщения канала, его необходимо подключить к этому каналу и проверить права.',
  },
  {
    kind: 'ordinary',
    title: 'Обычный бот',
    what: 'Отдельный бот, которого вы добавили сами и используете для реакций.',
    why: 'Позволяет ставить реакции от имени нескольких ботов без личного аккаунта.',
    can: ['Ставить реакции в подключённых каналах', 'Работать без вашего аккаунта'],
    cannot: ['Не управляет системой', 'Не приглашает участников'],
    addToChannel:
      'Его нужно добавить в канал и дать право ставить реакции — так же, как управляемого бота.',
  },
]

function bindingsForBot(botId: string): Binding[] {
  return bindings.value.filter((b) => b.bot_id === botId)
}

function botChannelStatus(bot: Bot): { label: string; cls: string } {
  if (bot.kind === 'manager') return { label: 'Не требуется', cls: 'status-unknown' }
  if (bot.kind === 'managed' && !bot.has_token) return { label: 'Недоступен', cls: 'status-unknown' }
  const bs = bindingsForBot(bot.id)
  if (!bs.length) return { label: 'Не подключён', cls: 'status-unknown' }
  if (bs.some((b) => b.status === 'ready')) return { label: 'Готов', cls: 'status-ok' }
  if (bs.some((b) => b.status === 'needs_permission')) return { label: 'Нужны права', cls: 'status-warning' }
  if (bs.some((b) => b.status === 'error')) return { label: 'Ошибка', cls: 'status-error' }
  if (bs.some((b) => b.status === 'connected')) return { label: 'Подключён', cls: 'status-ok' }
  return { label: 'Не подключён', cls: 'status-unknown' }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    bots.value = await api.bots()
    summary.value = await api.botsSummary()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось загрузить список ботов.'
  } finally {
    loading.value = false
  }
  // Channels and bindings are best-effort: their absence must not break the page.
  try {
    const [channelList, bindingList] = await Promise.all([api.channels(), api.bindings()])
    channels.value = channelList.items
    bindings.value = bindingList.items
  } catch {
    channels.value = []
    bindings.value = []
  }
}

async function connectToChannel(bot: Bot) {
  const channelId = bindChannel.value[bot.id]
  if (!channelId) {
    error.value = 'Выберите канал для подключения бота.'
    return
  }
  busyId.value = bot.id
  error.value = ''
  notice.value = ''
  try {
    const binding = await api.connectBinding({ bot_id: bot.id, channel_id: channelId })
    notice.value = binding.invite_link
      ? `Бот добавлен в приложение. Откройте Telegram и добавьте его в канал: ${binding.invite_link}`
      : 'Бот добавлен в приложение. Добавьте его в канал и нажмите «Проверить».'
    bindChannel.value[bot.id] = ''
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

async function checkBotBinding(bot: Bot) {
  const bs = bindingsForBot(bot.id)
  if (!bs.length) return
  busyId.value = bot.id
  error.value = ''
  notice.value = ''
  try {
    const results = await Promise.all(bs.map((b) => api.checkBinding(b.id)))
    notice.value = results.map((r) => r.message).join(' ')
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

function friendlyError(e: unknown): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || 'Произошла ошибка.'
}

async function submitAdd() {
  addBusy.value = true
  error.value = ''
  try {
    await api.addBot({ token: token.value, kind: kind.value })
    token.value = ''
    showAdd.value = false
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    addBusy.value = false
  }
}

async function withBot(id: string, fn: () => Promise<unknown>) {
  busyId.value = id
  error.value = ''
  try {
    await fn()
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    busyId.value = ''
  }
}

const check = (b: Bot) => withBot(b.id, () => api.checkBot(b.id))
const toggle = (b: Bot) => withBot(b.id, () => (b.enabled ? api.disableBot(b.id) : api.enableBot(b.id)))
const remove = (b: Bot) => {
  if (!confirm(`Удалить бота @${b.username || b.telegram_id} из конфигурации?`)) return
  return withBot(b.id, () => api.removeBot(b.id))
}

async function previewManaged() {
  error.value = ''
  try {
    managedPreview.value = await api.managedPreview(managedUsername.value, managedName.value)
  } catch (e) {
    error.value = friendlyError(e)
  }
}

async function registerManaged() {
  error.value = ''
  try {
    await api.registerManagedBot({
      user_id: Number(managedRegistration.value.user_id),
      username: managedRegistration.value.username,
      title: managedRegistration.value.title,
    })
    managedRegistration.value = { user_id: '', username: '', title: '' }
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Боты <InfoHint topic="managed_bot" /></h2>
    <p class="page-subtitle">
      Здесь собраны все боты: управляющий, управляемые и обычные. Секретные токены
      хранятся в зашифрованном виде и никогда не показываются.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div v-if="summary" class="grid">
      <div class="card">
        <div>
          <span class="status-dot" :class="healthClass(summary.manager_health)"></span>
          <strong>Управляющий бот</strong>
        </div>
        <p v-if="summary.manager_connected">@{{ summary.manager_username }} · {{ healthLabel(summary.manager_health) }}</p>
        <p v-else class="muted">
          Ещё не подключён. Создайте бота в @BotFather и добавьте его токен ниже.
        </p>
      </div>
      <div class="card">
        <strong>Всего ботов</strong>
        <p class="muted">
          Управляющих: {{ summary.by_kind['manager'] ?? 0 }} ·
          Управляемых: {{ summary.by_kind['managed'] ?? 0 }} ·
          Обычных: {{ summary.by_kind['ordinary'] ?? 0 }}
        </p>
      </div>
    </div>

    <h3>Какие бывают боты</h3>
    <div class="grid">
      <div v-for="t in botTypes" :key="t.kind" class="card">
        <strong>{{ t.title }}</strong>
        <p><b>Что это?</b> {{ t.what }}</p>
        <p><b>Зачем нужен?</b> {{ t.why }}</p>
        <p><b>Что умеет:</b></p>
        <ul class="muted">
          <li v-for="c in t.can" :key="c">{{ c }}</li>
        </ul>
        <p><b>Чего не может:</b></p>
        <ul class="muted">
          <li v-for="c in t.cannot" :key="c">{{ c }}</li>
        </ul>
        <p class="inline-note">{{ t.addToChannel }}</p>
      </div>
    </div>

    <div class="toolbar">
      <button class="primary" @click="showAdd = !showAdd">
        {{ showAdd ? 'Отмена' : '+ Добавить бота' }}
      </button>
      <button @click="showManaged = !showManaged">
        {{ showManaged ? 'Скрыть управляемых ботов' : 'Управляемые боты' }}
      </button>
      <button @click="load">Обновить</button>
    </div>

    <div v-if="showAdd" class="card">
      <h3>Подключение бота</h3>
      <p class="muted">
        Откройте @BotFather в Telegram → /newbot → скопируйте токен. Токен нужен
        только для проверки: в системе он сохраняется в зашифрованном виде.
      </p>
      <label class="field">
        <span>Токен бота</span>
        <input v-model="token" type="password" placeholder="123456:ABC-DEF..." autocomplete="off" />
      </label>
      <label class="field">
        <span>Тип бота</span>
        <select v-model="kind">
          <option value="manager">Управляющий (главный бот системы)</option>
          <option value="ordinary">Обычный</option>
        </select>
      </label>
      <button class="primary" :disabled="addBusy || !token" @click="submitAdd">
        {{ addBusy ? 'Проверяем…' : 'Проверить и добавить' }}
      </button>
    </div>

    <div v-if="showManaged" class="card">
      <h3>Создание управляемого бота (официальный способ Telegram)</h3>
      <p class="muted">
        Telegram позволяет управляющему боту создавать дочерние боты. В @BotFather
        у управляющего бота включите «Bot Management Mode». Затем сформируйте ссылку,
        откройте её в Telegram и подтвердите создание. Токен можно запросить кнопкой
        «Получить токен».
      </p>
      <label class="field">
        <span>@username нового бота</span>
        <input v-model="managedUsername" placeholder="my_new_bot" />
      </label>
      <label class="field">
        <span>Отображаемое имя (необязательно)</span>
        <input v-model="managedName" placeholder="Мой новый бот" />
      </label>
      <button :disabled="!managedUsername" @click="previewManaged">Сформировать ссылку</button>

      <div v-if="managedPreview" class="inline-note">
        <p>{{ managedPreview.instructions }}</p>
        <p><a :href="managedPreview.create_link" target="_blank" rel="noopener">{{ managedPreview.create_link }}</a></p>
      </div>

      <h4>Уже созданный бот</h4>
      <p class="muted">Если бот создан, укажите его Telegram ID, чтобы запросить токен.</p>
      <label class="field">
        <span>Telegram ID управляемого бота</span>
        <input v-model="managedRegistration.user_id" placeholder="123456789" />
      </label>
      <label class="field">
        <span>@username (необязательно)</span>
        <input v-model="managedRegistration.username" placeholder="my_new_bot" />
      </label>
      <button :disabled="!managedRegistration.user_id" @click="registerManaged">Зарегистрировать</button>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="bots.length === 0" class="card empty">
      Пока нет ни одного бота. Нажмите «+ Добавить бота», чтобы подключить управляющего бота.
    </div>
    <table v-else>
      <thead>
        <tr>
          <th>Бот</th>
          <th>Тип</th>
          <th>Статус</th>
          <th>Канал</th>
          <th>Последняя проверка</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="bot in bots" :key="bot.id">
          <td>
            <strong>{{ bot.username ? '@' + bot.username : bot.title || '—' }}</strong>
            <div class="muted">ID: {{ bot.telegram_id ?? '—' }}<span v-if="!bot.has_token"> · нет токена</span></div>
          </td>
          <td>{{ kindLabel(bot.kind) }}</td>
          <td>
            <span class="status-dot" :class="healthClass(bot.health)"></span>
            {{ healthLabel(bot.health) }}
            <span v-if="!bot.enabled" class="badge warning">выключен</span>
            <div v-if="bot.health_message" class="muted">{{ bot.health_message }}</div>
            <div v-if="bot.health_hint" class="muted">{{ bot.health_hint }}</div>
          </td>
          <td>
            <template v-if="bot.kind !== 'manager'">
              <span class="status-dot" :class="botChannelStatus(bot).cls"></span>
              {{ botChannelStatus(bot).label }}
              <div v-if="bindingsForBot(bot.id).length" class="muted">
                {{ bindingsForBot(bot.id).map((b) => b.channel_label).join(', ') }}
              </div>
              <div class="actions" style="margin-top: 0.4rem">
                <select v-model="bindChannel[bot.id]">
                  <option value="">— выберите канал —</option>
                  <option v-for="c in channels" :key="c.id" :value="c.id">
                    {{ c.title || c.username || c.reference }}
                  </option>
                </select>
                <button
                  :disabled="busyId === bot.id || !bindChannel[bot.id]"
                  @click="connectToChannel(bot)"
                >
                  Подключить к каналу
                </button>
                <button
                  v-if="bindingsForBot(bot.id).length"
                  :disabled="busyId === bot.id"
                  @click="checkBotBinding(bot)"
                >
                  Проверить
                </button>
              </div>
              <div v-if="bot.kind === 'managed'" class="muted">
                Чтобы он мог реагировать на сообщения канала, его необходимо подключить
                к этому каналу и проверить права.
              </div>
            </template>
            <span v-else class="muted">Не требуется</span>
          </td>
          <td class="muted">{{ bot.last_health_at ? new Date(bot.last_health_at).toLocaleString() : '—' }}</td>
          <td>
            <div class="actions">
              <button :disabled="busyId === bot.id" @click="check(bot)">Проверить</button>
              <button :disabled="busyId === bot.id" @click="toggle(bot)">
                {{ bot.enabled ? 'Выключить' : 'Включить' }}
              </button>
              <button
                v-if="bot.kind === 'managed' && !bot.has_token"
                :disabled="busyId === bot.id"
                @click="withBot(bot.id, () => api.fetchManagedToken(bot.id))"
              >
                Получить токен
              </button>
              <button class="danger" :disabled="busyId === bot.id" @click="remove(bot)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
