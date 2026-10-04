<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type AudienceSource,
  type AudienceTag,
  type AudienceUser,
  type AudienceUserDetail,
  type ExportPreview,
  type FilterPreset,
  type ImportResult,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const users = ref<AudienceUser[]>([])
const total = ref(0)
const sources = ref<AudienceSource[]>([])
const tags = ref<AudienceTag[]>([])
const presets = ref<FilterPreset[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')

// Filters
const search = ref('')
const sourceId = ref('')
const tagFilter = ref('')
const statusFilter = ref('')
const hasUsername = ref(false)
const isPremium = ref(false)
const activePreset = ref('')
const sort = ref('last_seen')
const order = ref('desc')

// Pagination
const limit = ref(50)
const page = ref(0)

// Selection + bulk
const selected = ref<string[]>([])

// Detail
const detail = ref<AudienceUserDetail | null>(null)

// Tag manager
const showTags = ref(false)
const tagBusy = ref(false)

// Export / import
const showExport = ref(false)
const showImport = ref(false)
const exportForm = ref({ format: 'csv', include_pii: false, limit: 0, source_id: '', tag: '' })
const exportPreview = ref<ExportPreview | null>(null)
const exportBusy = ref(false)
const importForm = ref({ data: '', format: 'csv', source_id: '' })
const importBusy = ref(false)
const importResult = ref<ImportResult | null>(null)

const STATUS_LABELS: Record<string, string> = {
  active: 'Активный',
  inactive: 'Неактивный',
  deleted: 'Удалён',
  blocked: 'Заблокирован',
  unknown: 'Неизвестно',
}

const INVITE_LABELS: Record<string, string> = {
  '': '—',
  pending: 'Ожидает',
  invited: 'Приглашён',
  already_member: 'Уже в канале',
  privacy: 'Приватность',
  flood_wait: 'Ожидание',
  failed: 'Ошибка',
}

const SORT_LABELS: Record<string, string> = {
  last_seen: 'По последней активности',
  first_seen: 'По первой находке',
  username: 'По username',
  score: 'По оценке',
  created: 'По дате добавления',
  telegram_id: 'По Telegram ID',
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)))

function friendlyError(e: unknown): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || 'Произошла ошибка.'
}

function buildParams(): Record<string, string> {
  const p: Record<string, string> = {
    sort: sort.value,
    order: order.value,
    limit: String(limit.value),
    offset: String(page.value * limit.value),
  }
  if (search.value) p.search = search.value
  if (sourceId.value) p.source_id = sourceId.value
  if (tagFilter.value) p.tag = tagFilter.value
  if (statusFilter.value) p.status = statusFilter.value
  if (hasUsername.value) p.has_username = 'true'
  if (isPremium.value) p.is_premium = 'true'
  return p
}

async function load(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const data = await api.audienceUsers(buildParams())
    users.value = data.items
    total.value = data.total
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  try {
    const [src, tg, pr] = await Promise.all([
      api.audienceSources({ limit: '200' }),
      api.audienceTags(),
      api.audienceFilterPresets(),
    ])
    sources.value = src.items
    tags.value = tg
    presets.value = pr
  } catch (e) {
    error.value = friendlyError(e)
  }
}

function applyFilters() {
  page.value = 0
  load()
}

function resetFilters() {
  search.value = ''
  sourceId.value = ''
  tagFilter.value = ''
  statusFilter.value = ''
  hasUsername.value = false
  isPremium.value = false
  activePreset.value = ''
  sort.value = 'last_seen'
  order.value = 'desc'
  page.value = 0
  load()
}

function applyPreset(preset: FilterPreset) {
  resetFilters()
  activePreset.value = preset.key
  const f = preset.filters as Record<string, unknown>
  if (f.is_bot === false && f.is_deleted === false) {
    statusFilter.value = 'active'
  }
  if (f.has_username === true) hasUsername.value = true
  if (f.is_premium === true) isPremium.value = true
  load()
}

function goPage(delta: number) {
  const next = page.value + delta
  if (next < 0 || next >= totalPages.value) return
  page.value = next
  load()
}

function toggleSelect(id: string) {
  const i = selected.value.indexOf(id)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(id)
}

const allSelected = computed(
  () => users.value.length > 0 && selected.value.length === users.value.length,
)
function toggleAll() {
  selected.value = allSelected.value ? [] : users.value.map((u) => u.id)
}

async function openDetail(u: AudienceUser) {
  error.value = ''
  try {
    detail.value = await api.audienceUser(u.id)
  } catch (e) {
    error.value = friendlyError(e)
  }
}

async function bulkTag() {
  if (!selected.value.length) return
  const name = prompt('Введите тег для выбранных участников:')
  if (!name) return
  error.value = ''
  try {
    const res = await api.assignTags(selected.value, [name])
    notice.value = `Тег «${name}» добавлен: ${res.updated} записей.`
    selected.value = []
    await Promise.all([load(true), loadMeta()])
  } catch (e) {
    error.value = friendlyError(e)
  }
}

async function bulkStatus(status: string) {
  if (!selected.value.length) return
  error.value = ''
  try {
    const res = await api.bulkUserStatus(selected.value, status)
    notice.value = `Статус обновлён: ${res.updated} записей.`
    selected.value = []
    await load(true)
  } catch (e) {
    error.value = friendlyError(e)
  }
}

async function renameTag(t: AudienceTag) {
  const name = prompt(`Новое имя тега «${t.name}»:`, t.name)
  if (!name || name === t.name) return
  tagBusy.value = true
  try {
    await api.renameTag(t.name, name)
    await Promise.all([loadMeta(), load(true)])
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    tagBusy.value = false
  }
}

async function deleteTag(t: AudienceTag) {
  if (!confirm(`Удалить тег «${t.name}» у всех участников?`)) return
  tagBusy.value = true
  try {
    await api.deleteTag(t.name)
    if (tagFilter.value === t.name) tagFilter.value = ''
    await Promise.all([loadMeta(), load(true)])
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    tagBusy.value = false
  }
}

function exportPayload() {
  return {
    format: exportForm.value.format,
    include_pii: exportForm.value.include_pii,
    limit: Number(exportForm.value.limit) || 0,
    source_id: exportForm.value.source_id || null,
    tag: exportForm.value.tag || null,
  }
}

async function previewExport() {
  exportBusy.value = true
  error.value = ''
  try {
    exportPreview.value = await api.exportPreview(exportPayload())
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    exportBusy.value = false
  }
}

async function runExport() {
  exportBusy.value = true
  error.value = ''
  try {
    const res = await api.exportAudience(exportPayload())
    notice.value = `Файл сохранён: ${res.filename} (${res.row_count} строк). Он лежит локально в папке exports.`
    showExport.value = false
    exportPreview.value = null
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    exportBusy.value = false
  }
}

async function runImport() {
  importBusy.value = true
  error.value = ''
  importResult.value = null
  try {
    importResult.value = await api.importAudience({
      data: importForm.value.data,
      format: importForm.value.format,
      source_id: importForm.value.source_id || null,
    })
    await Promise.all([load(true), loadMeta()])
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    importBusy.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadMeta()])
})
</script>

<template>
  <div>
    <h2 class="page-title">Аудитория <InfoHint topic="audience" /></h2>
    <p class="page-subtitle">
      Здесь хранятся все собранные участники. Используйте поиск, фильтры и теги,
      чтобы отобрать нужную аудиторию для приглашений. База не отправляется наружу:
      экспорт сохраняется локально.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div class="toolbar">
      <RouterLink to="/sources"><button>← Источники</button></RouterLink>
      <button @click="showTags = !showTags">{{ showTags ? 'Скрыть теги' : 'Теги' }}</button>
      <button @click="showExport = !showExport">Экспорт</button>
      <button @click="showImport = !showImport">Импорт</button>
      <button @click="load()">Обновить</button>
    </div>

    <div v-if="presets.length" class="toolbar">
      <button
        v-for="p in presets"
        :key="p.key"
        :class="{ primary: activePreset === p.key }"
        :title="p.description"
        @click="applyPreset(p)"
      >
        {{ p.label }}
      </button>
    </div>

    <!-- Filters -->
    <div class="card">
      <div class="two-cols">
        <label class="field">
          <span>Поиск (имя, @username)</span>
          <input v-model="search" placeholder="Иван или @ivan" @keyup.enter="applyFilters" />
        </label>
        <label class="field">
          <span>Источник</span>
          <select v-model="sourceId">
            <option value="">Все источники</option>
            <option v-for="s in sources" :key="s.id" :value="s.id">
              {{ s.title || s.username || s.reference }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Тег</span>
          <select v-model="tagFilter">
            <option value="">Все теги</option>
            <option v-for="t in tags" :key="t.name" :value="t.name">
              {{ t.name }} ({{ t.count }})
            </option>
          </select>
        </label>
        <label class="field">
          <span>Статус</span>
          <select v-model="statusFilter">
            <option value="">Любой</option>
            <option value="active">Активный</option>
            <option value="inactive">Неактивный</option>
            <option value="deleted">Удалён</option>
            <option value="blocked">Заблокирован</option>
            <option value="unknown">Неизвестно</option>
          </select>
        </label>
        <label class="field">
          <span>Сортировка</span>
          <select v-model="sort">
            <option v-for="(label, key) in SORT_LABELS" :key="key" :value="key">{{ label }}</option>
          </select>
        </label>
        <label class="field">
          <span>Порядок</span>
          <select v-model="order">
            <option value="desc">По убыванию</option>
            <option value="asc">По возрастанию</option>
          </select>
        </label>
      </div>
      <div class="field-inline">
        <label><input v-model="hasUsername" type="checkbox" /> только с @username</label>
        <label><input v-model="isPremium" type="checkbox" /> только Premium</label>
      </div>
      <div class="toolbar">
        <button class="primary" @click="applyFilters">Применить</button>
        <button @click="resetFilters">Сбросить</button>
      </div>
    </div>

    <!-- Bulk actions -->
    <div v-if="selected.length" class="card">
      <div class="row-between">
        <strong>Выбрано: {{ selected.length }}</strong>
        <div class="actions">
          <button @click="bulkTag">Добавить тег</button>
          <button @click="bulkStatus('active')">Пометить активными</button>
          <button @click="bulkStatus('blocked')">Пометить заблокированными</button>
          <button @click="selected = []">Снять выбор</button>
        </div>
      </div>
    </div>

    <!-- Tag manager -->
    <div v-if="showTags" class="card">
      <h3>Теги</h3>
      <p class="muted">Теги помогают группировать участников. Изменения применяются сразу.</p>
      <div v-if="tags.length === 0" class="muted">Тегов пока нет.</div>
      <table v-else class="table">
        <thead>
          <tr><th>Тег</th><th>Участников</th><th>Действия</th></tr>
        </thead>
        <tbody>
          <tr v-for="t in tags" :key="t.name">
            <td>{{ t.name }}</td>
            <td>{{ t.count }}</td>
            <td>
              <div class="actions">
                <button :disabled="tagBusy" @click="renameTag(t)">Переименовать</button>
                <button class="danger" :disabled="tagBusy" @click="deleteTag(t)">Удалить</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Export -->
    <div v-if="showExport" class="card">
      <h3>Экспорт базы</h3>
      <p class="muted">
        Файл сохраняется локально в папку exports и никуда не отправляется. Персональные
        данные (телефон в маскированном виде) включаются только по вашему выбору.
      </p>
      <div class="two-cols">
        <label class="field">
          <span>Формат</span>
          <select v-model="exportForm.format">
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </label>
        <label class="field">
          <span>Источник</span>
          <select v-model="exportForm.source_id">
            <option value="">Все источники</option>
            <option v-for="s in sources" :key="s.id" :value="s.id">
              {{ s.title || s.username || s.reference }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>Тег</span>
          <select v-model="exportForm.tag">
            <option value="">Все теги</option>
            <option v-for="t in tags" :key="t.name" :value="t.name">{{ t.name }}</option>
          </select>
        </label>
        <label class="field">
          <span>Лимит строк (0 = все)</span>
          <input v-model.number="exportForm.limit" type="number" min="0" />
        </label>
      </div>
      <div class="field-inline">
        <label><input v-model="exportForm.include_pii" type="checkbox" /> включить персональные данные</label>
      </div>
      <div class="toolbar">
        <button :disabled="exportBusy" @click="previewExport">Предпросмотр</button>
        <button class="primary" :disabled="exportBusy" @click="runExport">
          {{ exportBusy ? 'Сохраняем…' : 'Экспортировать' }}
        </button>
      </div>
      <div v-if="exportPreview" class="inline-note">
        <p>Строк: {{ exportPreview.count }} · Полей: {{ exportPreview.fields.length }}</p>
        <p class="muted">{{ exportPreview.note }}</p>
        <p class="muted">Папка: {{ exportPreview.destination }}</p>
      </div>
    </div>

    <!-- Import -->
    <div v-if="showImport" class="card">
      <h3>Импорт базы</h3>
      <p class="muted">
        Вставьте содержимое CSV или JSON. Совпадения объединяются, дубликаты не создаются.
      </p>
      <label class="field">
        <span>Формат</span>
        <select v-model="importForm.format">
          <option value="csv">CSV</option>
          <option value="json">JSON</option>
        </select>
      </label>
      <label class="field">
        <span>Источник (необязательно)</span>
        <select v-model="importForm.source_id">
          <option value="">Не привязывать</option>
          <option v-for="s in sources" :key="s.id" :value="s.id">
            {{ s.title || s.username || s.reference }}
          </option>
        </select>
      </label>
      <label class="field">
        <span>Данные</span>
        <textarea v-model="importForm.data" rows="6" placeholder="telegram_user_id,username,..."></textarea>
      </label>
      <button class="primary" :disabled="importBusy || !importForm.data" @click="runImport">
        {{ importBusy ? 'Импортируем…' : 'Импортировать' }}
      </button>
      <div v-if="importResult" class="inline-note">
        Добавлено: {{ importResult.created }} · Объединено: {{ importResult.merged }} ·
        Пропущено: {{ importResult.invalid }}
      </div>
    </div>

    <!-- User detail -->
    <div v-if="detail" class="card">
      <div class="row-between">
        <h3>{{ detail.display_name || detail.username || detail.telegram_user_id }}</h3>
        <button @click="detail = null">Закрыть</button>
      </div>
      <div class="two-cols">
        <p><strong>@username:</strong> {{ detail.username || '—' }}</p>
        <p><strong>Telegram ID:</strong> {{ detail.telegram_user_id }}</p>
        <p><strong>Статус:</strong> {{ STATUS_LABELS[detail.status] ?? detail.status }}</p>
        <p><strong>Оценка:</strong> {{ detail.score }} <span class="muted">{{ detail.score_reason }}</span></p>
        <p><strong>Premium:</strong> {{ detail.is_premium ? 'Да' : 'Нет' }}</p>
        <p><strong>Приглашение:</strong> {{ INVITE_LABELS[detail.invite_status] ?? detail.invite_status }}</p>
        <p><strong>Телефон:</strong> {{ detail.phone_masked || '—' }}</p>
        <p><strong>Последняя активность:</strong>
          {{ detail.last_seen_at ? new Date(detail.last_seen_at).toLocaleString() : '—' }}
        </p>
      </div>
      <p v-if="detail.tags.length"><strong>Теги:</strong>
        <span v-for="t in detail.tags" :key="t" class="badge badge-muted">{{ t }}</span>
      </p>
      <p v-if="detail.sources.length"><strong>Источники:</strong> {{ detail.sources.join(', ') }}</p>
      <div v-if="detail.score_components.length">
        <strong>Из чего состоит оценка:</strong>
        <ul class="plain-list">
          <li v-for="(c, i) in detail.score_components" :key="i">
            {{ c.label ?? c.key ?? 'компонент' }}: {{ c.value ?? c.score ?? '' }}
          </li>
        </ul>
      </div>
      <p v-if="detail.last_invite_error" class="error-text">
        Последняя ошибка приглашения: {{ detail.last_invite_error }}
      </p>
    </div>

    <!-- Table -->
    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="users.length === 0" class="card empty">
      Ничего не найдено. Измените фильтры или добавьте источник и запустите сканирование.
    </div>
    <table v-else class="table">
      <thead>
        <tr>
          <th><input type="checkbox" :checked="allSelected" @change="toggleAll" /></th>
          <th>Участник</th>
          <th>Статус</th>
          <th>Оценка</th>
          <th>Теги</th>
          <th>Приглашение</th>
          <th>Активность</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td><input type="checkbox" :checked="selected.includes(u.id)" @change="toggleSelect(u.id)" /></td>
          <td>
            <a href="#" @click.prevent="openDetail(u)">
              <strong>{{ u.display_name || (u.username ? '@' + u.username : u.telegram_user_id) }}</strong>
            </a>
            <div class="muted">
              <span v-if="u.username">@{{ u.username }} · </span>ID {{ u.telegram_user_id }}
              <span v-if="u.is_bot" class="badge badge-muted">бот</span>
              <span v-if="u.is_premium" class="badge ok">Premium</span>
            </div>
          </td>
          <td>
            <span
              class="status-dot"
              :class="u.status === 'active' ? 'status-ok' : u.status === 'deleted' ? 'status-error' : 'status-unknown'"
            ></span>
            {{ STATUS_LABELS[u.status] ?? u.status }}
          </td>
          <td>{{ u.score }}</td>
          <td>
            <span v-for="t in u.tags" :key="t" class="badge badge-muted">{{ t }}</span>
            <span v-if="!u.tags.length" class="muted">—</span>
          </td>
          <td>{{ INVITE_LABELS[u.invite_status] ?? u.invite_status }}</td>
          <td class="muted">
            {{ u.last_seen_at ? new Date(u.last_seen_at).toLocaleDateString() : '—' }}
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="!loading && users.length" class="toolbar">
      <button :disabled="page === 0" @click="goPage(-1)">← Назад</button>
      <span class="muted">Страница {{ page + 1 }} из {{ totalPages }} · всего {{ total }}</span>
      <button :disabled="page + 1 >= totalPages" @click="goPage(1)">Вперёд →</button>
      <label class="field-inline">
        <span class="muted">На странице:</span>
        <select v-model.number="limit" @change="applyFilters">
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
        </select>
      </label>
    </div>
  </div>
</template>
