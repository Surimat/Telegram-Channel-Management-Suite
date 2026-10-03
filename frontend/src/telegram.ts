// Thin wrapper around the Telegram WebApp SDK, used by the shared SPA.
// The same build runs in a normal browser (SDK absent) and inside Telegram.

export interface TelegramWebAppUser {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  language_code?: string
  photo_url?: string
}

export interface TelegramWebApp {
  initData: string
  initDataUnsafe?: { user?: TelegramWebAppUser }
  version?: string
  platform?: string
  colorScheme?: 'light' | 'dark'
  ready?: () => void
  expand?: () => void
  setHeaderColor?: (color: string) => void
  setBackgroundColor?: (color: string) => void
  onEvent?: (event: string, cb: () => void) => void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null
}

/** True when the page is running inside the Telegram webview. */
export function isTelegramMiniApp(): boolean {
  const app = getTelegramWebApp()
  return Boolean(app && typeof app.initData === 'string' && app.initData.length > 0)
}

/** Signal readiness/expansion to Telegram and follow its color scheme. */
export function initTelegramWebApp(): void {
  const app = getTelegramWebApp()
  if (!app) return
  app.ready?.()
  app.expand?.()
  if (app.colorScheme === 'dark') {
    document.documentElement.dataset.tgTheme = 'dark'
  }
  app.onEvent?.('themeChanged', () => {
    document.documentElement.dataset.tgTheme = app.colorScheme === 'dark' ? 'dark' : 'light'
  })
}
