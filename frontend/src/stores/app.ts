import { defineStore } from 'pinia'
import { api, type SystemStatus } from '@/api/client'

interface AppState {
  status: SystemStatus | null
  loading: boolean
  error: string
  language: string
}

export const useAppStore = defineStore('app', {
  state: (): AppState => ({
    status: null,
    loading: false,
    error: '',
    language: 'ru',
  }),
  actions: {
    async loadStatus() {
      this.loading = true
      this.error = ''
      try {
        this.status = await api.systemStatus()
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Не удалось получить состояние системы.'
      } finally {
        this.loading = false
      }
    },
  },
})
