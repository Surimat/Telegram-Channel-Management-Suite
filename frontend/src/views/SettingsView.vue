<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type NotificationSettings, type Setting } from '@/api/client'

const settings = ref<Setting[]>([])
const loading = ref(true)
const error = ref('')
const saved = ref(false)

const notifications = ref<NotificationSettings | null>(null)
const notificationsSaved = ref(false)
const notificationsError = ref('')

const miniappUrl = ref('')
const miniappBusy = ref(false)
const miniappResult = ref('')
const miniappOk = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    settings.value = await api.settings()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Ошибка загрузки настроек.'
  } finally {
    loading.value = false
  }
  try {
    notifications.value = await api.managerNotifications()
  } catch {
    notifications.value = null
  }
  try {
    const cfg = await api.miniappConfig()
    miniappUrl.value = cfg.public_url
  } catch {
    // Mini App config is optional for this page.
  }
}

async function setupMiniApp() {
  miniappBusy.value = true
  miniappResult.value = ''
  try {
    const result = await api.miniappSetup(miniappUrl.value)
    miniappOk.value = result.ok
    miniappResult.value = result.ok ? result.message : `${result.message} ${result.how_to_fix}`
  } catch (e) {
    miniappOk.value = false
    miniappResult.value = e instanceof Error ? e.message : 'Не удалось подключить мини-приложение.'
  } finally {
    miniappBusy.value = false
  }
}

async function save() {
  saved.value = false
  error.value = ''
  const values: Record<string, string> = {}
  for (const s of settings.value) {
    if (!s.is_secret) values[s.key] = s.value
  }
  try {
    settings.value = await api.updateSettings(values)
    saved.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Не удалось сохранить настройки.'
  }
}

async function saveNotifications() {
  if (!notifications.value) return
  notificationsSaved.value = false
  notificationsError.value = ''
  const categories: Record<string, boolean> = {}
  for (const c of notifications.value.categories) categories[c.key] = c.enabled
  try {
    notifications.value = await api.managerUpdateNotifications({
      enabled: notifications.value.enabled,
      categories,
    })
    notificationsSaved.value = true
  } catch (e) {
    notificationsSaved.value = false
    notificationsError.value =
      e instanceof Error ? e.message : 'Не удалось сохранить уведомления.'
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Настройки</h2>
    <p class="page-subtitle">
      Здесь можно изменить параметры системы. Секреты (токены, ключи) здесь не хранятся и не
      отображаются.
    </p>

    <div v-if="loading" class="card">Загрузка...</div>
    <div v-else-if="error" class="card error-text">{{ error }}</div>
    <div v-else-if="!settings.length" class="card empty">
      Пока нет настроек для отображения. Они появятся по мере настройки системы.
    </div>

    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Параметр</th>
            <th>Зачем нужно</th>
            <th>Значение</th>
            <th>По умолчанию</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in settings" :key="s.key">
            <td><strong>{{ s.title || s.key }}</strong></td>
            <td class="muted">{{ s.description || '—' }}</td>
            <td>
              <input
                v-model="s.value"
                :disabled="s.is_secret"
                :type="s.value_type === 'int' || s.value_type === 'float' ? 'number' : 'text'"
              />
            </td>
            <td class="muted">{{ s.default_value || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p style="margin-top: 16px">
        <button class="primary" @click="save">Сохранить</button>
        <span v-if="saved" class="muted" style="margin-left: 12px">Сохранено</span>
      </p>
    </div>

    <div v-if="notifications" class="card" style="margin-top: 20px">
      <h3>Уведомления управляющего бота</h3>
      <p class="muted">
        Управляющий бот может присылать важные события в Telegram. Включайте только нужные
        категории, чтобы не получать лишние сообщения.
      </p>

      <label class="toggle-row">
        <input v-model="notifications.enabled" type="checkbox" />
        <span><strong>Присылать уведомления</strong> — общий выключатель</span>
      </label>

      <div v-if="notifications.enabled" class="notif-grid">
        <label v-for="c in notifications.categories" :key="c.key" class="toggle-row">
          <input v-model="c.enabled" type="checkbox" />
          <span>{{ c.label }}</span>
        </label>
      </div>

      <p style="margin-top: 16px">
        <button class="primary" @click="saveNotifications">Сохранить уведомления</button>
        <span v-if="notificationsSaved" class="muted" style="margin-left: 12px">Сохранено</span>
        <span v-if="notificationsError" class="error-text" style="margin-left: 12px">
          {{ notificationsError }}
        </span>
      </p>
    </div>

    <div class="card" style="margin-top: 20px">
      <h3>Мини-приложение Telegram</h3>
      <p class="muted">
        Мини-приложение открывает эту же панель прямо из Telegram — кнопкой меню у бота.
        Для работы нужен публичный адрес по HTTPS (локальный
        <code>http://127.0.0.1</code> не подойдёт). Обычный локальный веб-интерфейс
        работает и без этого.
      </p>

      <label class="field">
        <span>Публичный адрес приложения</span>
        <input v-model="miniappUrl" type="text" placeholder="https://ваш-домен" />
      </label>
      <p class="muted">
        Укажите адрес, по которому панель доступна из интернета. Мы зарегистрируем его в
        Telegram как кнопку меню бота. Токен бота при этом нигде не показывается.
      </p>

      <p style="margin-top: 16px">
        <button class="primary" :disabled="miniappBusy" @click="setupMiniApp">
          {{ miniappBusy ? 'Подключаем…' : 'Подключить мини-приложение' }}
        </button>
        <span
          v-if="miniappResult"
          :class="miniappOk ? 'muted' : 'error-text'"
          style="margin-left: 12px"
        >
          {{ miniappResult }}
        </span>
      </p>
    </div>
  </div>
</template>
