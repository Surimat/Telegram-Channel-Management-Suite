<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type SyncRestorePreview, type SyncStatus } from '@/api/client'
import { useOwnerStore } from '@/stores/owner'
import InfoHint from '@/components/InfoHint.vue'

const owner = useOwnerStore()

// Setup / login form
const secret = ref('')
const confirm = ref('')
const displayName = ref('')
const method = ref('password')
const recoveryHint = ref('')
const busy = ref(false)
const localError = ref('')
const notice = ref('')

// Change password
const currentSecret = ref('')
const newSecret = ref('')

// Config sync
const sync = ref<SyncStatus | null>(null)
const syncSecret = ref('')
const syncBusy = ref(false)
const syncNotice = ref('')
const syncError = ref('')
const preview = ref<SyncRestorePreview | null>(null)
const provider = ref('local')
const showAdvanced = ref(false)

const stateClass = computed(() => {
  if (!owner.status?.exists) return 'badge-muted'
  return owner.status.enabled ? 'badge ok' : 'badge warning'
})

const protectionLabel = computed(() => {
  if (!owner.status?.exists) return 'Профиль не создан'
  return owner.status.enabled ? 'Защита включена' : 'Защита выключена'
})

function shortSecret(): boolean {
  return secret.value.trim().length < 4
}

async function createProfile() {
  localError.value = ''
  notice.value = ''
  if (shortSecret()) {
    localError.value = 'Пароль слишком короткий: минимум 4 символа.'
    return
  }
  if (secret.value !== confirm.value) {
    localError.value = 'Пароли не совпадают.'
    return
  }
  busy.value = true
  try {
    await owner.setup(secret.value, method.value, displayName.value, recoveryHint.value)
    secret.value = ''
    confirm.value = ''
    notice.value = 'Профиль владельца создан. Панель защищена этим паролем.'
    await loadSync()
  } catch {
    // owner.error/hint carry the friendly message.
  } finally {
    busy.value = false
  }
}

async function signIn() {
  localError.value = ''
  notice.value = ''
  busy.value = true
  try {
    await owner.login(secret.value)
    secret.value = ''
    notice.value = 'Вход выполнен.'
    await loadSync()
  } catch {
    // handled by the store
  } finally {
    busy.value = false
  }
}

async function changePassword() {
  localError.value = ''
  notice.value = ''
  busy.value = true
  try {
    await api.ownerChangePassword(currentSecret.value, newSecret.value)
    currentSecret.value = ''
    newSecret.value = ''
    notice.value = 'Пароль изменён.'
  } catch (e) {
    localError.value = e instanceof Error ? e.message : 'Не удалось изменить пароль.'
  } finally {
    busy.value = false
  }
}

async function toggleProtection() {
  if (!owner.status) return
  await owner.setProtection(!owner.status.enabled)
}

async function signOut() {
  await owner.logout()
  notice.value = 'Вы вышли. Панель снова требует вход.'
}

async function loadSync() {
  try {
    sync.value = await api.syncStatus()
  } catch {
    sync.value = null
  }
}

async function configureSync() {
  syncError.value = ''
  syncNotice.value = ''
  syncBusy.value = true
  try {
    sync.value = await api.syncConfigure(provider.value, true)
    syncNotice.value = 'Способ синхронизации сохранён.'
  } catch (e) {
    syncError.value = e instanceof Error ? e.message : 'Не удалось сохранить настройку.'
  } finally {
    syncBusy.value = false
  }
}

async function uploadBundle() {
  syncError.value = ''
  syncNotice.value = ''
  preview.value = null
  syncBusy.value = true
  try {
    sync.value = await api.syncUpload(syncSecret.value)
    syncNotice.value = 'Настройки выгружены (зашифрованный пакет).'
  } catch (e) {
    syncError.value = e instanceof Error ? e.message : 'Не удалось выгрузить настройки.'
  } finally {
    syncBusy.value = false
  }
}

async function previewBundle() {
  syncError.value = ''
  syncNotice.value = ''
  syncBusy.value = true
  try {
    preview.value = await api.syncDownloadPreview(syncSecret.value)
  } catch (e) {
    syncError.value = e instanceof Error ? e.message : 'Не удалось прочитать пакет настроек.'
  } finally {
    syncBusy.value = false
  }
}

async function applyBundle() {
  syncBusy.value = true
  syncError.value = ''
  try {
    sync.value = await api.syncDownloadApply(syncSecret.value, false)
    syncNotice.value = 'Настройки применены.'
    preview.value = null
  } catch (e) {
    syncError.value = e instanceof Error ? e.message : 'Не удалось применить настройки.'
  } finally {
    syncBusy.value = false
  }
}

async function googleConnect() {
  syncError.value = ''
  try {
    const auth = await api.syncGoogleAuth()
    if (!auth.configured) {
      syncError.value =
        'Google Drive не настроен. Укажите Client ID и Client Secret в настройках приложения.'
      return
    }
    window.open(auth.authorization_url, '_blank', 'noopener')
    syncNotice.value =
      'Откройте ссылку, разрешите доступ и вставьте полученный токен ниже (дополнительно).'
    showAdvanced.value = true
  } catch (e) {
    syncError.value = e instanceof Error ? e.message : 'Не удалось начать вход в Google.'
  }
}

onMounted(async () => {
  await owner.refresh()
  await loadSync()
})
</script>

<template>
  <div>
    <h2 class="page-title">Владелец <InfoHint topic="owner_auth" /></h2>
    <p class="page-subtitle">
      Владелец — это вы. Пароль владельца защищает панель на этом компьютере и служит ключом
      для переноса настроек. Он не связан с вашим Telegram-аккаунтом.
    </p>

    <div v-if="owner.error" class="card error-text">{{ owner.error }}</div>
    <div v-if="owner.hint" class="card muted">{{ owner.hint }}</div>
    <div v-if="localError" class="card error-text">{{ localError }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div v-if="owner.loading" class="card">Загрузка…</div>

    <template v-else>
      <!-- Profile status -->
      <div class="card">
        <h3>Профиль владельца</h3>
        <p>
          Состояние:
          <span :class="stateClass">{{ protectionLabel }}</span>
        </p>
        <p v-if="owner.status?.exists" class="muted">
          Способ: {{ owner.status.method_title || 'пароль' }}
          <span v-if="owner.status.display_name"> · {{ owner.status.display_name }}</span>
          <span v-if="owner.status.locked"> · временно заблокировано</span>
        </p>
        <p class="muted">{{ owner.status?.local_only_note }}</p>
        <div v-if="owner.status?.exists" class="actions">
          <button v-if="owner.status.enabled" @click="toggleProtection">
            Выключить защиту панели
          </button>
          <button v-else @click="toggleProtection">Включить защиту панели</button>
          <button class="danger" @click="signOut">Выйти</button>
        </div>
      </div>

      <!-- Setup (no profile yet) -->
      <div v-if="!owner.status?.exists" class="card">
        <h3>Создать профиль владельца</h3>
        <p class="muted">
          Пока профиль не создан, панель открыта — как и раньше. После создания панель будет
          просить этот пароль.
        </p>
        <label class="field">
          <span>Пароль (минимум 4 символа)</span>
          <input v-model="secret" type="password" autocomplete="new-password" />
        </label>
        <label class="field">
          <span>Повторите пароль</span>
          <input v-model="confirm" type="password" autocomplete="new-password" />
        </label>
        <label class="field">
          <span>Способ</span>
          <select v-model="method">
            <option value="password">Пароль</option>
            <option value="pin">PIN-код</option>
          </select>
        </label>
        <label class="field">
          <span>Имя (необязательно)</span>
          <input v-model="displayName" />
        </label>
        <label class="field">
          <span>Напоминание (не пароль)</span>
          <input v-model="recoveryHint" />
        </label>
        <p class="muted">
          Пароль нигде не хранится в открытом виде. Забытый пароль восстановить нельзя —
          профиль можно удалить и создать заново.
        </p>
        <button class="primary" :disabled="busy" @click="createProfile">
          {{ busy ? 'Создаём…' : 'Создать профиль' }}
        </button>
      </div>

      <!-- Login (profile exists, not authenticated) -->
      <div v-else-if="owner.needsLogin" class="card">
        <h3>Вход владельца</h3>
        <p class="muted">Введите пароль владельца, чтобы пользоваться панелью.</p>
        <label class="field">
          <span>Пароль</span>
          <input v-model="secret" type="password" autocomplete="current-password" />
        </label>
        <button class="primary" :disabled="busy" @click="signIn">
          {{ busy ? 'Проверяем…' : 'Войти' }}
        </button>
      </div>

      <!-- Change password (profile exists, authenticated) -->
      <div v-else class="card">
        <h3>Сменить пароль</h3>
        <label class="field">
          <span>Текущий пароль</span>
          <input v-model="currentSecret" type="password" autocomplete="current-password" />
        </label>
        <label class="field">
          <span>Новый пароль</span>
          <input v-model="newSecret" type="password" autocomplete="new-password" />
        </label>
        <button :disabled="busy" @click="changePassword">Сменить пароль</button>
      </div>

      <!-- Config sync -->
      <div v-if="owner.status?.exists && owner.authenticated" class="card">
        <h3>Перенос настроек между компьютерами <InfoHint topic="config_sync" /></h3>
        <p class="muted">{{ sync?.no_live_db_note }}</p>
        <p v-if="sync" class="muted">
          Состояние:
          <span class="badge" :class="sync.state === 'available' ? 'ok' : 'badge-muted'">
            {{ sync.state_label }}
          </span>
          · способ: {{ sync.provider_label }} · устройство: {{ sync.device_name || 'этот компьютер' }}
        </p>
        <p v-if="sync?.cloud_updated_at" class="muted">
          Последняя копия: {{ new Date(sync.cloud_updated_at).toLocaleString('ru-RU') }}
          <span v-if="sync.cloud_device"> · {{ sync.cloud_device }}</span>
        </p>
        <p v-if="sync?.message" class="muted">{{ sync.message }}</p>
        <p v-if="sync?.conflict" class="error-text">
          Обнаружен конфликт версий: облако новее. Выгрузите свои настройки или сначала
          просмотрите и примените облачные.
        </p>

        <label class="field">
          <span>Способ переноса</span>
          <select v-model="provider">
            <option value="local">Локальная папка</option>
            <option value="google_drive">Google Drive</option>
          </select>
        </label>
        <div class="actions">
          <button :disabled="syncBusy" @click="configureSync">Сохранить способ</button>
          <button :disabled="syncBusy" @click="googleConnect">Подключить Google Drive</button>
        </div>

        <p class="muted">
          {{ sync?.appdata_scope_note }}
        </p>
        <label class="field">
          <span>Пароль владельца (для шифрования пакета)</span>
          <input v-model="syncSecret" type="password" autocomplete="current-password" />
        </label>
        <div class="actions">
          <button class="primary" :disabled="syncBusy" @click="uploadBundle">
            Выгрузить настройки
          </button>
          <button :disabled="syncBusy" @click="previewBundle">Просмотреть облачные</button>
          <button class="danger" :disabled="syncBusy || !preview" @click="applyBundle">
            Применить облачные
          </button>
        </div>
        <div v-if="syncError" class="error-text">{{ syncError }}</div>
        <div v-if="syncNotice" class="success-text">{{ syncNotice }}</div>

        <div v-if="preview" class="inline-note">
          <p>
            <strong>Пакет настроек</strong> (версия {{ preview.revision }}) от
            {{ preview.device_name || preview.device_id }}.
          </p>
          <p class="muted">
            Настроек: {{ Object.keys(preview.settings).length }} ·
            ботов: {{ preview.bot_count }} · каналов: {{ preview.channel_count }}
          </p>
          <p v-if="preview.differing.length" class="muted">
            Отличаются: {{ preview.differing.join(', ') }}
          </p>
          <p class="muted">
            Секреты (пароли, токены, session, TDATA) в пакет не попадают — они не копируются
            между компьютерами.
          </p>
        </div>
      </div>
    </template>
  </div>
</template>
