<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  ApiError,
  type Campaign,
  type CampaignDetail,
  type Channel,
  type DonorMetric,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const campaigns = ref<Campaign[]>([])
const riskModes = ref<Record<string, string>>({})
const channels = ref<Channel[]>([])
const donors = ref<DonorMetric[]>([])
const donorNote = ref('')
const detail = ref<CampaignDetail | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const showAdd = ref(false)
const form = ref({ name: '', channel_id: '', risk_mode: 'conservative', requires_approval: true })

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  active: 'Активна',
  paused: 'Пауза',
  completed: 'Завершена',
  disabled: 'Отключена',
}

const LINK_STATUS_LABELS: Record<string, string> = {
  active: 'Активна',
  revoked: 'Отозвана',
  expired: 'Истекла',
  error: 'Ошибка',
}

const QUALITY_LABELS: Record<string, string> = {
  good: 'Хороший источник',
  average: 'Средний',
  suspect: 'Похоже на накрутку',
  unknown: 'Недостаточно данных',
}

function friendly(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.hint ? `${e.message} ${e.hint}` : e.message
  return e instanceof Error ? e.message : fallback
}

function statusClass(status: string): string {
  if (status === 'active' || status === 'completed') return 'status-ok'
  if (status === 'paused' || status === 'draft') return 'status-warning'
  if (status === 'error' || status === 'disabled') return 'status-error'
  return 'status-unknown'
}

function qualityClass(quality: string): string {
  if (quality === 'good') return 'status-ok'
  if (quality === 'suspect') return 'status-error'
  if (quality === 'average') return 'status-warning'
  return 'status-unknown'
}

async function load(silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [list, chans] = await Promise.all([api.campaigns(), api.channels({ limit: '200' })])
    campaigns.value = list.items
    riskModes.value = list.risk_modes
    channels.value = chans.items
    try {
      const d = await api.donors()
      donors.value = d.items
      donorNote.value = d.note
    } catch {
      donors.value = []
    }
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить кампании.')
  } finally {
    loading.value = false
  }
}

async function createCampaign() {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await api.createCampaign({
      name: form.value.name,
      channel_id: form.value.channel_id,
      risk_mode: form.value.risk_mode,
      requires_approval: form.value.requires_approval,
    })
    notice.value = `Кампания «${created.name}» создана. Добавьте ссылку-приглашение.`
    form.value = { name: '', channel_id: '', risk_mode: 'conservative', requires_approval: true }
    showAdd.value = false
    await load(true)
  } catch (e) {
    error.value = friendly(e, 'Не удалось создать кампанию.')
  } finally {
    busy.value = false
  }
}

async function openDetail(campaign: Campaign) {
  try {
    detail.value = await api.campaign(campaign.id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось открыть кампанию.')
  }
}

async function addLink() {
  if (!detail.value) return
  busy.value = true
  error.value = ''
  try {
    await api.addCampaignLink(detail.value.campaign.id, { label: '' })
    notice.value = 'Ссылка-приглашение создана.'
    detail.value = await api.campaign(detail.value.campaign.id)
    await load(true)
  } catch (e) {
    error.value = friendly(e, 'Не удалось создать ссылку.')
  } finally {
    busy.value = false
  }
}

async function revokeLink(linkId: string) {
  if (!detail.value) return
  if (!confirm('Отозвать эту ссылку? По ней больше нельзя будет присоединиться.')) return
  busy.value = true
  try {
    await api.revokeCampaignLink(detail.value.campaign.id, linkId)
    detail.value = await api.campaign(detail.value.campaign.id)
  } catch (e) {
    error.value = friendly(e, 'Не удалось отозвать ссылку.')
  } finally {
    busy.value = false
  }
}

async function setStatus(campaign: Campaign, status: string) {
  busy.value = true
  error.value = ''
  try {
    await api.setCampaignStatus(campaign.id, status)
    await load(true)
    if (detail.value?.campaign.id === campaign.id) await openDetail(campaign)
  } catch (e) {
    error.value = friendly(e, 'Не удалось изменить состояние.')
  } finally {
    busy.value = false
  }
}

async function removeCampaign(campaign: Campaign) {
  if (!confirm(`Удалить кампанию «${campaign.name}»? Действие нельзя отменить.`)) return
  busy.value = true
  try {
    await api.deleteCampaign(campaign.id)
    if (detail.value?.campaign.id === campaign.id) detail.value = null
    notice.value = 'Кампания удалена.'
    await load(true)
  } catch (e) {
    error.value = friendly(e, 'Не удалось удалить кампанию.')
  } finally {
    busy.value = false
  }
}

async function analyzeDonors() {
  busy.value = true
  error.value = ''
  try {
    const result = await api.analyzeAllDonors()
    donors.value = result.items
    donorNote.value = result.note
    notice.value = 'Качество источников пересчитано.'
  } catch (e) {
    error.value = friendly(e, 'Не удалось проанализировать источники.')
  } finally {
    busy.value = false
  }
}

const channelLabel = computed(
  () => (c: Campaign) => {
    const found = channels.value.find((ch) => ch.id === c.channel_id)
    return found ? found.title || found.reference : c.target_title || '—'
  },
)

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Кампании приглашений <InfoHint topic="invites" /></h2>
    <p class="page-subtitle">
      Кампании работают по ссылкам-приглашениям и не требуют аккаунта Telegram.
      Управляющий бот создаёт ссылку, а вы видите переходы и заявки.
    </p>

    <div v-if="loading" class="card">Загрузка...</div>
    <div v-else-if="error && !campaigns.length" class="card error-text">{{ error }}</div>

    <template v-else>
      <div v-if="notice" class="card success-text">{{ notice }}</div>
      <div v-if="error" class="card error-text">{{ error }}</div>

      <div class="card">
        <div class="row space-between">
          <h3>Кампании ({{ campaigns.length }})</h3>
          <button class="primary" @click="showAdd = !showAdd">
            {{ showAdd ? 'Отмена' : 'Новая кампания' }}
          </button>
        </div>

        <div v-if="showAdd" class="add-form">
          <div class="row">
            <input v-model="form.name" type="text" placeholder="Название кампании" maxlength="120" />
            <select v-model="form.channel_id">
              <option value="">Канал не выбран</option>
              <option v-for="c in channels" :key="c.id" :value="c.id">
                {{ c.title || c.reference }}
              </option>
            </select>
          </div>
          <div class="row">
            <label>
              Режим риска:
              <select v-model="form.risk_mode">
                <option v-for="(label, key) in riskModes" :key="key" :value="key">
                  {{ label }}
                </option>
              </select>
            </label>
            <label class="checkbox">
              <input v-model="form.requires_approval" type="checkbox" />
              Заявки требуют подтверждения
            </label>
          </div>
          <p class="muted">
            Консервативный режим безопаснее: меньше действий в час и мягкие паузы. Это
            снижает риск ограничений Telegram.
          </p>
          <button class="primary" :disabled="busy || !form.name.trim()" @click="createCampaign">
            Создать
          </button>
        </div>

        <div v-if="!campaigns.length" class="empty">
          Пока нет кампаний. Создайте первую — это безопасно и не требует аккаунта.
        </div>

        <table v-else>
          <thead>
            <tr>
              <th>Название</th>
              <th>Состояние</th>
              <th>Канал</th>
              <th>Ссылок</th>
              <th>Переходов</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in campaigns" :key="c.id">
              <td><strong>{{ c.name }}</strong></td>
              <td>
                <span class="badge" :class="statusClass(c.status)">
                  {{ STATUS_LABELS[c.status] || c.status }}
                </span>
              </td>
              <td>{{ channelLabel(c) }}</td>
              <td>{{ c.links_count }}</td>
              <td>{{ c.joins_count }}</td>
              <td class="actions">
                <button :disabled="busy" @click="openDetail(c)">Открыть</button>
                <button
                  v-if="c.status === 'active'"
                  :disabled="busy"
                  @click="setStatus(c, 'paused')"
                >
                  Пауза
                </button>
                <button
                  v-else-if="c.status !== 'completed'"
                  :disabled="busy"
                  @click="setStatus(c, 'active')"
                >
                  Запустить
                </button>
                <button class="danger" :disabled="busy" @click="removeCampaign(c)">Удалить</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="detail" class="card">
        <div class="row space-between">
          <h3>Кампания «{{ detail.campaign.name }}»</h3>
          <button @click="detail = null">Закрыть</button>
        </div>
        <p class="muted">{{ detail.campaign.summary }}</p>
        <p class="muted">
          Заявок в ожидании: {{ detail.requests_pending }} · одобрено: {{ detail.requests_approved }}
        </p>
        <div class="row">
          <button class="primary" :disabled="busy" @click="addLink">Создать ссылку</button>
        </div>
        <div v-if="!detail.links.length" class="empty">
          Ссылок пока нет. Создайте первую кнопкой выше.
        </div>
        <table v-else>
          <thead>
            <tr>
              <th>Ссылка</th>
              <th>Состояние</th>
              <th>Переходов</th>
              <th>Заявок</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in detail.links" :key="l.id">
              <td class="mono">{{ l.link || '—' }}</td>
              <td>{{ LINK_STATUS_LABELS[l.status] || l.status }}</td>
              <td>{{ l.joins_count }}</td>
              <td>{{ l.requests_count }}</td>
              <td>
                <button
                  v-if="l.status === 'active'"
                  class="danger"
                  :disabled="busy"
                  @click="revokeLink(l.id)"
                >
                  Отозвать
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <div class="row space-between">
          <h3>Качество источников</h3>
          <button :disabled="busy" @click="analyzeDonors">Пересчитать</button>
        </div>
        <p class="muted">{{ donorNote }}</p>
        <div v-if="!donors.length" class="empty">Источников пока нет.</div>
        <table v-else>
          <thead>
            <tr>
              <th>Источник</th>
              <th>Оценка</th>
              <th>Доля ботов</th>
              <th>Уверенность</th>
              <th>Пояснение</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in donors" :key="d.id">
              <td><strong>{{ d.title || d.source_id }}</strong></td>
              <td>
                <span class="badge" :class="qualityClass(d.quality)">
                  {{ QUALITY_LABELS[d.quality] || d.quality }}
                </span>
              </td>
              <td>
                {{ d.bot_share_estimate === null ? 'не измерено' : Math.round(d.bot_share_estimate * 100) + '%' }}
              </td>
              <td>{{ d.confidence }}</td>
              <td class="muted">{{ d.summary }}</td>
            </tr>
          </tbody>
        </table>
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
.status-ok {
  background: rgba(46, 160, 67, 0.15);
}
.status-warning {
  background: rgba(210, 153, 34, 0.2);
}
.status-error {
  background: rgba(180, 35, 24, 0.15);
}
.status-unknown {
  background: rgba(120, 120, 120, 0.15);
}
.add-form {
  border-top: 1px solid var(--border, #e5e7eb);
  margin-top: 0.75rem;
  padding-top: 0.75rem;
}
.mono {
  font-family: monospace;
  font-size: 0.85rem;
}
.success-text {
  color: #17663a;
}
.btn.danger {
  color: #b42318;
}
</style>
