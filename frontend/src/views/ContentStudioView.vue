<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  ApiError,
  type Channel,
  type ContentCalendar,
  type ContentDashboard,
  type ContentItem,
  type ContentPreview,
  type ContentProviderStatus,
  type ContentPublication,
  type ContentSource,
  type ContentValidation,
  type GrabResult,
  type RightsInfo,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const tab = ref<'overview' | 'sources' | 'items' | 'calendar'>('overview')
const loading = ref(true)
const error = ref('')
const notice = ref('')

const providers = ref<ContentProviderStatus[]>([])
const dashboard = ref<ContentDashboard | null>(null)
const sources = ref<ContentSource[]>([])
const channels = ref<Channel[]>([])
const items = ref<ContentItem[]>([])
const calendar = ref<ContentCalendar | null>(null)

// Add-source form
const showAdd = ref(false)
const addBusy = ref(false)
const form = ref({
  kind: 'manual',
  reference: '',
  title: '',
  channel_id: '',
})

// Item workspace
const selected = ref<ContentItem | null>(null)
const cleanPreview = ref<{ original: string; cleaned: string; changed: boolean; removed_lines: number } | null>(null)
const rights = ref<RightsInfo | null>(null)
const validation = ref<ContentValidation | null>(null)
const preview = ref<ContentPreview | null>(null)
const publications = ref<ContentPublication[]>([])
const planChannel = ref('')
const planWhen = ref('')
const planBusy = ref(false)

const KIND_TITLES: Record<string, string> = {
  telegram: 'Telegram-канал',
  rss: 'RSS-лента',
  atom: 'Atom-лента',
  manual: 'Вручную',
}

const STATUS_CLASS: Record<string, string> = {
  ready: 'ok',
  published: 'ok',
  planned: 'warning',
  scheduled: 'warning',
  publishing: 'warning',
  draft: 'warning',
  imported: 'warning',
  failed: 'error',
  error: 'error',
  archived: 'badge-muted',
}

function friendly(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.hint ? `${e.message} ${e.hint}` : e.message
  return e instanceof Error ? e.message : fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [prov, dash, src] = await Promise.all([
      api.contentProviders(),
      api.contentDashboard(),
      api.contentSources(),
    ])
    providers.value = prov
    dashboard.value = dash
    sources.value = src.items
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить Content Studio.')
  } finally {
    loading.value = false
  }
  try {
    channels.value = (await api.channels()).items
  } catch {
    channels.value = []
  }
}

async function loadItems() {
  try {
    const list = await api.contentItems({ limit: '200' })
    items.value = list.items
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить материалы.')
  }
}

async function loadCalendar() {
  try {
    calendar.value = await api.contentCalendar()
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить календарь.')
  }
}

async function submitAdd() {
  addBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.addContentSource({
      kind: form.value.kind,
      reference: form.value.reference,
      title: form.value.title,
      channel_id: form.value.channel_id,
    })
    form.value = { kind: 'manual', reference: '', title: '', channel_id: '' }
    showAdd.value = false
    notice.value = 'Источник добавлен. Нажмите «Собрать материалы», чтобы забрать контент.'
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось добавить источник.')
  } finally {
    addBusy.value = false
  }
}

async function grab(source: ContentSource) {
  error.value = ''
  notice.value = ''
  try {
    const result: GrabResult = await api.grabContentSource(source.id)
    const parts = [`Новых: ${result.new_items}`, `Повторов: ${result.duplicates}`]
    if (result.blocked) parts.push(`Отфильтровано: ${result.blocked}`)
    if (result.held) parts.push(`Удержано модерацией: ${result.held}`)
    notice.value = `${result.message} (${parts.join(', ')})`
    if (result.protected) {
      notice.value += ' Материал защищён от копирования — сохранена только ссылка.'
    }
    await Promise.all([load(), loadItems()])
  } catch (e) {
    error.value = friendly(e, 'Не удалось собрать материалы.')
  }
}

async function removeSource(source: ContentSource) {
  if (!confirm(`Удалить источник «${source.title || source.reference}»?`)) return
  try {
    await api.removeContentSource(source.id)
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось удалить источник.')
  }
}

async function openItem(item: ContentItem) {
  error.value = ''
  notice.value = ''
  selected.value = item
  cleanPreview.value = null
  validation.value = null
  preview.value = null
  planChannel.value = channels.value[0]?.id ?? ''
  planWhen.value = ''
  try {
    const [r, pubs] = await Promise.all([
      api.contentRights(item.id),
      api.contentPublications(item.id),
    ])
    rights.value = r
    publications.value = pubs.publications
  } catch (e) {
    error.value = friendly(e, 'Не удалось открыть материал.')
  }
}

async function previewClean() {
  if (!selected.value) return
  try {
    cleanPreview.value = await api.contentCleanPreview(selected.value.id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось показать очистку.')
  }
}

async function applyClean() {
  if (!selected.value) return
  try {
    selected.value = await api.applyContentClean(selected.value.id)
    cleanPreview.value = null
    notice.value = 'Очистка применена. Её можно отменить.'
    await loadItems()
  } catch (e) {
    error.value = friendly(e, 'Не удалось применить очистку.')
  }
}

async function revertClean() {
  if (!selected.value) return
  try {
    selected.value = await api.revertContentClean(selected.value.id)
    notice.value = 'Очистка отменена.'
    await loadItems()
  } catch (e) {
    error.value = friendly(e, 'Не удалось отменить очистку.')
  }
}

async function checkMarkup() {
  if (!selected.value) return
  try {
    validation.value = await api.contentValidate(selected.value.id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось проверить разметку.')
  }
}

async function showPreview() {
  if (!selected.value) return
  try {
    preview.value = await api.contentPreview(selected.value.id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось построить предпросмотр.')
  }
}

async function plan() {
  if (!selected.value || !planChannel.value) {
    error.value = 'Выберите канал для публикации.'
    return
  }
  planBusy.value = true
  error.value = ''
  try {
    const payload = {
      targets: [
        {
          channel_id: planChannel.value,
          ...(planWhen.value ? { scheduled_at: new Date(planWhen.value).toISOString() } : {}),
        },
      ],
    }
    const result = await api.planContent(selected.value.id, payload)
    publications.value = result.publications
    notice.value = planWhen.value
      ? 'Публикация запланирована. Она выйдет в назначенное время.'
      : 'Публикация подготовлена. Нажмите «Опубликовать сейчас», чтобы отправить её.'
    await loadCalendar()
  } catch (e) {
    error.value = friendly(e, 'Не удалось запланировать публикацию.')
  } finally {
    planBusy.value = false
  }
}

async function publish(pub: ContentPublication) {
  error.value = ''
  notice.value = ''
  try {
    const result = await api.publishContentPublication(pub.id)
    notice.value = result.ok ? result.message : `${result.message} ${result.how_to_fix}`
    await refreshPublications()
  } catch (e) {
    error.value = friendly(e, 'Не удалось опубликовать.')
  }
}

async function cancel(pub: ContentPublication) {
  try {
    await api.cancelContentPublication(pub.id)
    notice.value = 'Публикация отменена.'
    await refreshPublications()
  } catch (e) {
    error.value = friendly(e, 'Не удалось отменить публикацию.')
  }
}

async function refreshPublications() {
  if (!selected.value) return
  const pubs = await api.contentPublications(selected.value.id)
  publications.value = pubs.publications
  await Promise.all([loadItems(), loadCalendar()])
}

const selectedText = computed(() =>
  selected.value ? selected.value.cleaned_text || selected.value.text : '',
)

onMounted(async () => {
  await load()
  await Promise.all([loadItems(), loadCalendar()])
})
</script>

<template>
  <div>
    <h2 class="page-title">Content Studio <InfoHint topic="content_studio" /></h2>
    <p class="page-subtitle">
      Собирайте материалы из источников, очищайте их, проверяйте права и разметку и
      публикуйте в свои каналы. Материал никогда не публикуется без вашего подтверждения.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div class="toolbar">
      <button :class="{ primary: tab === 'overview' }" @click="tab = 'overview'">Обзор</button>
      <button :class="{ primary: tab === 'sources' }" @click="tab = 'sources'">Источники</button>
      <button :class="{ primary: tab === 'items' }" @click="tab = 'items'">Материалы</button>
      <button :class="{ primary: tab === 'calendar' }" @click="tab = 'calendar'">Календарь</button>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>

    <!-- Overview -->
    <template v-else-if="tab === 'overview'">
      <div v-if="dashboard" class="grid">
        <div class="card">
          <strong>Черновики</strong>
          <p>{{ dashboard.drafts }}</p>
          <p class="muted">Материалы, которые вы ещё готовите.</p>
        </div>
        <div class="card">
          <strong>Готовы к публикации</strong>
          <p>{{ dashboard.ready }}</p>
          <p class="muted">Проверены и ждут отправки.</p>
        </div>
        <div class="card">
          <strong>Запланировано</strong>
          <p>{{ dashboard.scheduled }}</p>
          <p class="muted">Выйдут автоматически в назначенное время.</p>
        </div>
        <div class="card">
          <strong>Опубликовано сегодня</strong>
          <p>{{ dashboard.published_today }}</p>
          <p class="muted">Успешные публикации за сутки.</p>
        </div>
        <div class="card">
          <strong>Импортировано</strong>
          <p>{{ dashboard.imported }}</p>
          <p class="muted">Забрано из источников и ещё не обработано.</p>
        </div>
        <div class="card">
          <strong :class="{ 'error-text': dashboard.failed > 0 }">Ошибки</strong>
          <p>{{ dashboard.failed }}</p>
          <p class="muted">Требуют внимания.</p>
        </div>
      </div>

      <div class="card">
        <h3>Доступные источники</h3>
        <p class="muted">
          Telegram-канал требует подключённого аккаунта. RSS, Atom и ручной ввод работают
          без аккаунта.
        </p>
        <table>
          <thead>
            <tr><th>Тип</th><th>Состояние</th><th>Пояснение</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in providers" :key="p.kind">
              <td>{{ p.title }}</td>
              <td>
                <span class="badge" :class="p.available ? 'ok' : 'warning'">
                  {{ p.available ? 'Доступен' : 'Недоступен' }}
                </span>
              </td>
              <td class="muted">
                {{ p.message || (p.requires_account ? 'Нужен подключённый аккаунт.' : 'Работает без аккаунта.') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Sources -->
    <template v-else-if="tab === 'sources'">
      <div class="toolbar">
        <button class="primary" @click="showAdd = !showAdd">Добавить источник</button>
      </div>

      <div v-if="showAdd" class="card">
        <label class="field">
          <span>Тип источника</span>
          <select v-model="form.kind">
            <option value="manual">Вручную (текст)</option>
            <option value="rss">RSS-лента</option>
            <option value="atom">Atom-лента</option>
            <option value="telegram">Telegram-канал (нужен аккаунт)</option>
          </select>
        </label>
        <label class="field">
          <span>Ссылка или текст</span>
          <input v-model="form.reference" placeholder="https://example.com/rss или текст" />
        </label>
        <label class="field">
          <span>Название (необязательно)</span>
          <input v-model="form.title" placeholder="Например: Новости" />
        </label>
        <label v-if="form.kind === 'telegram'" class="field">
          <span>Канал в реестре</span>
          <select v-model="form.channel_id">
            <option value="">— выберите канал —</option>
            <option v-for="c in channels" :key="c.id" :value="c.id">
              {{ c.title || c.reference }}
            </option>
          </select>
        </label>
        <button class="primary" :disabled="addBusy || !form.reference" @click="submitAdd">
          Добавить
        </button>
      </div>

      <div v-if="!sources.length" class="card empty">
        Пока нет источников. Добавьте первый — вручную, RSS или Atom.
      </div>

      <div v-for="s in sources" :key="s.id" class="card">
        <div class="row-between">
          <div>
            <strong>{{ s.title || s.reference }}</strong>
            <span class="badge badge-muted">{{ s.kind_title || KIND_TITLES[s.kind] || s.kind }}</span>
            <p class="muted">{{ s.reference }}</p>
          </div>
          <div class="actions">
            <button class="primary" @click="grab(s)">Собрать материалы</button>
            <button class="danger" @click="removeSource(s)">Удалить</button>
          </div>
        </div>
        <p class="muted">
          Состояние: {{ s.status_title }} ·
          новых за последний сбор: {{ s.last_fetch_new }}
          <span v-if="s.last_error"> · ошибка: {{ s.last_error }}</span>
        </p>
        <p v-if="s.blocked_keywords.length" class="muted">
          Фильтр слов: {{ s.blocked_keywords.join(', ') }}
        </p>
        <p v-if="s.quiet_hours_enabled" class="muted">
          Тихие часы: {{ s.quiet_hours_start }}:00–{{ s.quiet_hours_end }}:00 ({{ s.quiet_hours_tz }})
        </p>
      </div>
    </template>

    <!-- Items -->
    <template v-else-if="tab === 'items'">
      <div class="card">
        <h3>Материалы</h3>
        <div v-if="!items.length" class="empty">
          Материалов пока нет. Соберите их на вкладке «Источники».
        </div>
        <table v-else>
          <thead>
            <tr><th>Заголовок</th><th>Статус</th><th>Права</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="i in items" :key="i.id">
              <td>{{ i.title || i.text.slice(0, 60) }}</td>
              <td>
                <span class="badge" :class="STATUS_CLASS[i.status] || 'badge-muted'">
                  {{ i.status_title }}
                </span>
                <span v-if="i.held" class="badge warning">Удержано</span>
              </td>
              <td class="muted">{{ i.rights_title }}</td>
              <td><button @click="openItem(i)">Открыть</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="selected" class="card">
        <div class="row-between">
          <h3>Редактор: {{ selected.title || 'без названия' }}</h3>
          <span class="badge" :class="STATUS_CLASS[selected.status] || 'badge-muted'">
            {{ selected.status_title }}
          </span>
        </div>

        <div v-if="rights && rights.warning" class="inline-note warning-text">
          {{ rights.warning }}
        </div>

        <h4>Текст</h4>
        <div class="inline-note">{{ selectedText }}</div>

        <div class="toolbar">
          <button @click="previewClean">Показать очистку</button>
          <button @click="applyClean">Применить очистку</button>
          <button @click="revertClean">Отменить очистку</button>
          <button @click="checkMarkup">Проверить разметку</button>
          <button @click="showPreview">Предпросмотр</button>
        </div>

        <div v-if="cleanPreview" class="inline-note">
          <strong>После очистки</strong> (удалено строк: {{ cleanPreview.removed_lines }})
          <p>{{ cleanPreview.cleaned }}</p>
          <p v-if="!cleanPreview.changed" class="muted">Менять нечего.</p>
        </div>

        <div v-if="validation" class="inline-note">
          <strong v-if="validation.ok" class="success-text">Разметка в порядке.</strong>
          <strong v-else class="error-text">{{ validation.first_error }}</strong>
          <ul v-if="validation.issues.length">
            <li v-for="(issue, idx) in validation.issues" :key="idx">
              {{ issue.message }}<span v-if="issue.line"> (строка {{ issue.line }})</span>
            </li>
          </ul>
          <ul v-if="validation.button_problems.length">
            <li v-for="(p, idx) in validation.button_problems" :key="idx" class="error-text">{{ p }}</li>
          </ul>
        </div>

        <div v-if="preview" class="inline-note">
          <strong>Предпросмотр ({{ preview.char_count }} символов)</strong>
          <p>{{ preview.text }}</p>
          <p v-if="preview.buttons.length" class="muted">
            Кнопки:
            <span v-for="(row, ri) in preview.buttons" :key="ri">
              {{ row.map((b) => b.text).join(' | ') }}
            </span>
          </p>
          <p class="muted">{{ preview.notice }}</p>
        </div>

        <h4>Публикация</h4>
        <label class="field">
          <span>Канал</span>
          <select v-model="planChannel">
            <option value="">— выберите канал —</option>
            <option v-for="c in channels" :key="c.id" :value="c.id">
              {{ c.title || c.reference }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Время (необязательно)</span>
          <input v-model="planWhen" type="datetime-local" />
        </label>
        <button class="primary" :disabled="planBusy" @click="plan">
          {{ planWhen ? 'Запланировать' : 'Подготовить публикацию' }}
        </button>

        <div v-if="publications.length">
          <h4>Публикации</h4>
          <table>
            <thead>
              <tr><th>Канал</th><th>Статус</th><th>Время</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="pub in publications" :key="pub.id">
                <td>{{ pub.channel_username || pub.channel_id }}</td>
                <td>
                  <span class="badge" :class="STATUS_CLASS[pub.status] || 'badge-muted'">
                    {{ pub.status_title }}
                  </span>
                  <span v-if="pub.error" class="error-text"> {{ pub.error }}</span>
                </td>
                <td class="muted">{{ pub.scheduled_at || pub.published_at || '—' }}</td>
                <td class="actions">
                  <button
                    v-if="pub.status === 'planned' || pub.status === 'scheduled'"
                    class="primary"
                    @click="publish(pub)"
                  >
                    Опубликовать сейчас
                  </button>
                  <button
                    v-if="pub.status === 'planned' || pub.status === 'scheduled'"
                    @click="cancel(pub)"
                  >
                    Отменить
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Calendar -->
    <template v-else-if="tab === 'calendar'">
      <div class="card">
        <h3>Календарь публикаций</h3>
        <p class="muted">
          {{ calendar?.start?.slice(0, 10) }} — {{ calendar?.end?.slice(0, 10) }}
        </p>
        <div v-if="!calendar || !calendar.entries.length" class="empty">
          На ближайшие дни публикаций нет.
        </div>
        <table v-else>
          <thead>
            <tr><th>Когда</th><th>Канал</th><th>Материал</th><th>Статус</th></tr>
          </thead>
          <tbody>
            <tr v-for="e in calendar.entries" :key="e.publication_id">
              <td>{{ e.scheduled_at || e.published_at }}</td>
              <td>{{ e.channel_title || e.channel_id }}</td>
              <td>{{ e.title || e.item_id }}</td>
              <td>
                <span class="badge" :class="STATUS_CLASS[e.status] || 'badge-muted'">
                  {{ e.status_title }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
