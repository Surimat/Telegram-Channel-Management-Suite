<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type Channel,
  type PermissionResult,
  type ProxyProfile,
  type SessionImportDetect,
  type SessionRisk,
  type SessionSummary,
  type UserSession,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const accounts = ref<UserSession[]>([])
const channels = ref<Channel[]>([])
const summary = ref<SessionSummary | null>(null)
const risks = ref<Record<string, SessionRisk>>({})
const loading = ref(true)
const busyId = ref('')
const error = ref('')
const notice = ref('')

// Wizard state
const showWizard = ref(false)
const wStep = ref<'credentials' | 'code' | 'password' | 'done'>('credentials')
const wBusy = ref(false)
const wError = ref('')
const wAccountId = ref('')
const wPhoneMasked = ref('')
const wIdentity = ref('')

const form = ref({ api_id: '', api_hash: '', phone: '', display_name: '' })
const codeInput = ref('')
const passwordInput = ref('')

// Import state
const showImport = ref(false)
const importForm = ref({ api_id: '', api_hash: '', phone: '', session_file_path: '' })

// Account Hub: multi-format local import (v1.1). The string session is a secret:
// it is sent once and never shown again.
const showImportHub = ref(false)
const hubTab = ref<'file' | 'string'>('file')
const hubForm = ref({ path: '', string_session: '', api_id: '', api_hash: '', phone: '' })
const hubDetect = ref<SessionImportDetect | null>(null)
const hubBusy = ref(false)

const RISK_CLASS: Record<string, string> = {
  healthy: 'status-ok',
  warning: 'status-warning',
  flood_wait: 'status-warning',
  restricted: 'status-error',
  auth_required: 'status-warning',
  disabled: 'status-unknown',
  unknown: 'status-unknown',
}

// Network routes / proxies (v1.1). A proxy is a normal connection route; it
// never lifts Telegram limits.
const proxies = ref<ProxyProfile[]>([])
const proxyNotice = ref('')
const proxyBusy = ref(false)
const proxyError = ref('')
const proxyForm = ref({ name: '', kind: 'socks5', host: '', port: 1080, username: '', password: '' })

const PROXY_STATUS_CLASS: Record<string, string> = {
  ok: 'status-ok',
  error: 'status-error',
  timeout: 'status-warning',
  unknown: 'status-unknown',
}

async function loadProxies() {
  try {
    const data = await api.proxies()
    proxies.value = data.items
    proxyNotice.value = data.notice
  } catch {
    proxies.value = []
  }
}

async function addProxy() {
  proxyBusy.value = true
  proxyError.value = ''
  try {
    await api.addProxy({
      name: proxyForm.value.name,
      kind: proxyForm.value.kind,
      host: proxyForm.value.host,
      port: Number(proxyForm.value.port) || 0,
      username: proxyForm.value.username,
      password: proxyForm.value.password,
    })
    proxyForm.value = { name: '', kind: 'socks5', host: '', port: 1080, username: '', password: '' }
    await loadProxies()
  } catch (e) {
    proxyError.value = friendlyError(e)
  } finally {
    proxyBusy.value = false
  }
}

async function checkProxy(p: ProxyProfile) {
  proxyBusy.value = true
  proxyError.value = ''
  try {
    const result = await api.checkProxy(p.id)
    notice.value = result.message
    await loadProxies()
  } catch (e) {
    proxyError.value = friendlyError(e)
  } finally {
    proxyBusy.value = false
  }
}

async function removeProxy(p: ProxyProfile) {
  if (!confirm(`Удалить прокси «${p.name}»? Аккаунты переключатся на прямое подключение.`)) return
  proxyBusy.value = true
  proxyError.value = ''
  try {
    await api.removeProxy(p.id)
    await loadProxies()
    await load()
  } catch (e) {
    proxyError.value = friendlyError(e)
  } finally {
    proxyBusy.value = false
  }
}

async function assignProxy(a: UserSession, profileId: string) {
  proxyBusy.value = true
  proxyError.value = ''
  try {
    await api.bindProxy(a.id, profileId)
    await load()
  } catch (e) {
    proxyError.value = friendlyError(e)
  } finally {
    proxyBusy.value = false
  }
}

const proxyName = (id: string) =>
  proxies.value.find((p) => p.id === id)?.name || '—'

// Permission probe (post-1.0 hardening)
const permAccountId = ref('')
const permTarget = ref('')
const permChannelId = ref('')
const permResult = ref<PermissionResult | null>(null)
const permHistory = ref<PermissionResult[]>([])
const permBusy = ref(false)
const permError = ref('')

const PERM_STATUS_LABEL: Record<string, string> = {
  ok: 'Всё доступно',
  partial: 'Частичный доступ',
  no_access: 'Нет доступа',
  auth_required: 'Требуется авторизация',
  admin_required: 'Нужны права администратора',
  privacy_restricted: 'Данные скрыты Telegram',
  flood_wait: 'Telegram просит подождать',
  error: 'Ошибка проверки',
}

function permStatusLabel(s: string): string {
  return permResult.value?.status_label || PERM_STATUS_LABEL[s] || s
}

async function loadPermissionHistory() {
  try {
    const data = await api.permissionHistory(10)
    permHistory.value = data.items
  } catch {
    permHistory.value = []
  }
}

async function runPermissionCheck() {
  permBusy.value = true
  permError.value = ''
  permResult.value = null
  try {
    permResult.value = await api.permissionCheck({
      account_id: permAccountId.value,
      target: permChannelId.value ? undefined : permTarget.value,
      channel_id: permChannelId.value || undefined,
    })
    await loadPermissionHistory()
  } catch (e) {
    permError.value = friendlyError(e)
  } finally {
    permBusy.value = false
  }
}

const STATUS_LABEL: Record<string, string> = {
  online: 'Авторизован',
  auth_required: 'Нужна авторизация',
  disconnected: 'Нет сессии',
  flood_wait: 'Ожидание Telegram',
  error: 'Ошибка',
  disabled: 'Выключен',
}

const statusLabel = (s: string) => STATUS_LABEL[s] ?? s
const statusClass = (s: string) =>
  s === 'online'
    ? 'status-ok'
    : s === 'auth_required' || s === 'flood_wait'
      ? 'status-warning'
      : s === 'error'
        ? 'status-error'
        : 'status-unknown'

function friendlyError(e: unknown): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || 'Произошла ошибка.'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    accounts.value = await api.sessions()
    summary.value = await api.sessionsSummary()
    channels.value = (await api.channels({ limit: '200' })).items
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
  // Risk bands are best-effort: a failure must not hide the account list.
  const next: Record<string, SessionRisk> = {}
  await Promise.all(
    accounts.value.map(async (a) => {
      try {
        next[a.id] = await api.sessionRisk(a.id)
      } catch {
        /* ignore single-account risk failure */
      }
    }),
  )
  risks.value = next
}

async function hubDetectFormat() {
  hubBusy.value = true
  error.value = ''
  hubDetect.value = null
  try {
    hubDetect.value = await api.detectSessionImport({
      path: hubForm.value.path,
      string_session: hubTab.value === 'string' ? hubForm.value.string_session : '',
      api_id: hubForm.value.api_id,
      api_hash: hubForm.value.api_hash,
    })
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    hubBusy.value = false
  }
}

async function hubImport() {
  hubBusy.value = true
  error.value = ''
  try {
    const res = await api.importSessionArtifact({
      path: hubTab.value === 'file' ? hubForm.value.path : '',
      string_session: hubTab.value === 'string' ? hubForm.value.string_session : '',
      api_id: hubForm.value.api_id,
      api_hash: hubForm.value.api_hash,
      phone: hubForm.value.phone,
    })
    hubForm.value = { path: '', string_session: '', api_id: '', api_hash: '', phone: '' }
    hubDetect.value = null
    showImportHub.value = false
    notice.value = `${res.message || 'Аккаунт подключён.'} Формат: ${res.format_title}.`
    await load()
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    hubBusy.value = false
  }
}

function resetWizard() {
  wStep.value = 'credentials'
  wAccountId.value = ''
  wPhoneMasked.value = ''
  wIdentity.value = ''
  codeInput.value = ''
  passwordInput.value = ''
  wError.value = ''
  form.value = { api_id: '', api_hash: '', phone: '', display_name: '' }
}

function openWizard() {
  resetWizard()
  showWizard.value = true
  showImport.value = false
}

async function startAuth() {
  wBusy.value = true
  wError.value = ''
  try {
    const res = await api.authStart({
      api_id: form.value.api_id,
      api_hash: form.value.api_hash,
      phone: form.value.phone,
      display_name: form.value.display_name,
    })
    wAccountId.value = res.account_id ?? ''
    wPhoneMasked.value = res.phone_masked
    wStep.value = res.next_step === 'code' ? 'code' : 'code'
    notice.value = res.message
  } catch (e) {
    wError.value = friendlyError(e)
  } finally {
    wBusy.value = false
  }
}

async function submitCode() {
  wBusy.value = true
  wError.value = ''
  try {
    const res = await api.authCode(wAccountId.value, codeInput.value)
    if (res.done) {
      wStep.value = 'done'
      wIdentity.value = res.identity ? `${res.identity.display_name}${res.identity.username ? ' (@' + res.identity.username + ')' : ''}` : ''
    } else if (res.next_step === 'password') {
      wStep.value = 'password'
    }
  } catch (e) {
    wError.value = friendlyError(e)
  } finally {
    wBusy.value = false
  }
}

async function submitPassword() {
  wBusy.value = true
  wError.value = ''
  try {
    const res = await api.authPassword(wAccountId.value, passwordInput.value)
    if (res.done) {
      wStep.value = 'done'
      wIdentity.value = res.identity ? `${res.identity.display_name}${res.identity.username ? ' (@' + res.identity.username + ')' : ''}` : ''
    }
  } catch (e) {
    wError.value = friendlyError(e)
  } finally {
    wBusy.value = false
  }
}

async function finishWizard() {
  showWizard.value = false
  resetWizard()
  notice.value = 'Аккаунт добавлен.'
  await load()
}

async function submitImport() {
  wBusy.value = true
  wError.value = ''
  try {
    await api.importSession({
      api_id: importForm.value.api_id,
      api_hash: importForm.value.api_hash,
      phone: importForm.value.phone,
      session_file_path: importForm.value.session_file_path,
    })
    showImport.value = false
    importForm.value = { api_id: '', api_hash: '', phone: '', session_file_path: '' }
    notice.value = 'Аккаунт импортирован.'
    await load()
  } catch (e) {
    wError.value = friendlyError(e)
  } finally {
    wBusy.value = false
  }
}

async function withAccount(id: string, fn: () => Promise<unknown>) {
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

const check = (a: UserSession) => withAccount(a.id, () => api.checkSession(a.id))
const toggle = (a: UserSession) =>
  withAccount(a.id, () => (a.enabled ? api.disableSession(a.id) : api.enableSession(a.id)))
const logout = (a: UserSession) => {
  if (!confirm('Начать повторную авторизацию этого аккаунта?')) return
  return withAccount(a.id, () => api.logoutSession(a.id))
}
const remove = (a: UserSession) => {
  if (!confirm(`Удалить аккаунт ${a.username ? '@' + a.username : a.phone_masked} и его файл сессии?`)) return
  return withAccount(a.id, () => api.removeSession(a.id))
}

onMounted(() => {
  load()
  loadPermissionHistory()
  loadProxies()
})
</script>

<template>
  <div>
    <h2 class="page-title">Аккаунты <InfoHint topic="telegram_account" /></h2>
    <p class="page-subtitle">
      Пользовательские аккаунты Telegram нужны для анализа аудитории и приглашений.
      Файлы сессий хранятся локально и никогда не попадают в git, а секреты — только
      в зашифрованном виде.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div v-if="summary" class="grid">
      <div class="card">
        <strong>Всего аккаунтов</strong>
        <p class="muted">{{ summary.total }} · готовых: {{ summary.active }}</p>
      </div>
      <div class="card">
        <strong>Состояние</strong>
        <p class="muted">
          Авторизовано: {{ summary.online }} · нужна авторизация: {{ summary.auth_required }} ·
          выключено: {{ summary.disabled }}
        </p>
      </div>
    </div>

    <div class="toolbar">
      <button class="primary" @click="openWizard">
        {{ showWizard || showImport || showImportHub ? 'Отмена' : '+ Добавить аккаунт' }}
      </button>
      <button @click="showImportHub = !showImportHub; showImport = false; showWizard = false">
        Центр аккаунтов (импорт)
      </button>
      <button @click="showImport = !showImport; showWizard = false; showImportHub = false">
        Импортировать .session
      </button>
      <button @click="load">Обновить</button>
    </div>

    <!-- Account Hub: multi-format local import (v1.1) -->
    <div v-if="showImportHub" class="card">
      <h3>Центр аккаунтов — импорт</h3>
      <p class="muted">
        Импортируйте только свои аккаунты и файлы, которыми вы владеете или имеете право
        управлять. Мы не ищем и не скачиваем чужие сессии и не обходим проверки Telegram.
      </p>
      <div class="actions" style="margin-bottom: 0.75rem">
        <button :class="{ primary: hubTab === 'file' }" @click="hubTab = 'file'; hubDetect = null">
          Файл или папка
        </button>
        <button :class="{ primary: hubTab === 'string' }" @click="hubTab = 'string'; hubDetect = null">
          StringSession
        </button>
      </div>

      <template v-if="hubTab === 'file'">
        <label class="field">
          <span>Путь к файлу .session, .json или папке TDATA</span>
          <input
            v-model="hubForm.path"
            placeholder="C:\\path\\to\\account.session или C:\\path\\to\\tdata"
            autocomplete="off"
          />
        </label>
      </template>
      <template v-else>
        <label class="field">
          <span>Строка StringSession</span>
          <input
            v-model="hubForm.string_session"
            type="password"
            placeholder="1AbCd..."
            autocomplete="off"
          />
        </label>
      </template>

      <label class="field">
        <span>API ID (если известен)</span>
        <input v-model="hubForm.api_id" placeholder="1234567" autocomplete="off" />
      </label>
      <label class="field">
        <span>API Hash (если известен)</span>
        <input v-model="hubForm.api_hash" type="password" autocomplete="off" />
      </label>
      <label class="field">
        <span>Номер телефона (необязательно)</span>
        <input v-model="hubForm.phone" placeholder="+79991234567" autocomplete="off" />
      </label>

      <div class="actions">
        <button
          :disabled="hubBusy || (hubTab === 'file' ? !hubForm.path : !hubForm.string_session)"
          @click="hubDetectFormat"
        >
          {{ hubBusy ? 'Определяем формат…' : 'Определить формат' }}
        </button>
        <button
          class="primary"
          :disabled="hubBusy || (hubTab === 'file' ? !hubForm.path : !hubForm.string_session)"
          @click="hubImport"
        >
          {{ hubBusy ? 'Импортируем…' : 'Импортировать' }}
        </button>
      </div>

      <div v-if="hubDetect" class="inline-note">
        <p>
          Формат: <strong>{{ hubDetect.format_title }}</strong>
          <span v-if="hubDetect.format !== 'unknown'"> · {{ hubDetect.format }}</span>
        </p>
        <p>
          Состояние:
          <span class="badge" :class="hubDetect.state === 'valid' ? 'ok' : 'warning'">
            {{ hubDetect.state_title }}
          </span>
          <span v-if="!hubDetect.available" class="badge warning">недоступно</span>
        </p>
        <p :class="hubDetect.state === 'valid' ? 'ok-text' : 'muted'">{{ hubDetect.message }}</p>
        <p v-if="hubDetect.how_to_fix" class="muted">{{ hubDetect.how_to_fix }}</p>
        <ul v-if="hubDetect.notes.length" class="muted">
          <li v-for="n in hubDetect.notes" :key="n">{{ n }}</li>
        </ul>
      </div>

      <p class="inline-note">
        Файл авторизации Telegram — чувствительные данные. Никому его не передавайте.
      </p>
    </div>

    <!-- Wizard -->
    <div v-if="showWizard" class="card">
      <h3>Мастер добавления аккаунта</h3>

      <div v-if="wStep === 'credentials'">
        <p class="muted">
          API ID и API Hash выдаются Telegram на странице
          <a href="https://my.telegram.org" target="_blank" rel="noopener">my.telegram.org</a>
          в разделе «API development tools». Они нужны, чтобы программа могла работать
          от имени вашего аккаунта.
        </p>
        <label class="field">
          <span>API ID</span>
          <input v-model="form.api_id" placeholder="1234567" autocomplete="off" />
        </label>
        <label class="field">
          <span>API Hash</span>
          <input v-model="form.api_hash" type="password" placeholder="abcdef0123456789" autocomplete="off" />
        </label>
        <label class="field">
          <span>Номер телефона</span>
          <input v-model="form.phone" placeholder="+79991234567" autocomplete="off" />
        </label>
        <label class="field">
          <span>Название (необязательно)</span>
          <input v-model="form.display_name" placeholder="Основной аккаунт" />
        </label>
        <div v-if="wError" class="error-text">{{ wError }}</div>
        <button class="primary" :disabled="wBusy || !form.api_id || !form.api_hash || !form.phone" @click="startAuth">
          {{ wBusy ? 'Отправляем код…' : 'Получить код' }}
        </button>
      </div>

      <div v-else-if="wStep === 'code'">
        <p class="muted">
          Код отправлен в Telegram на номер {{ wPhoneMasked }}. Откройте приложение
          Telegram и введите код (в служебном чате «Telegram»).
        </p>
        <label class="field">
          <span>Код подтверждения</span>
          <input v-model="codeInput" placeholder="12345" autocomplete="off" />
        </label>
        <div v-if="wError" class="error-text">{{ wError }}</div>
        <button class="primary" :disabled="wBusy || !codeInput" @click="submitCode">
          {{ wBusy ? 'Проверяем…' : 'Подтвердить' }}
        </button>
      </div>

      <div v-else-if="wStep === 'password'">
        <p class="muted">
          У аккаунта включена двухэтапная аутентификация. Введите облачный пароль,
          который вы задавали в настройках Telegram.
        </p>
        <label class="field">
          <span>Пароль 2FA</span>
          <input v-model="passwordInput" type="password" autocomplete="off" />
        </label>
        <div v-if="wError" class="error-text">{{ wError }}</div>
        <button class="primary" :disabled="wBusy || !passwordInput" @click="submitPassword">
          {{ wBusy ? 'Проверяем…' : 'Войти' }}
        </button>
      </div>

      <div v-else>
        <h4>Готово</h4>
        <p>Аккаунт авторизован<span v-if="wIdentity">: {{ wIdentity }}</span>.</p>
        <button class="primary" @click="finishWizard">Завершить</button>
      </div>
    </div>

    <!-- Import -->
    <div v-if="showImport" class="card">
      <h3>Импорт существующей сессии</h3>
      <p class="muted">
        Укажите путь к файлу <code>.session</code> на этом компьютере. Файл будет
        скопирован в защищённую папку сессий. Его содержимое нигде не показывается и не
        записывается в логи.
      </p>
      <label class="field">
        <span>API ID</span>
        <input v-model="importForm.api_id" placeholder="1234567" autocomplete="off" />
      </label>
      <label class="field">
        <span>API Hash</span>
        <input v-model="importForm.api_hash" type="password" autocomplete="off" />
      </label>
      <label class="field">
        <span>Номер телефона (необязательно)</span>
        <input v-model="importForm.phone" placeholder="+79991234567" />
      </label>
      <label class="field">
        <span>Путь к файлу .session</span>
        <input v-model="importForm.session_file_path" placeholder="C:\\path\\to\\account.session" />
      </label>
      <div v-if="wError" class="error-text">{{ wError }}</div>
      <button
        class="primary"
        :disabled="wBusy || !importForm.api_id || !importForm.api_hash || !importForm.session_file_path"
        @click="submitImport"
      >
        {{ wBusy ? 'Импортируем…' : 'Импортировать' }}
      </button>
    </div>

    <div v-if="loading" class="card">Загрузка…</div>
    <div v-else-if="accounts.length === 0" class="card empty">
      Пока нет ни одного аккаунта. Нажмите «+ Добавить аккаунт», чтобы подключить
      пользовательский аккаунт Telegram.
    </div>
    <table v-else>
      <thead>
        <tr>
          <th>Аккаунт</th>
          <th>Телефон</th>
          <th>Состояние</th>
          <th>Риск ограничений</th>
          <th>Проверка</th>
          <th>Маршрут</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in accounts" :key="a.id">
          <td>
            <strong>{{ a.username ? '@' + a.username : a.display_name || 'Без имени' }}</strong>
            <div class="muted">
              ID: {{ a.telegram_user_id ?? '—' }}
              <span v-if="!a.has_session"> · нет сессии</span>
              <span v-if="!a.session_file_exists && a.has_session"> · файл не найден</span>
            </div>
          </td>
          <td class="muted">{{ a.phone_masked || '—' }}</td>
          <td>
            <span class="status-dot" :class="statusClass(a.status)"></span>
            {{ statusLabel(a.status) }}
            <span v-if="!a.enabled" class="badge warning">выключен</span>
            <div v-if="a.status_message" class="muted">{{ a.status_message }}</div>
            <div v-if="a.status_hint" class="muted">{{ a.status_hint }}</div>
          </td>
          <td>
            <template v-if="risks[a.id]">
              <span class="status-dot" :class="RISK_CLASS[risks[a.id].level] || 'status-unknown'"></span>
              <strong>{{ risks[a.id].title }}</strong>
              <div class="muted">{{ risks[a.id].message }}</div>
            </template>
            <span v-else class="muted">—</span>
          </td>
          <td class="muted">
            {{ a.last_checked_at ? new Date(a.last_checked_at).toLocaleString() : '—' }}
          </td>
          <td>
            <select
              :value="a.proxy_id || ''"
              :disabled="proxyBusy"
              @change="assignProxy(a, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">Прямое подключение</option>
              <option v-for="p in proxies" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <div v-if="a.proxy_id" class="muted">{{ proxyName(a.proxy_id) }}</div>
          </td>
          <td>
            <div class="actions">
              <button :disabled="busyId === a.id" @click="check(a)">Проверить</button>
              <button :disabled="busyId === a.id" @click="toggle(a)">
                {{ a.enabled ? 'Выключить' : 'Включить' }}
              </button>
              <button :disabled="busyId === a.id" @click="logout(a)">Переавторизовать</button>
              <button class="danger" :disabled="busyId === a.id" @click="remove(a)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Network routes (proxies) -->
    <div class="card" style="margin-top: 20px">
      <h3>Сетевые маршруты (прокси)</h3>
      <p class="muted">
        Прокси — это обычный маршрут подключения для аккаунта. Он
        <strong>не отменяет</strong> ограничения Telegram (FloodWait, приватность,
        права администратора) и не помогает их обходить.
      </p>
      <div v-if="proxyError" class="error-text">{{ proxyError }}</div>
      <table v-if="proxies.length">
        <thead>
          <tr>
            <th>Название</th>
            <th>Тип</th>
            <th>Адрес</th>
            <th>Состояние</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in proxies" :key="p.id">
            <td><strong>{{ p.name }}</strong></td>
            <td class="muted">{{ p.kind_title }}</td>
            <td class="muted">{{ p.host }}:{{ p.port }}</td>
            <td>
              <span class="status-dot" :class="PROXY_STATUS_CLASS[p.status] || 'status-unknown'"></span>
              {{ p.status_title }}
              <div v-if="p.status_message" class="muted">{{ p.status_message }}</div>
            </td>
            <td>
              <div class="actions">
                <button :disabled="proxyBusy" @click="checkProxy(p)">Проверить</button>
                <button class="danger" :disabled="proxyBusy" @click="removeProxy(p)">Удалить</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">Прокси не настроены — все аккаунты подключаются напрямую.</p>

      <h4 style="margin-top: 16px">Добавить прокси</h4>
      <div class="grid">
        <label class="field">
          <span>Название</span>
          <input v-model="proxyForm.name" placeholder="Например: домашний" />
        </label>
        <label class="field">
          <span>Тип</span>
          <select v-model="proxyForm.kind">
            <option value="socks5">SOCKS5</option>
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
          </select>
        </label>
        <label class="field">
          <span>Адрес</span>
          <input v-model="proxyForm.host" placeholder="127.0.0.1" autocomplete="off" />
        </label>
        <label class="field">
          <span>Порт</span>
          <input v-model.number="proxyForm.port" type="number" placeholder="1080" />
        </label>
        <label class="field">
          <span>Логин (необязательно)</span>
          <input v-model="proxyForm.username" autocomplete="off" />
        </label>
        <label class="field">
          <span>Пароль (необязательно)</span>
          <input v-model="proxyForm.password" type="password" autocomplete="off" />
        </label>
      </div>
      <button
        class="primary"
        :disabled="proxyBusy || !proxyForm.host || !proxyForm.port"
        @click="addProxy"
      >
        {{ proxyBusy ? 'Сохраняем…' : 'Добавить прокси' }}
      </button>
    </div>

    <!-- Permission probe (post-1.0 hardening) -->
    <div class="card" style="margin-top: 20px">
      <h3>Проверка прав на канал</h3>
      <p class="muted">
        Перед приглашениями проверьте, что у аккаунта действительно есть доступ к целевому
        каналу: найдётся ли канал, виден ли список участников и можно ли приглашать.
      </p>
      <label class="field">
        <span>Аккаунт</span>
        <select v-model="permAccountId">
          <option value="">— выберите аккаунт —</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.username ? '@' + a.username : a.display_name || a.id }}
          </option>
        </select>
      </label>
      <label v-if="channels.length" class="field">
        <span>Канал из реестра (необязательно)</span>
        <select v-model="permChannelId">
          <option value="">Указать вручную ниже</option>
          <option v-for="c in channels" :key="c.id" :value="c.id">
            {{ c.title || c.reference }}
          </option>
        </select>
      </label>
      <label v-if="!permChannelId" class="field">
        <span>Целевой канал</span>
        <input v-model="permTarget" placeholder="@my_channel или ссылка" />
      </label>
      <div v-if="permError" class="error-text">{{ permError }}</div>
      <button
        class="primary"
        :disabled="permBusy || !permAccountId || (!permTarget && !permChannelId)"
        @click="runPermissionCheck"
      >
        {{ permBusy ? 'Проверяем…' : 'Проверить доступ' }}
      </button>

      <div v-if="permResult" style="margin-top: 16px">
        <p>
          <span
            class="status-dot"
            :class="
              permResult.status === 'ok'
                ? 'status-ok'
                : permResult.status === 'error' || permResult.status === 'no_access'
                  ? 'status-error'
                  : 'status-warning'
            "
          ></span>
          <strong>{{ permResult.status_label || permStatusLabel(permResult.status) }}</strong>
        </p>
        <p v-if="permResult.message">{{ permResult.message }}</p>
        <p v-if="permResult.how_to_fix" class="muted">
          Как исправить: {{ permResult.how_to_fix }}
        </p>
        <ul class="muted">
          <li>Канал найден: {{ permResult.channel_found ? 'да' : 'нет' }}</li>
          <li>Список участников доступен: {{ permResult.can_read_participants ? 'да' : 'нет' }}</li>
          <li>Можно приглашать: {{ permResult.can_invite ? 'да' : 'нет' }}</li>
          <li v-if="permResult.participants_count !== null">
            Участников: {{ permResult.participants_count }}
          </li>
          <li v-if="permResult.retry_after">Подождать: {{ permResult.retry_after }} сек.</li>
        </ul>
      </div>

      <div v-if="permHistory.length" style="margin-top: 12px">
        <h4>Последние проверки</h4>
        <ul class="muted">
          <li v-for="c in permHistory" :key="c.check_id ?? c.target">
            {{ c.target_title || c.target }} — {{ c.status_label || permStatusLabel(c.status) }}
            <span v-if="c.checked_at"> · {{ new Date(c.checked_at).toLocaleString() }}</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
