// Owner Auth state (v1.6). Local-first: the panel stays open until an owner
// profile exists and protection is on. The token lives in sessionStorage and is
// never the password; it is cleared on logout and when the server rejects it.
import { defineStore } from 'pinia'
import { api, ApiError, getOwnerToken, setOwnerToken, type OwnerStatus } from '@/api/client'

interface OwnerState {
  status: OwnerStatus | null
  loading: boolean
  error: string
  hint: string
  authenticated: boolean
}

export const useOwnerStore = defineStore('owner', {
  state: (): OwnerState => ({
    status: null,
    loading: false,
    error: '',
    hint: '',
    authenticated: false,
  }),
  getters: {
    /** True when the app requires a token and this browser does not hold one. */
    needsLogin(state): boolean {
      return Boolean(state.status?.auth_required) && !state.authenticated
    },
  },
  actions: {
    async refresh() {
      this.loading = true
      this.error = ''
      try {
        this.status = await api.ownerStatus()
        // A profile that does not protect the app needs no login.
        this.authenticated = !this.status.enabled || Boolean(getOwnerToken())
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Не удалось получить состояние владельца.'
      } finally {
        this.loading = false
      }
    },
    async setup(secret: string, method = 'password', displayName = '', recoveryHint = '') {
      this.error = ''
      this.hint = ''
      try {
        const result = await api.ownerSetup({
          secret,
          method,
          display_name: displayName,
          recovery_hint: recoveryHint,
        })
        setOwnerToken(result.token)
        this.status = result.status
        this.authenticated = true
      } catch (e) {
        this._fail(e)
        throw e
      }
    },
    async login(secret: string) {
      this.error = ''
      this.hint = ''
      try {
        const result = await api.ownerLogin(secret)
        setOwnerToken(result.token)
        this.status = result.status
        this.authenticated = true
      } catch (e) {
        this._fail(e)
        throw e
      }
    },
    async logout() {
      try {
        await api.ownerLogout()
      } catch {
        // Best-effort: the local token is cleared regardless.
      }
      setOwnerToken('')
      this.authenticated = false
      await this.refresh()
    },
    async setProtection(enabled: boolean) {
      this.status = await api.ownerSetProtection(enabled)
      if (!enabled) this.authenticated = true
    },
    /** Drop a token the server no longer accepts (e.g. profile deleted). */
    clear() {
      setOwnerToken('')
      this.authenticated = false
    },
    _fail(e: unknown) {
      if (e instanceof ApiError) {
        this.error = e.message
        this.hint = e.hint
      } else {
        this.error = e instanceof Error ? e.message : 'Не удалось выполнить вход.'
      }
    },
  },
})
