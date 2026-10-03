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

export interface ReactionCategory {
  key: string
  title: string
}

export interface ReactionProfile {
  id: string
  name: string
  description: string
  enabled: boolean
  is_default: boolean
  allowed_emoji: string[]
  emoji_weights: Record<string, number>
  participation_probability: number
  skip_probability: number
  delay_min: number
  delay_max: number
  delay_preset: 'early' | 'normal' | 'spread'
  max_bots_per_post: number
  created_at: string
  updated_at: string
}

export interface ReactionRule {
  id: string
  name: string
  category: string
  enabled: boolean
  priority: number
  manual_override: boolean
  language: string
  keywords: string[]
  phrases: string[]
  regexes: string[]
  exclusions: string[]
  allowed_reactions: string[]
  preferred_reactions: string[]
  forbidden_reactions: string[]
  min_confidence: number
  created_at: string
  updated_at: string
}

export interface Post {
  id: string
  telegram_message_id: number | null
  channel_id: number | null
  channel_username: string
  text: string
  category: string
  category_title: string
  classification_source: string
  confidence: number
  matched_terms: string
  status: string
  posted_at: string | null
  processed_at: string | null
  created_at: string
}

export interface ReactionJob {
  id: string
  post_id: string
  bot_id: string
  profile_id: string
  reaction: string
  status: string
  scheduled_at: string | null
  completed_at: string | null
  attempts: number
  error: string
  created_at: string
}

export interface SimulationStep {
  bot_id: string
  bot_username: string
  emoji: string
  delay_seconds: number
  scheduled_at: string
  status: string
  delay_human: string
}

export interface SimulationResult {
  text: string
  category: string
  category_title: string
  confidence: number
  source: string
  tone: string
  mode: string
  ai_attempted: boolean
  ai_used: boolean
  fallback_used: boolean
  ai_error: string
  allowed_reactions: string[]
  preferred_reactions: string[]
  forbidden_reactions: string[]
  profile_id: string
  profile_name: string
  total_bots: number
  participating: number
  skipped: number
  steps: SimulationStep[]
}

export interface ReactionLastPost {
  id: string
  category: string
  category_title: string
  created_at: string
  reactions: number
}

export interface ReactionStats {
  enabled: boolean
  active_bots: number
  queue_total: number
  planned_today: number
  done_today: number
  failed_today: number
  counts: Record<string, number>
  last_post: ReactionLastPost | null
}

// Sessions / user accounts (PHASE 4)
export interface UserSession {
  id: string
  telegram_user_id: number | null
  username: string
  display_name: string
  phone_masked: string
  api_id: string
  status: string
  enabled: boolean
  auth_step: string
  has_session: boolean
  has_api_hash: boolean
  session_file_exists: boolean
  session_file_size: number
  status_message: string
  status_hint: string
  last_error: string
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface SessionSummary {
  total: number
  active: number
  online: number
  auth_required: number
  disabled: number
  error: number
  by_status: Record<string, number>
}

export interface AccountIdentity {
  id: number
  username: string
  first_name: string
  last_name: string
  display_name: string
}

export interface AuthStartResult {
  account_id: string | null
  next_step: string
  message: string
  how_to_fix: string
  phone_masked: string
}

export interface AuthStepResult {
  account_id: string
  next_step: string
  done: boolean
  message: string
  how_to_fix: string
  identity: AccountIdentity | null
}

export interface SessionHealth {
  account_id: string
  ok: boolean
  status: string
  message: string
  how_to_fix: string
}

// Invite Manager (PHASE 6)
export interface InvitePreviewSample {
  id: string
  telegram_user_id: number
  username: string
  display_name: string
}

export interface InvitePreview {
  target: string
  source_ids: string[]
  source_labels: string[]
  account_ids: string[]
  account_labels: string[]
  filters: Record<string, unknown>
  total_candidates: number
  planned_operations: number
  accounts_count: number
  max_total: number
  sample: InvitePreviewSample[]
  explanation: string
  requires_confirmation: boolean
}

export interface InviteJob {
  id: string
  name: string
  target: string
  target_title: string
  status: string
  dry_run: boolean
  confirmed_at: string | null
  account_ids: string[]
  source_ids: string[]
  filters: Record<string, unknown>
  total_tasks: number
  processed_count: number
  invited_count: number
  already_count: number
  privacy_count: number
  flood_count: number
  error_count: number
  waiting_account_id: string
  wait_until: string | null
  started_at: string | null
  finished_at: string | null
  last_error: string
  explanation: string
  created_at: string
  updated_at: string
}

export interface InviteJobList {
  items: InviteJob[]
  total: number
  limit: number
  offset: number
}

export interface InviteTask {
  id: string
  job_id: string
  user_id: string
  telegram_user_id: number
  account_id: string
  status: string
  attempts: number
  scheduled_at: string | null
  completed_at: string | null
  wait_until: string | null
  error: string
}

export interface InviteTaskList {
  items: InviteTask[]
  total: number
  limit: number
  offset: number
  status_counts: Record<string, number>
}

// Tiny AI classifier (PHASE 7)
export interface AiSettingHelp {
  key: string
  title: string
  value_type: string
  value: string
  default_value: string
  what_it_does: string
  why: string
  large_value_effect: string
  safe_default: string
}

export interface AiStatus {
  enabled: boolean
  backend: string
  runtime_available: boolean
  model_path: string
  model_exists: boolean
  model_size_bytes: number
  model_size_human: string
  model_loaded: boolean
  effective: boolean
  reason: string
  how_to_fix: string
}

export interface AiMetrics {
  rules_count: number
  ai_count: number
  fallback_count: number
  manual_count: number
  ai_error_count: number
  average_latency_ms: number
  last_latency_ms: number
  model_load_ms: number
  total_classifications: number
}

export interface AiOverview {
  status: AiStatus
  metrics: AiMetrics
  today: AiMetrics
}

export interface AiModel {
  name: string
  path: string
  size_bytes: number
  size_human: string
}

export interface AiModelCheck {
  ok: boolean
  runtime_available: boolean
  model_exists: boolean
  message: string
  how_to_fix: string
  size_bytes: number
  load_ms: number
}

export interface AiClassifyResult {
  category: string
  category_title: string
  tone: string
  confidence: number
  source: string
  source_title: string
  model: string
  processing_time_ms: number
  mode: string
  ai_attempted: boolean
  ai_used: boolean
  fallback_used: boolean
  ai_error: string
}

export interface AiRecord {
  id: string
  source: string
  category: string
  tone: string
  confidence: number
  model: string
  latency_ms: number
  mode: string
  ok: boolean
  detail: string
  created_at: string
}

export interface AiHistory {
  items: AiRecord[]
  total: number
}

// Analytics (PHASE 8) — read-only aggregates with plain-language summaries.
export interface DayPoint {
  date: string
  count: number
}

export interface TitledCount {
  key: string
  title: string
  count: number
}

export interface EmojiCount {
  reaction: string
  count: number
}

export interface BotCount {
  bot_id: string
  count: number
}

export interface SourceCount {
  id: string
  title: string
  username: string
  users: number
}

export interface SourceEffectiveness {
  id: string
  title: string
  username: string
  discovered: number
  new: number
  duplicates: number
  errors: number
  completeness: string
}

export interface ContentAnalytics {
  days: number
  posts_total: number
  posts_window: number
  posts_previous_window: number
  change_percent: number | null
  average_per_day: number
  per_day: DayPoint[]
  by_category: TitledCount[]
  by_source: TitledCount[]
  by_status: Record<string, number>
  summary: string
}

export interface ReactionsAnalytics {
  days: number
  reactions_total: number
  by_status: Record<string, number>
  success_rate: number | null
  per_day: DayPoint[]
  completed_per_day: DayPoint[]
  by_emoji: EmojiCount[]
  by_category: TitledCount[]
  by_bot: BotCount[]
  summary: string
}

export interface AudienceAnalytics {
  days: number
  audience_total: number
  new_7d: number
  per_day: DayPoint[]
  by_status: TitledCount[]
  sources_total: number
  links_total: number
  top_sources: SourceCount[]
  source_effectiveness: SourceEffectiveness[]
  invites: Record<string, number>
  summary: string
}

export interface AnalyticsHeadline {
  posts_total: number
  posts_window: number
  posts_change_percent: number | null
  reactions_total: number
  reaction_success_rate: number | null
  audience_total: number
  audience_new_7d: number
  sources_total: number
}

export interface AnalyticsOverview {
  days: number
  generated_at: string
  headline: AnalyticsHeadline
  content: ContentAnalytics
  reactions: ReactionsAnalytics
  audience: AudienceAnalytics
  summary: string[]
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

  // Reactions (PHASE 3)
  reactionCategories: () =>
    request<ReactionCategory[]>('/api/v1/reactions/categories'),
  reactionStatus: () => request<ReactionStats>('/api/v1/reactions/status'),
  enableReactions: () =>
    request<ReactionStats>('/api/v1/reactions/enable', { method: 'POST' }),
  disableReactions: () =>
    request<ReactionStats>('/api/v1/reactions/disable', { method: 'POST' }),

  reactionProfiles: () => request<ReactionProfile[]>('/api/v1/reactions/profiles'),
  createProfile: (payload: Partial<ReactionProfile>) =>
    request<ReactionProfile>('/api/v1/reactions/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProfile: (id: string, payload: Partial<ReactionProfile>) =>
    request<ReactionProfile>(`/api/v1/reactions/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteProfile: (id: string) =>
    request<null>(`/api/v1/reactions/profiles/${id}`, { method: 'DELETE' }),

  reactionRules: () => request<ReactionRule[]>('/api/v1/reactions/rules'),
  createRule: (payload: Partial<ReactionRule>) =>
    request<ReactionRule>('/api/v1/reactions/rules', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateRule: (id: string, payload: Partial<ReactionRule>) =>
    request<ReactionRule>(`/api/v1/reactions/rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteRule: (id: string) =>
    request<null>(`/api/v1/reactions/rules/${id}`, { method: 'DELETE' }),

  simulate: (payload: { text: string; profile_id?: string; bot_count?: number; seed?: number }) =>
    request<SimulationResult>('/api/v1/reactions/simulate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  reactionPosts: (params: Record<string, string> = {}) =>
    request<Page<Post>>('/api/v1/reactions/posts?' + new URLSearchParams(params).toString()),
  createPost: (payload: {
    text: string
    channel_id?: number
    telegram_message_id?: number
    force_category?: string
    plan?: boolean
  }) =>
    request<Post>('/api/v1/reactions/posts', { method: 'POST', body: JSON.stringify(payload) }),

  reactionJobs: (params: Record<string, string> = {}) =>
    request<Page<ReactionJob>>('/api/v1/reactions/jobs?' + new URLSearchParams(params).toString()),

  // Sessions / user accounts (PHASE 4)
  sessions: (params: Record<string, string> = {}) =>
    request<UserSession[]>('/api/v1/sessions?' + new URLSearchParams(params).toString()),
  sessionsSummary: () => request<SessionSummary>('/api/v1/sessions/summary'),
  authStart: (payload: { api_id: string; api_hash: string; phone: string; display_name?: string }) =>
    request<AuthStartResult>('/api/v1/sessions/auth/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  authCode: (id: string, code: string) =>
    request<AuthStepResult>(`/api/v1/sessions/${id}/code`, {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  authPassword: (id: string, password: string) =>
    request<AuthStepResult>(`/api/v1/sessions/${id}/password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  importSession: (payload: {
    api_id: string
    api_hash: string
    phone?: string
    session_file_path: string
    display_name?: string
  }) =>
    request<UserSession>('/api/v1/sessions/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  checkSession: (id: string) =>
    request<SessionHealth>(`/api/v1/sessions/${id}/health`, { method: 'POST' }),
  enableSession: (id: string) =>
    request<UserSession>(`/api/v1/sessions/${id}/enable`, { method: 'POST' }),
  disableSession: (id: string) =>
    request<UserSession>(`/api/v1/sessions/${id}/disable`, { method: 'POST' }),
  logoutSession: (id: string) =>
    request<UserSession>(`/api/v1/sessions/${id}/logout`, { method: 'POST' }),
  removeSession: (id: string) =>
    request<null>(`/api/v1/sessions/${id}`, { method: 'DELETE' }),

  // Invite Manager (PHASE 6)
  invitePreview: (payload: {
    target: string
    account_ids?: string[]
    source_ids?: string[]
    filters?: Record<string, unknown>
    max_total?: number
  }) =>
    request<InvitePreview>('/api/v1/invites/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  inviteJobs: (params: Record<string, string> = {}) =>
    request<InviteJobList>('/api/v1/invites?' + new URLSearchParams(params).toString()),
  createInviteJob: (payload: {
    name?: string
    target: string
    account_ids?: string[]
    source_ids?: string[]
    filters?: Record<string, unknown>
    dry_run?: boolean
    per_account_delay_min?: number
    per_account_delay_max?: number
    max_per_account?: number
    max_total?: number
  }) =>
    request<InviteJob>('/api/v1/invites', { method: 'POST', body: JSON.stringify(payload) }),
  getInviteJob: (id: string) => request<InviteJob>(`/api/v1/invites/${id}`),
  confirmInviteJob: (id: string) =>
    request<InviteJob>(`/api/v1/invites/${id}/confirm`, { method: 'POST' }),
  pauseInviteJob: (id: string) =>
    request<InviteJob>(`/api/v1/invites/${id}/pause`, { method: 'POST' }),
  resumeInviteJob: (id: string) =>
    request<InviteJob>(`/api/v1/invites/${id}/resume`, { method: 'POST' }),
  stopInviteJob: (id: string) =>
    request<InviteJob>(`/api/v1/invites/${id}/stop`, { method: 'POST' }),
  retryInviteJob: (id: string) =>
    request<InviteJob>(`/api/v1/invites/${id}/retry`, { method: 'POST' }),
  inviteTasks: (id: string, params: Record<string, string> = {}) =>
    request<InviteTaskList>(
      `/api/v1/invites/${id}/tasks?` + new URLSearchParams(params).toString(),
    ),

  // Tiny AI classifier (PHASE 7)
  aiOverview: () => request<AiOverview>('/api/v1/ai/overview'),
  aiStatus: () => request<AiStatus>('/api/v1/ai/status'),
  aiSettings: () => request<{ items: AiSettingHelp[] }>('/api/v1/ai/settings'),
  aiUpdateSettings: (values: Record<string, unknown>) =>
    request<{ items: AiSettingHelp[] }>('/api/v1/ai/settings', {
      method: 'PUT',
      body: JSON.stringify({ values }),
    }),
  aiClassify: (payload: { text: string; mode?: string }) =>
    request<AiClassifyResult>('/api/v1/ai/classify', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  aiModels: () => request<AiModel[]>('/api/v1/ai/models'),
  aiCheckModel: () => request<AiModelCheck>('/api/v1/ai/model/check', { method: 'POST' }),
  aiLoadModel: () => request<AiModelCheck>('/api/v1/ai/model/load', { method: 'POST' }),
  aiUnloadModel: () => request<AiStatus>('/api/v1/ai/model/unload', { method: 'POST' }),
  aiMetrics: () => request<AiMetrics>('/api/v1/ai/metrics'),
  aiHistory: (params: Record<string, string> = {}) =>
    request<AiHistory>('/api/v1/ai/history?' + new URLSearchParams(params).toString()),

  // Analytics (PHASE 8)
  analyticsOverview: (days = 30) =>
    request<AnalyticsOverview>(`/api/v1/analytics/overview?days=${days}`),
  analyticsContent: (days = 30) =>
    request<ContentAnalytics>(`/api/v1/analytics/content?days=${days}`),
  analyticsReactions: (days = 30) =>
    request<ReactionsAnalytics>(`/api/v1/analytics/reactions?days=${days}`),
  analyticsAudience: (days = 30) =>
    request<AudienceAnalytics>(`/api/v1/analytics/audience?days=${days}`),
}
