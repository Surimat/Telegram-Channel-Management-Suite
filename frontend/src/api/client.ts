// Shared API client. Used by both the Web UI and the Telegram Mini App
// (decision D-003): one SPA, one API.

export interface ApiErrorBody {
  code: string
  message: string
  hint?: string
}

export class ApiError extends Error {
  code: string
  hint: string
  constructor(body: ApiErrorBody) {
    super(body.message)
    this.code = body.code
    this.hint = body.hint ?? ''
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    const body: ApiErrorBody = data?.error ?? {
      code: 'error',
      message: 'Произошла ошибка.',
    }
    throw new ApiError(body)
  }
  return data as T
}

export interface SetupCheck {
  key: string
  title: string
  status: 'ok' | 'warning' | 'error' | 'unknown'
  meaning: string
  how_to_fix: string
}

export interface SystemStatus {
  version: string
  environment: string
  checks: SetupCheck[]
  overall: string
}

export interface Setting {
  key: string
  value: string
  value_type: string
  title: string
  description: string
  default_value: string
  is_secret: boolean
}

export interface EventItem {
  id: string
  level: string
  module: string
  actor: string
  operation: string
  status: string
  message: string
  explanation: string
  how_to_fix: string
  resolved: boolean
  created_at: string
}

export interface Job {
  id: string
  kind: string
  status: string
  priority: number
  scheduled_at: string | null
  attempts: number
  max_attempts: number
  error: string
  group_key: string
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface Health {
  status: string
  version: string
}

export interface SystemInfo {
  version: string
  environment: string
  language: string
  scheduler_enabled: boolean
  ai_enabled: boolean
}

export interface Bot {
  id: string
  kind: string
  enabled: boolean
  telegram_id: number | null
  username: string
  title: string
  has_token: boolean
  owner_id: number | null
  owner_username: string
  can_manage_bots: boolean | null
  health: 'unknown' | 'ok' | 'warning' | 'error'
  health_message: string
  health_hint: string
  last_error: string
  last_health_at: string | null
  created_at: string
  updated_at: string
}

export interface BotSummary {
  total: number
  by_kind: Record<string, number>
  manager_connected: boolean
  manager_username: string
  manager_health: string
}

export interface BotHealth {
  bot_id: string
  ok: boolean
  status: string
  message: string
  how_to_fix: string
  username: string
  telegram_id: number | null
}

export interface ManagedBotPreview {
  bot: Bot | null
  create_link: string
  instructions: string
}

export const api = {
  health: () => request<Health>('/health'),
  healthDeep: () => request<Record<string, unknown>>('/health/deep'),
  systemStatus: () => request<SystemStatus>('/api/v1/system/status'),
  systemInfo: () => request<SystemInfo>('/api/v1/system/info'),
  settings: () => request<Setting[]>('/api/v1/settings'),
  updateSettings: (values: Record<string, string>) =>
    request<Setting[]>('/api/v1/settings', {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    }),
  events: (params: Record<string, string> = {}) =>
    request<Page<EventItem>>('/api/v1/events?' + new URLSearchParams(params).toString()),
  resolveEvent: (id: string) =>
    request<EventItem>(`/api/v1/events/${id}/resolve`, { method: 'POST' }),
  jobs: (params: Record<string, string> = {}) =>
    request<Page<Job>>('/api/v1/queue?' + new URLSearchParams(params).toString()),
  retryJob: (id: string) => request<Job>(`/api/v1/queue/${id}/retry`, { method: 'POST' }),
  cancelJob: (id: string) => request<Job>(`/api/v1/queue/${id}/cancel`, { method: 'POST' }),

  // Bots (PHASE 2)
  bots: (params: Record<string, string> = {}) =>
    request<Bot[]>('/api/v1/bots?' + new URLSearchParams(params).toString()),
  botsSummary: () => request<BotSummary>('/api/v1/bots/summary'),
  addBot: (payload: { token: string; kind?: string; title?: string }) =>
    request<Bot>('/api/v1/bots', { method: 'POST', body: JSON.stringify(payload) }),
  checkBot: (id: string) =>
    request<BotHealth>(`/api/v1/bots/${id}/health`, { method: 'POST' }),
  enableBot: (id: string) => request<Bot>(`/api/v1/bots/${id}/enable`, { method: 'POST' }),
  disableBot: (id: string) => request<Bot>(`/api/v1/bots/${id}/disable`, { method: 'POST' }),
  removeBot: (id: string) =>
    request<null>(`/api/v1/bots/${id}`, { method: 'DELETE' }),
  managedPreview: (username: string, name = '') =>
    request<ManagedBotPreview>(
      `/api/v1/bots/managed/preview?` + new URLSearchParams({ username, name }).toString(),
    ),
  registerManagedBot: (payload: {
    user_id: number
    username?: string
    title?: string
    owner_id?: number
    owner_username?: string
  }) => request<Bot>('/api/v1/bots/managed/register', { method: 'POST', body: JSON.stringify(payload) }),
  fetchManagedToken: (id: string) =>
    request<Bot>(`/api/v1/bots/${id}/managed/token`, { method: 'POST' }),
  replaceManagedToken: (id: string) =>
    request<Bot>(`/api/v1/bots/${id}/managed/replace-token`, { method: 'POST' }),
}
