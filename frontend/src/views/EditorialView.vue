<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  api,
  type EditorialAudit,
  type EditorialBoard,
  type EditorialMember,
  type EditorialRoom,
} from '@/api/client'
import InfoHint from '@/components/InfoHint.vue'

const rooms = ref<EditorialRoom[]>([])
const channels = ref<{ id: string; title: string; reference: string }[]>([])
const bots = ref<{ id: string; title: string; username: string }[]>([])

const activeRoom = ref<EditorialRoom | null>(null)
const board = ref<EditorialBoard | null>(null)
const members = ref<EditorialMember[]>([])
const audit = ref<EditorialAudit[]>([])

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const newRoom = ref({ channel_id: '', group_chat_id: '', bot_id: '', group_title: '' })
const newMember = ref({ telegram_user_id: '', role: 'editor', display_name: '' })

// Columns the board shows, in workflow order (the suite owns this order).
const COLUMN_ORDER = ['inbox', 'editing', 'review', 'scheduled', 'published', 'failed']

const ROOM_CLASS: Record<string, string> = {
  ready: 'status-ok',
  needs_rights: 'status-warning',
  not_connected: 'status-unknown',
  error: 'status-error',
}

function friendly(e: unknown, fallback: string): string {
  const err = e as { message?: string; hint?: string }
  return [err?.message, err?.hint].filter(Boolean).join(' ') || fallback
}

const activeColumns = computed(() => {
  if (!board.value) return []
  return COLUMN_ORDER.filter((key) => board.value!.columns[key]).map((key) => ({
    key,
    title: board.value!.status_titles[key] || key,
    items: board.value!.columns[key] || [],
  }))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [roomList, channelList, botList] = await Promise.all([
      api.editorialRooms(),
      api.channels(),
      api.bots(),
    ])
    rooms.value = roomList.items
    channels.value = channelList.items ?? []
    bots.value = botList
    if (rooms.value.length && !activeRoom.value) {
      await selectRoom(rooms.value[0])
    }
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить редакционные комнаты.')
  } finally {
    loading.value = false
  }
}

async function selectRoom(room: EditorialRoom) {
  activeRoom.value = room
  await refreshRoom()
}

async function refreshRoom() {
  if (!activeRoom.value) return
  try {
    const [b, m, a] = await Promise.all([
      api.editorialBoard(activeRoom.value.id),
      api.editorialMembers(activeRoom.value.id),
      api.editorialAudit(activeRoom.value.id),
    ])
    board.value = b
    members.value = m
    audit.value = a
  } catch (e) {
    error.value = friendly(e, 'Не удалось загрузить очередь.')
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
    if (activeRoom.value) await refreshRoom()
  } catch (e) {
    error.value = friendly(e, 'Операция не выполнена.')
  } finally {
    busy.value = false
  }
}

const createRoom = () =>
  run(
    () =>
      api.createEditorialRoom({
        channel_id: newRoom.value.channel_id,
        group_chat_id: Number(newRoom.value.group_chat_id),
        bot_id: newRoom.value.bot_id,
        group_title: newRoom.value.group_title,
      }),
    'Комната создана. Проверьте права бота.',
  )

const checkRoom = () =>
  activeRoom.value &&
  run(() => api.checkEditorialRoom(activeRoom.value!.id), 'Проверка выполнена.')

const addMember = () =>
  activeRoom.value &&
  run(
    () =>
      api.setEditorialMember(activeRoom.value!.id, {
        telegram_user_id: Number(newMember.value.telegram_user_id),
        role: newMember.value.role,
        display_name: newMember.value.display_name,
      }),
    'Роль сохранена.',
  )

const removeMember = (userId: number) =>
  activeRoom.value &&
  run(() => api.removeEditorialMember(activeRoom.value!.id, userId), 'Участник удалён.')

const move = (itemId: string, status: string) =>
  activeRoom.value &&
  run(
    () => api.editorialMove(activeRoom.value!.id, itemId, { status }),
    'Материал перемещён.',
  )

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Редакционная комната
      <InfoHint topic="editorial_workspace" />
    </h2>
    <p class="page-subtitle">
      Командная работа над очередью публикаций в Telegram-супергруппе с темами.
      Панель владеет очередью и порядком; темы только отражают статусы.
      Права бота проверяются по-настоящему — «Готова» появляется только после
      подтверждения от Telegram.
    </p>

    <div v-if="error" class="card error-text">{{ error }}</div>
    <div v-if="notice" class="card muted">{{ notice }}</div>

    <div v-if="loading" class="card">Загрузка…</div>

    <template v-else>
      <div class="card">
        <h3>Новая комната</h3>
        <div class="grid">
          <label class="field">
            <span>Канал</span>
            <select v-model="newRoom.channel_id">
              <option value="">— выберите канал —</option>
              <option v-for="c in channels" :key="c.id" :value="c.id">
                {{ c.title || c.reference }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>ID группы редакции (супергруппа с темами)</span>
            <input v-model="newRoom.group_chat_id" type="text" placeholder="-100…" />
          </label>
          <label class="field">
            <span>Бот</span>
            <select v-model="newRoom.bot_id">
              <option value="">— управляющий бот —</option>
              <option v-for="b in bots" :key="b.id" :value="b.id">
                {{ b.title || b.username || b.id }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>Название группы</span>
            <input v-model="newRoom.group_title" type="text" />
          </label>
        </div>
        <p>
          <button class="primary" :disabled="busy || !newRoom.channel_id" @click="createRoom">
            Создать комнату
          </button>
        </p>
      </div>

      <div class="card">
        <h3>Комнаты</h3>
        <p v-if="!rooms.length" class="muted">Пока нет ни одной комнаты.</p>
        <ul v-else class="room-list">
          <li
            v-for="room in rooms"
            :key="room.id"
            class="room-row"
            :class="{ active: activeRoom && activeRoom.id === room.id }"
          >
            <button class="link" @click="selectRoom(room)">
              {{ room.channel_label || room.channel_id }}
            </button>
            <span :class="ROOM_CLASS[room.status] || 'status-unknown'">
              {{ room.status_label }}
            </span>
            <span class="muted">{{ room.group_title }}</span>
          </li>
        </ul>
      </div>

      <div v-if="activeRoom" class="card">
        <h3>Комната «{{ activeRoom.channel_label }}»</h3>
        <p>
          Статус:
          <strong :class="ROOM_CLASS[activeRoom.status] || 'status-unknown'">
            {{ activeRoom.status_label }}
          </strong>
        </p>
        <p class="muted">
          Бот в группе: {{ activeRoom.bot_is_member ? 'да' : 'нет' }} ·
          отправка сообщений: {{ activeRoom.can_send_messages ? 'да' : 'нет' }} ·
          управление темами: {{ activeRoom.can_manage_topics ? 'да' : 'нет' }}
        </p>
        <p v-if="activeRoom.last_error" class="error-text">{{ activeRoom.last_error }}</p>
        <p>
          <button class="primary" :disabled="busy" @click="checkRoom">
            Проверить права и создать темы
          </button>
        </p>
      </div>

      <div v-if="board" class="card">
        <h3>Очередь публикаций</h3>
        <div class="board">
          <div v-for="column in activeColumns" :key="column.key" class="board-column">
            <h4>{{ column.title }} ({{ column.items.length }})</h4>
            <div v-for="item in column.items" :key="item.id" class="board-card">
              <strong>{{ item.title || item.content_item_id }}</strong>
              <div class="muted">№ {{ item.order_index }}</div>
              <div v-if="item.error" class="error-text">{{ item.error }}</div>
              <div class="actions">
                <button
                  v-for="action in item.available_actions"
                  :key="action"
                  class="small"
                  :disabled="busy"
                  @click="move(item.id, action)"
                >
                  {{ action }}
                </button>
              </div>
            </div>
            <p v-if="!column.items.length" class="muted">Пусто</p>
          </div>
        </div>
      </div>

      <div v-if="activeRoom" class="card">
        <h3>Участники и роли</h3>
        <p class="muted">
          Роли выдаются по числовому Telegram ID (username не является идентификатором).
        </p>
        <ul>
          <li v-for="m in members" :key="m.id">
            {{ m.display_name || m.username || m.telegram_user_id }} — {{ m.role_title }}
            <button class="small" :disabled="busy" @click="removeMember(m.telegram_user_id)">
              Удалить
            </button>
          </li>
        </ul>
        <div class="grid">
          <label class="field">
            <span>Telegram ID</span>
            <input v-model="newMember.telegram_user_id" type="text" />
          </label>
          <label class="field">
            <span>Роль</span>
            <select v-model="newMember.role">
              <option value="editor">Редактор</option>
              <option value="moderator">Модератор</option>
              <option value="viewer">Наблюдатель</option>
            </select>
          </label>
          <label class="field">
            <span>Имя</span>
            <input v-model="newMember.display_name" type="text" />
          </label>
        </div>
        <p>
          <button class="primary" :disabled="busy || !newMember.telegram_user_id" @click="addMember">
            Сохранить роль
          </button>
        </p>
      </div>

      <div v-if="audit.length" class="card">
        <h3>Журнал действий</h3>
        <ul>
          <li v-for="entry in audit" :key="entry.id">
            {{ entry.actor_name || entry.actor_telegram_id }} — {{ entry.action }}
            <span class="muted">{{ entry.old_status }} → {{ entry.new_status }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.room-list {
  list-style: none;
  padding: 0;
}
.room-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 6px 0;
}
.room-row.active {
  font-weight: 600;
}
.link {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
.board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
}
.board-column {
  min-width: 200px;
  flex: 1;
}
.board-card {
  border: 1px solid rgba(128, 128, 128, 0.3);
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 8px;
}
.actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
