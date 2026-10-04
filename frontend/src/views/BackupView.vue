<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  ApiError,
  type BackupEntry,
  type BackupInfo,
  type BackupList,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const info = ref<BackupInfo | null>(null)
const list = ref<BackupList | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const includeSessions = ref(false)
const note = ref('')
const importFile = ref<File | null>(null)
const replaceOnImport = ref(true)

function friendly(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.hint ? `${e.message} ${e.hint}` : e.message
  return e instanceof Error ? e.message : fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [i, l] = await Promise.all([api.backupInfo(), api.backups()])
    info.value = i
    list.value = l
    includeSessions.value = l.include_sessions_default
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить данные о копиях.')
  } finally {
    loading.value = false
  }
}

async function createBackup() {
  if (includeSessions.value) {
    const ok = window.confirm(
      'Вы включаете файлы сессий Telegram. Они дают полный доступ к аккаунтам. ' +
        'Храните такую копию в защищённом месте. Продолжить?',
    )
    if (!ok) return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const entry = await api.createBackup({
      include_sessions: includeSessions.value,
      note: note.value,
    })
    notice.value = `Копия создана: ${entry.filename} (${entry.size_human}).`
    note.value = ''
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось создать копию.')
  } finally {
    busy.value = false
  }
}

async function restore(entry: BackupEntry) {
  const ok = window.confirm(
    `Восстановить из копии «${entry.filename}»?\n\n` +
      'Текущие данные будут заменены. Перед этим автоматически создаётся ' +
      'защитная копия текущего состояния.',
  )
  if (!ok) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await api.restoreBackup(entry.filename)
    notice.value =
      `Восстановлено из «${result.source}». Защитная копия: ${result.safety_backup}. ` +
      'Перезапустите приложение, чтобы все изменения вступили в силу.'
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось восстановить из копии.')
  } finally {
    busy.value = false
  }
}

async function remove(entry: BackupEntry) {
  if (!window.confirm(`Удалить копию «${entry.filename}»? Это действие нельзя отменить.`)) {
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.deleteBackup(entry.filename)
    notice.value = 'Копия удалена.'
    await load()
  } catch (e) {
    error.value = friendly(e, 'Не удалось удалить копию.')
  } finally {
    busy.value = false
  }
}

function download(entry: BackupEntry) {
  window.location.href = api.backupDownloadUrl(entry.filename)
}

function exportConfig() {
  window.location.href = api.configExportUrl()
}

async function importConfig() {
  const file = importFile.value
  if (!file) {
    error.value = 'Выберите файл конфигурации (.json).'
    return
  }
  if (
    replaceOnImport.value &&
    !window.confirm(
      'Импорт заменит текущие правила, профили реакций и настройки содержимым файла. Продолжить?',
    )
  ) {
    return
  }
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const resp = await fetch(
      '/api/v1/backup/config/import?replace=' + (replaceOnImport.value ? 'true' : 'false'),
      { method: 'POST', body: form },
    )
    const data = await resp.json()
    if (!resp.ok) {
      error.value = data?.error?.message ?? 'Не удалось импортировать конфигурацию.'
    } else {
      const counts = data.imported ?? {}
      const summary = Object.entries(counts)
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ')
      notice.value = `Конфигурация импортирована (${summary}).`
      importFile.value = null
    }
  } catch (e) {
    error.value = friendly(e, 'Не удалось импортировать конфигурацию.')
  } finally {
    busy.value = false
  }
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  importFile.value = target.files?.[0] ?? null
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU')
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Резервные копии <InfoHint topic="backup" /></h2>
    <p class="page-subtitle">
      Сохраняйте и восстанавливайте данные приложения. Конфигурацию можно перенести между
      установками отдельным файлом.
    </p>

    <div v-if="loading" class="card">Загрузка...</div>
    <div v-else-if="error" class="card error-text">{{ error }}</div>

    <template v-else>
      <div v-if="notice" class="card success-text">{{ notice }}</div>

      <div v-if="info" class="card help-card">
        <h3>Зачем это нужно</h3>
        <p>{{ info.what_it_does }}</p>
        <p class="muted">{{ info.why }}</p>
        <p class="warning-text">{{ info.sessions_warning }}</p>
        <p class="muted">Безопасное значение по умолчанию: {{ info.safe_default }}</p>
      </div>

      <div class="card">
        <h3>Создать копию</h3>
        <div class="row">
          <label class="checkbox">
            <input v-model="includeSessions" type="checkbox" />
            Включить файлы сессий (небезопасно, по умолчанию выключено)
          </label>
        </div>
        <div class="row">
          <input
            v-model="note"
            type="text"
            placeholder="Заметка к копии (необязательно)"
            maxlength="200"
          />
          <button class="primary" :disabled="busy" @click="createBackup">
            Создать копию
          </button>
        </div>
      </div>

      <div class="card">
        <div class="row space-between">
          <h3>Сохранённые копии ({{ list?.total ?? 0 }})</h3>
          <span class="muted">Папка: {{ list?.backup_dir }}</span>
        </div>
        <p class="muted">
          Хранится последних копий: {{ list?.retention === 0 ? 'все' : list?.retention }}.
        </p>

        <div v-if="!list?.items.length" class="empty">
          Пока нет резервных копий. Создайте первую кнопкой выше.
        </div>

        <table v-else>
          <thead>
            <tr>
              <th>Файл</th>
              <th>Дата</th>
              <th>Размер</th>
              <th>Сессии</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in list.items" :key="entry.filename">
              <td><strong>{{ entry.filename }}</strong></td>
              <td>{{ formatDate(entry.created_at) }}</td>
              <td>{{ entry.size_human }}</td>
              <td>
                <span :class="entry.includes_sessions ? 'badge warning' : 'badge ok'">
                  {{ entry.includes_sessions ? 'включены' : 'нет' }}
                </span>
              </td>
              <td class="actions">
                <button :disabled="busy" @click="download(entry)">Скачать</button>
                <button :disabled="busy" @click="restore(entry)">Восстановить</button>
                <button class="danger" :disabled="busy" @click="remove(entry)">Удалить</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3>Конфигурация</h3>
        <p class="muted">
          Экспорт содержит правила, профили реакций и настройки. Секреты и аккаунты в файл не
          попадают.
        </p>
        <div class="row">
          <button :disabled="busy" @click="exportConfig">
            Экспортировать конфигурацию
          </button>
        </div>
        <div class="row">
          <input type="file" accept="application/json,.json" @change="onFileChange" />
          <label class="checkbox">
            <input v-model="replaceOnImport" type="checkbox" />
            Заменить текущую конфигурацию
          </label>
          <button :disabled="busy || !importFile" @click="importConfig">
            Импортировать конфигурацию
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.5rem;
}
.space-between {
  justify-content: space-between;
}
.checkbox {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.badge {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
}
.badge.ok {
  background: rgba(46, 160, 67, 0.15);
}
.badge.warning {
  background: rgba(210, 153, 34, 0.2);
}
.btn.danger {
  color: #b42318;
}
.help-card h3 {
  margin-top: 0;
}
.success-text {
  color: #17663a;
}
</style>
