// Mini App authentication state. In a normal browser this stays inert; inside
// Telegram it verifies initData once and remembers the result for the session.
import { defineStore } from 'pinia'
import { api, ApiError, type MiniAppUser } from '@/api/client'
import { getTelegramWebApp, initTelegramWebApp, isTelegramMiniApp } from '@/telegram'

interface MiniAppState {
  inTelegram: boolean
  loading: boolean
  authenticated: boolean
  isAdmin: boolean
  user: MiniAppUser | null
  error: string
  hint: string
  reason: string
}

export const useMiniAppStore = defineStore('miniapp', {
  state: (): MiniAppState => ({
    inTelegram: false,
    loading: false,
    authenticated: false,
    isAdmin: false,
    user: null,
    error: '',
    hint: '',
    reason: '',
  }),
  actions: {
    async bootstrap() {
      initTelegramWebApp()
      this.inTelegram = isTelegramMiniApp()
      if (!this.inTelegram) return

      this.loading = true
      this.error = ''
      try {
        const config = await api.miniappConfig()
        this.reason = config.reason
        if (!config.available) {
          this.error = config.reason
          this.hint = config.how_to_fix
          return
        }
        const initData = getTelegramWebApp()?.initData ?? ''
        const result = await api.miniappAuth(initData)
        this.authenticated = result.authenticated
        this.isAdmin = result.is_admin
        this.user = result.user
      } catch (e) {
        if (e instanceof ApiError) {
          this.error = e.message
          this.hint = e.hint
        } else {
          this.error = 'Не удалось войти через Telegram.'
        }
      } finally {
        this.loading = false
      }
    },
    async logout() {
      try {
        await api.miniappLogout()
      } catch {
        // Ignore: the local session cookie is cleared server-side best-effort.
      }
      this.authenticated = false
      this.user = null
    },
  },
})
