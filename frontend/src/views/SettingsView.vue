<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type Setting } from '@/api/client'

const settings = ref<Setting[]>([])
const loading = ref(true)
const error = ref('')
const saved = ref(false)

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
  </div>
</template>
