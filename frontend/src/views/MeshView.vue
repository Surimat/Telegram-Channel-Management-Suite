<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  api,
  type MeshLease,
  type MeshPeer,
  type MeshStatus,
  type PairingCode,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const status = ref<MeshStatus | null>(null)
const peers = ref<MeshPeer[]>([])
const leases = ref<MeshLease[]>([])
const pairing = ref<PairingCode | null>(null)

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const manual = ref({ host: '', port: 8001, name: '' })
const pairForm = ref({ code: '', node_id: '', host: '', port: 0, name: '' })

const CAP_LABELS: Record<string, string> = {
  telegram: 'Telegram',
  media: 'Медиа',
  ai: 'Мини-ИИ',
  backup: 'Резервные копии',
  rss: 'RSS',
  web: 'Веб',
}

const STATUS_CLASS: Record<string, string> = {
  online: 'status-ok',
  busy: 'status-warning',
  offline: 'status-error',
  unknown: 'status-unknown',
}

function friendly(e: unknown, fallback: string): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = await api.meshStatus()
    const [p, l] = await Promise.all([api.meshPeers(), api.meshLeases()])
    peers.value = p.items
    leases.value = l.items
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить состояние сети.')
  } finally {
    loading.value = false
  }
}

async function run(fn: () => Promise<unknown>, message = '') {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await fn()
    if (message) notice.value = message
    await load()
  } catch (e) {
    error.value = friendly(e, 'Операция не выполнена.')
  } finally {
    busy.value = false
  }
}

const discover = () => run(() => api.meshDiscover(), 'Поиск завершён.')
const makeCode = () =>
  run(async () => {
    pairing.value = await api.meshPairingCode()
  }, 'Код создан. Покажите его на другом компьютере.')
const addManual = () =>
  run(
    () =>
      api.meshAddPeer({
        host: manual.value.host,
        port: Number(manual.value.port),
        name: manual.value.name,
      }),
    'Компьютер добавлен. Подтвердите сопряжение.',
  )
const pair = () =>
  run(async () => {
    await api.meshPair({ ...pairForm.value, port: Number(pairForm.value.port) })
    pairForm.value = { code: '', node_id: '', host: '', port: 0, name: '' }
    pairing.value = null
  }, 'Компьютер сопряжён.')
const unpair = (peer: MeshPeer) => {
  if (!confirm(`Отключить компьютер «${peer.name || peer.host}»?`)) return
  return run(() => api.meshUnpair(peer.id))
}
const probe = (peer: MeshPeer) => run(() => api.meshProbe(peer.id))
const elect = () => run(() => api.meshElect(), 'Выбор главного компьютера выполнен.')

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Компьютеры (LAN Mesh) <InfoHint topic="lan_mesh" /></h2>
    <p class="page-subtitle">
      Необязательный режим: несколько ваших компьютеров в одной локальной сети
      работают вместе без облачного сервера. По умолчанию всё работает на одном
      компьютере — этот раздел нужен, только если вы хотите объединить несколько.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card success-text">{{ notice }}</div>

    <div v-if="loading" class="card">Загрузка…</div>
    <template v-else-if="status">
      <div class="grid">
        <div class="card">
          <strong>Этот компьютер</strong>
          <p>{{ status.name }}</p>
          <p class="muted">Роль: {{ status.role === 'coordinator' ? 'Главный' : status.role === 'worker' ? 'Рабочий' : 'Один компьютер' }}</p>
          <p class="muted">Режим: {{ status.mode_label }}</p>
        </div>
        <div class="card">
          <strong>Возможности</strong>
          <p class="muted">
            <span v-for="c in status.capabilities" :key="c" class="badge">{{ CAP_LABELS[c] || c }}</span>
          </p>
          <p class="muted">Компьютеров: {{ status.peers_total }} · доверенных: {{ status.peers_trusted }} · в сети: {{ status.peers_online }}</p>
        </div>
      </div>
      <div class="card inline-note">{{ status.note }}</div>

      <div class="toolbar">
        <button :disabled="busy" @click="discover">Найти компьютеры</button>
        <button :disabled="busy" @click="makeCode">Показать код сопряжения</button>
        <button :disabled="busy" @click="elect">Выбрать главный компьютер</button>
        <button :disabled="busy" @click="load">Обновить</button>
      </div>

      <div v-if="pairing" class="card">
        <h3>Код сопряжения</h3>
        <p class="muted">Покажите этот код на другом компьютере и введите его там.</p>
        <p><code style="font-size: 1.4rem">{{ pairing.code }}</code></p>
      </div>

      <div class="grid">
        <div class="card">
          <h3>Добавить компьютер вручную</h3>
          <p class="muted">Если автоматический поиск не работает из-за настроек сети.</p>
          <label class="field">
            <span>Адрес</span>
            <input v-model="manual.host" placeholder="192.168.1.20" />
          </label>
          <label class="field">
            <span>Порт</span>
            <input v-model.number="manual.port" type="number" />
          </label>
          <label class="field">
            <span>Имя (необязательно)</span>
            <input v-model="manual.name" placeholder="Ноутбук" />
          </label>
          <button :disabled="busy || !manual.host" @click="addManual">Добавить</button>
        </div>

        <div class="card">
          <h3>Сопряжение по коду</h3>
          <p class="muted">Введите код, показанный на другом компьютере.</p>
          <label class="field">
            <span>Код</span>
            <input v-model="pairForm.code" placeholder="ABCD2345" />
          </label>
          <label class="field">
            <span>Адрес (необязательно)</span>
            <input v-model="pairForm.host" placeholder="192.168.1.20" />
          </label>
          <label class="field">
            <span>Порт (необязательно)</span>
            <input v-model.number="pairForm.port" type="number" />
          </label>
          <button :disabled="busy || !pairForm.code" @click="pair">Сопрячь</button>
        </div>
      </div>

      <h3>Компьютеры</h3>
      <div v-if="peers.length === 0" class="card empty">
        Пока нет подключённых компьютеров. Это нормально: приложение работает и без них.
      </div>
      <table v-else>
        <thead>
          <tr>
            <th>Компьютер</th>
            <th>Адрес</th>
            <th>Возможности</th>
            <th>Статус</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in peers" :key="p.id">
            <td>
              <strong>{{ p.name || '—' }}</strong>
              <div class="muted">{{ p.trusted ? 'доверенный' : 'не сопряжён' }}</div>
            </td>
            <td class="muted">{{ p.host }}:{{ p.port }}</td>
            <td class="muted">
              <span v-for="c in p.capabilities" :key="c" class="badge">{{ CAP_LABELS[c] || c }}</span>
            </td>
            <td>
              <span class="status-dot" :class="STATUS_CLASS[p.status] || 'status-unknown'"></span>
              {{ p.status_label }}
            </td>
            <td>
              <div class="actions">
                <button :disabled="busy" @click="probe(p)">Проверить</button>
                <button class="danger" :disabled="busy" @click="unpair(p)">Отключить</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <h3>Задачи (аренда)</h3>
      <p class="muted">
        Каждая задача выполняется ровно на одном компьютере. Если он выключится,
        задача вернётся и её подхватит другой — без потери результата.
      </p>
      <div v-if="leases.length === 0" class="card empty">Активных задач нет.</div>
      <table v-else>
        <thead>
          <tr>
            <th>Задача</th>
            <th>Тип</th>
            <th>Исполнитель</th>
            <th>До</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in leases" :key="l.id">
            <td>{{ l.job_id }}</td>
            <td>{{ l.kind || '—' }}</td>
            <td class="muted">{{ l.lease_owner }}</td>
            <td class="muted">{{ l.lease_until ? new Date(l.lease_until).toLocaleTimeString() : '—' }}</td>
            <td>{{ l.status }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>
