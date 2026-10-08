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
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getOwnerToken()
  if (token) headers['X-Owner-Token'] = token
  const response = await fetch(path, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) },
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
  registry_channel_id: string
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
  proxy_id: string
  restriction_count: number
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

// v1.1 Account Hub: multi-format local import + restriction-risk band.
export interface SessionImportDetect {
  format: string
  format_title: string
  state: string
  state_title: string
  available: boolean
  message: string
  how_to_fix: string
  notes: string[]
}

export interface SessionImportResult {
  account: UserSession
  format: string
  format_title: string
  notes: string[]
  message: string
}

export interface SessionRisk {
  level: string
  title: string
  message: string
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

// v1.1: optional lightweight encoder model (ruBERT-tiny2) install status.
export interface EncoderStatus {
  runtime_available: boolean
  installed: boolean
  ready: boolean
  model_dir: string
  size_bytes: number
  size_human: string
  missing: string[]
  message: string
  how_to_fix: string
  repo: string
  license: string
}

export interface EncoderActionResult {
  ok: boolean
  message: string
  how_to_fix: string
  downloaded: number
  status: EncoderStatus
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

// Audience & Sources (PHASE 5)
export interface AudienceSource {
  id: string
  title: string
  username: string
  telegram_id: number | null
  source_type: string
  reference: string
  channel_id: string
  enabled: boolean
  account_id: string | null
  scan_status: string
  completeness: string
  last_scan_at: string | null
  last_scan_finished_at: string | null
  discovered_count: number
  imported_count: number
  new_count: number
  duplicate_count: number
  error_count: number
  reported_total: number | null
  scanned_offset: number
  scan_job_id: string
  last_error: string
  created_at: string
  updated_at: string
}

export interface SourceList {
  items: AudienceSource[]
  total: number
  limit: number
  offset: number
}

export interface SourceCheck {
  ok: boolean
  title: string
  username: string
  telegram_id: number | null
  kind: string
  participants_count: number | null
  participants_hidden: boolean
  message: string
  how_to_fix: string
  completeness: string
}

export interface ScanPreview {
  source_id: string
  title: string
  username: string
  source_type: string
  reference: string
  account_id: string
  account_label: string
  mode: string
  batch_size: number
  chunk_size: number
  estimated_total: number | null
  filters: Record<string, unknown>
  notes: string[]
}

export interface ScanResult {
  source_id: string
  scan_status: string
  completeness: string
  discovered: number
  new: number
  duplicates: number
  errors: number
  reported_total: number | null
  offset: number
  explanation: string
  completed: boolean
}

export interface AudienceUser {
  id: string
  telegram_user_id: number
  username: string
  first_name: string
  last_name: string
  display_name: string
  phone_masked: string
  is_bot: boolean
  is_deleted: boolean
  is_premium: boolean | null
  status: string
  score: number
  score_reason: string
  tags: string[]
  first_seen_at: string | null
  last_seen_at: string | null
  invite_status: string
  invite_attempts: number
  last_invite_at: string | null
  last_invite_error: string
}

export interface AudienceUserDetail extends AudienceUser {
  sources: string[]
  score_components: Record<string, unknown>[]
}

export interface AudienceUserList {
  items: AudienceUser[]
  total: number
  limit: number
  offset: number
}

export interface AudienceTag {
  name: string
  count: number
}

export interface FilterPreset {
  key: string
  label: string
  description: string
  filters: Record<string, unknown>
}

export interface AudienceDashboard {
  sources_total: number
  unique_users: number
  total_records: number
  new_users_7d: number
  scans_total: number
  partial_sources: number
  errors_total: number
  bots: number
  by_scan_status: Record<string, number>
  by_completeness: Record<string, number>
  source_overlap: Record<string, unknown>[]
  discovered_per_day: Record<string, unknown>[]
}

export interface ExportPreview {
  count: number
  fields: string[]
  includes_pii: boolean
  destination: string
  note: string
}

export interface ExportResult {
  filename: string
  path: string
  format: string
  fields: string[]
  includes_pii: boolean
  row_count: number
  size_bytes: number
}

export interface ImportResult {
  created: number
  merged: number
  invalid: number
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
  channel_id: string
  generated_at: string
  account_connected: boolean
  account_note: string
  headline: AnalyticsHeadline
  content: ContentAnalytics
  reactions: ReactionsAnalytics
  audience: AudienceAnalytics
  summary: string[]
}

// Telegram Mini App (PHASE 9)
export interface MiniAppConfig {
  enabled: boolean
  available: boolean
  bot_username: string
  public_url: string
  reason: string
  how_to_fix: string
}

export interface MiniAppUser {
  id: number
  display_name: string
  username: string
  language_code: string
  photo_url: string
}

export interface MiniAppAuthResponse {
  authenticated: boolean
  is_admin: boolean
  user: MiniAppUser
  expires_in: number
}

export interface MiniAppMe {
  authenticated: boolean
  is_admin: boolean
  telegram_id: number | null
  expires_at: number | null
}

export interface MiniAppSetupResult {
  ok: boolean
  message: string
  how_to_fix: string
}

// Backup / restore (PHASE 10)
export interface BackupEntry {
  filename: string
  kind: string
  created_at: string | null
  size_bytes: number
  size_human: string
  includes_sessions: boolean
  version: string
}

export interface BackupList {
  items: BackupEntry[]
  total: number
  backup_dir: string
  retention: number
  include_sessions_default: boolean
}

export interface BackupInfo {
  what_it_does: string
  why: string
  sessions_warning: string
  safe_default: string
  excluded_tables: string[]
}

export interface RestoreResult {
  restored: boolean
  source: string
  safety_backup: string
  includes_sessions: boolean
}

export interface ImportConfigResult {
  imported: Record<string, number>
  message: string
}

// Post-1.0 hardening: permission probe + manager bot runtime.
export interface PermissionResult {
  status: string
  status_label: string
  account_id: string
  account_label: string
  target: string
  target_title: string
  registry_channel_id: string
  channel_found: boolean
  authorized: boolean
  can_read_info: boolean
  can_read_participants: boolean
  can_invite: boolean
  session_ok: boolean
  channel_id: number | null
  channel_username: string
  channel_kind: string
  participants_count: number | null
  message: string
  how_to_fix: string
  retry_after: number | null
  checked_at: string | null
  check_id: string | null
}

export interface PermissionHistory {
  items: PermissionResult[]
  latest: PermissionResult | null
}

export interface ManagerStatus {
  connected: boolean
  runtime_running: boolean
  username: string
  health: string
  status_label: string
  admin_count: number
  notifications_enabled: boolean
  pending_notifications: number
  how_to_fix: string
}

export interface NotificationCategory {
  key: string
  label: string
  enabled: boolean
}

export interface NotificationSettings {
  enabled: boolean
  categories: NotificationCategory[]
}

// Channel Registry (hardening: one shared channel identity, decision D-051)
export interface Channel {
  id: string
  reference: string
  telegram_id: number | null
  username: string
  title: string
  kind: string
  status: string
  is_default: boolean
  modules: Record<string, boolean>
  verification_status: string
  verification_message: string
  verification_hint: string
  participants_count: number | null
  last_verified_at: string | null
  note: string
  created_at: string
  updated_at: string
}

export interface ChannelList {
  items: Channel[]
  total: number
  limit: number
  offset: number
}

export interface DiagnosticItem {
  key: string
  title: string
  status: 'ok' | 'warning' | 'error' | 'not_configured' | 'unknown'
  status_label: string
  meaning: string
  how_to_fix: string
}

export interface DiagnosticsReport {
  version: string
  environment: string
  overall: string
  overall_label: string
  generated_at: string
  items: DiagnosticItem[]
}

export interface MaintenanceAction {
  key: string
  title: string
  description: string
  destructive: boolean
  requires_confirmation: boolean
  available: boolean
}

export interface MaintenanceResult {
  action: string
  ok: boolean
  message: string
  detail: string
  affected: number
}

export interface HelpTopic {
  key: string
  title: string
  what: string
  why: string
  effect: string
  when_off: string
  safe_default: string
}

export interface UiPrefs {
  show_explanations: boolean
  language: string
  available_languages: string[]
}

export interface ChannelSummary {
  total: number
  verified: number
  with_warning: number
  with_error: number
  default_channel_id: string | null
  default_channel_label: string
}

export interface ChannelVerification {
  channel_id: string
  status: string
  status_label: string
  found: boolean
  title: string
  username: string
  kind: string
  participants_count: number | null
  message: string
  how_to_fix: string
  retry_after: number | null
}

// Product slice: bot↔channel bindings + channel reaction capabilities.
export interface Binding {
  id: string
  bot_id: string
  bot_username: string
  channel_id: string
  channel_label: string
  function: string
  status: string
  status_label: string
  role: string
  can_post_messages: boolean
  can_edit_messages: boolean
  can_delete_messages: boolean
  can_manage_chat: boolean
  can_invite_users: boolean
  can_set_reactions: boolean
  invite_link: string
  note: string
  last_checked: string | null
  last_error: string
  created_at: string
}

export interface BindingList {
  items: Binding[]
  total: number
}

export interface BindingCheck {
  binding_id: string
  status: string
  status_label: string
  role: string
  present: boolean
  can_set_reactions: boolean
  message: string
  how_to_fix: string
}

export interface Capability {
  channel_id: string
  status: string
  available: string[]
  bot_reactions: string[]
  reactions_limit: number
  paid_available: boolean
  message: string
  last_checked: string
}

// Product slice: invite campaigns (work without a user session).
export interface Campaign {
  id: string
  name: string
  status: string
  channel_id: string
  target_title: string
  risk_mode: string
  links_count: number
  joins_count: number
  requests_count: number
  conversion: number | null
  summary: string
}

export interface CampaignLink {
  id: string
  label: string
  link: string
  status: string
  join_request: boolean
  member_limit: number
  joins_count: number
  requests_count: number
  last_error: string
}

export interface CampaignDetail {
  campaign: Campaign
  links: CampaignLink[]
  requests_pending: number
  requests_approved: number
}

export interface CampaignList {
  items: Campaign[]
  total: number
  risk_modes: Record<string, string>
}

// Product slice: donor quality indicators (honest, no invented numbers).
export interface DonorMetric {
  id: string
  source_id: string
  channel_id: string
  title: string
  subscribers: number
  quality: string
  quality_title: string
  quality_score: number
  bot_probability: string
  confidence: string
  participant_data: boolean
  bot_share_estimate: number | null
  signals: string[]
  explanations: string[]
  summary: string
  source_completeness: string
  last_analyzed: string | null
}

export interface DonorList {
  items: DonorMetric[]
  total: number
  note: string
}

// Product slice: where backups are delivered.
export interface Destination {
  id: string
  kind: string
  title: string
  label: string
  enabled: boolean
  status: string
  account_label: string
  config: Record<string, unknown>
  last_backup_at: string | null
  last_error: string
  available_space: number | null
}

export interface DestinationList {
  items: Destination[]
  total: number
  available_kinds: Record<string, unknown>[]
}

export interface DeliveryResult {
  destination_id: string
  kind: string
  ok: boolean
  message: string
}

// Product slice: first-run promotion wizard.
export interface WizardStep {
  key: string
  title: string
  description: string
  status: string
  status_title: string
  how_to_fix: string
  route: string
  requires_session: boolean
}

export interface WizardState {
  preset: string
  preset_title: string
  preset_description: string
  has_session: boolean
  mode: string
  completed: boolean
  dismissed: boolean
  current_step: string
  completed_steps: number
  total_steps: number
  steps: WizardStep[]
  session_optional_note: string
  session_risk_note: string
  capabilities: CapabilityState[]
}

export interface WizardPreset {
  id: string
  title: string
  description: string
  requires_session: boolean
}

// Product slice: conservative auto-update.
export interface UpdateStatus {
  enabled: boolean
  state: string
  state_title: string
  current_version: string
  latest_version: string
  update_available: boolean
  release_url: string
  release_notes: string
  staged_file: string
  staged_sha256: string
  last_checked_at: string | null
  message: string
  last_error: string
}

// v1.1: proxy profiles (connection routes — never a Telegram limit bypass).
export interface ProxyProfile {
  id: string
  name: string
  kind: string
  kind_title: string
  host: string
  port: number
  username: string
  has_password: boolean
  enabled: boolean
  status: string
  status_title: string
  status_message: string
  last_checked: string
}

export interface ProxyList {
  items: ProxyProfile[]
  notice: string
}

export interface ProxyCheck {
  profile_id: string
  ok: boolean
  status: string
  status_title: string
  message: string
  how_to_fix: string
  latency_ms: number
}

// v1.1: donor discovery (candidates are proposals, added explicitly).
export interface DiscoveryProviderStatus {
  name: string
  title: string
  available: boolean
  message: string
}

export interface DiscoveryProviderReport {
  provider: string
  title: string
  ok: boolean
  message: string
  how_to_fix: string
  found: number
}

export interface DonorCandidate {
  id: string
  query: string
  provider: string
  provider_title: string
  username: string
  title: string
  telegram_id: number | null
  kind: string
  subscribers: number
  avg_views: number
  activity: number
  language: string
  fit: string
  fit_title: string
  fit_score: number
  confidence: string
  signals: string[]
  explanations: string[]
  summary: string
  added: boolean
  added_source_id: string
  reach_ratio: number
  reaction_ratio: number
  score_label: string
}

export interface DiscoveryResult {
  query: string
  stored: number
  providers: DiscoveryProviderReport[]
  candidates: DonorCandidate[]
}

export interface CandidateList {
  items: DonorCandidate[]
  providers: DiscoveryProviderStatus[]
}

export interface DiscoveryCompare {
  items: DonorCandidate[]
  best_id: string
  best_title: string
  best_reason: string
}

// v1.2: Content Studio (sources → items → clean → plan → publish).
export interface ContentProviderStatus {
  kind: string
  title: string
  available: boolean
  requires_account: boolean
  message: string
}

export interface ContentSource {
  id: string
  kind: string
  kind_title: string
  title: string
  reference: string
  enabled: boolean
  channel_id: string
  status: string
  status_title: string
  last_error: string
  last_fetch: string
  last_fetch_new: number
  etag: string
  last_modified: string
  last_seen_item: string
  blocked_keywords: string[]
  quiet_hours_enabled: boolean
  quiet_hours_start: number
  quiet_hours_end: number
  quiet_hours_tz: string
}

export interface ContentSourceList {
  items: ContentSource[]
  providers: ContentProviderStatus[]
}

export interface GrabResult {
  source_id: string
  ok: boolean
  new_items: number
  duplicates: number
  protected: boolean
  message: string
  how_to_fix: string
  item_ids: string[]
  blocked: number
  held: number
}

export interface ContentItem {
  id: string
  title: string
  text: string
  cleaned_text: string
  entities: Record<string, unknown>[]
  buttons: Record<string, unknown>[]
  status: string
  status_title: string
  mode: string
  source_id: string
  source_message_id: number | null
  source_url: string
  source_channel: string
  source_author: string
  imported_at: string
  rights_status: string
  rights_title: string
  attribution_enabled: boolean
  protected: boolean
  content_hash: string
  language: string
  note: string
  scheduled_at: string
  rights_warning: string
  held: boolean
  moderation_note: string
  original_text: string
  ai_status: string
  ai_category: string
  ai_intent: string
  ai_profile: string
  ai_note: string
  created_at: string
  updated_at: string
}

export interface ContentItemList {
  items: ContentItem[]
  total: number
  limit: number
  offset: number
}

export interface CleanPreview {
  original: string
  cleaned: string
  changed: boolean
  changes: Record<string, unknown>[]
  removed_lines: number
}

export interface RewriteResult {
  ok: boolean
  text: string
  mode: string
  mode_title: string
  message: string
  how_to_fix: string
  used_model: string
}

export interface RightsInfo {
  rights_status: string
  rights_title: string
  attribution_block: string
  warning: string
}

export interface ContentDashboard {
  drafts: number
  imported: number
  ready: number
  scheduled: number
  published_today: number
  failed: number
  status_counts: Record<string, number>
  publication_counts: Record<string, number>
}

export interface ContentButton {
  text: string
  action: string
  value: string
}

export interface ContentButtonSet {
  item_id: string
  rows: ContentButton[][]
  enabled: boolean
}

export interface ContentPublication {
  id: string
  item_id: string
  channel_id: string
  channel_username: string
  status: string
  status_title: string
  scheduled_at: string
  published_at: string
  delete_at: string
  telegram_message_ids: number[]
  error: string
  attempts: number
  mode: string
  profile_key: string
  comment_status: string
  delete_status: string
}

export interface ContentPlan {
  publications: ContentPublication[]
}

export interface PublishResult {
  publication_id: string
  ok: boolean
  status: string
  message_ids: number[]
  message: string
  how_to_fix: string
  uncertain: boolean
}

export interface CalendarEntry {
  publication_id: string
  item_id: string
  title: string
  channel_id: string
  channel_title: string
  status: string
  status_title: string
  scheduled_at: string
  published_at: string
  delete_at: string
}

export interface CalendarChannel {
  channel_id: string
  title: string
  reference: string
}

export interface ContentCalendar {
  start: string
  end: string
  channels: CalendarChannel[]
  entries: CalendarEntry[]
}

export interface ContentValidation {
  ok: boolean
  issues: { kind: string; message: string; line: number }[]
  button_problems: string[]
  first_error: string
  fixed_text: string
}

export interface ContentPreview {
  text: string
  entities: Record<string, unknown>[]
  buttons: { text: string; action: string; url: string }[][]
  media: { kind: string; filename: string; caption: string }[]
  is_album: boolean
  caption_used: boolean
  char_count: number
  notice: string
}

export interface ContentModeration {
  source_id: string
  blocked_keywords: string[]
  quiet_hours_enabled: boolean
  quiet_hours_start: number
  quiet_hours_end: number
  quiet_hours_tz: string
}

// --- Content Operations 2.0 (v1.9) -----------------------------------------
export interface AiProfile {
  id: string
  key: string
  title: string
  language: string
  tone: string
  max_length: number
  system_instructions: string
  provider_policy: string
  actions: string[]
  enabled: boolean
  builtin: boolean
  description: string
}

export interface AutomationRule {
  id: string
  name: string
  enabled: boolean
  source_kind: string
  condition: Record<string, unknown>
  actions: string[]
  action_titles: string[]
  profile_key: string
  priority: number
  description: string
}

export interface PipelineRecord {
  id: string
  item_id: string
  publication_id: string
  stage: string
  status: string
  source_kind: string
  channel_id: string
  provider: string
  model: string
  fallback_used: boolean
  latency_ms: number
  attempts: number
  detail: string
  occurred_at: string
}

export interface PipelineAnalytics {
  stage_counts: Record<string, number>
  ai_provider_counts: Record<string, number>
  ai_fallback: number
  ai_failed: number
  comment_posted: number
  comment_failed: number
  delete_failed: number
  recent: PipelineRecord[]
}

// --- LAN Mesh (v1.3) ---------------------------------------------------------
export interface MeshStatus {
  enabled: boolean
  mode: string
  mode_label: string
  role: string
  node_id: string
  name: string
  capabilities: string[]
  priority: number
  host: string
  port: number
  coordinator_id: string
  peers_total: number
  peers_trusted: number
  peers_online: number
  discovery_enabled: boolean
  note: string
}

export interface MeshPeer {
  id: string
  node_id: string
  name: string
  version: string
  capabilities: string[]
  priority: number
  host: string
  port: number
  trusted: boolean
  status: string
  status_label: string
  last_seen: string | null
  note: string
}

export interface MeshPeerList {
  items: MeshPeer[]
  total: number
}

export interface MeshLease {
  id: string
  job_id: string
  kind: string
  lease_owner: string
  lease_until: string | null
  fencing_token: number
  status: string
  attempts: number
  error: string
}

export interface MeshLeaseList {
  items: MeshLease[]
  total: number
}

export interface PairingCode {
  code: string
  expires_at: string | null
}

// --- Bot Factory (v1.3) ------------------------------------------------------
export interface FactoryTemplate {
  key: string
  name_template: string
  username_template: string
}

export interface FactoryBatch {
  id: string
  title: string
  prefix: string
  topic: string
  style: string
  requested_count: number
  created_count: number
  failed_count: number
  skipped_count: number
  status: string
  status_label: string
  manager_username: string
  channel_id: string
  queue_cancelled: boolean
  limit_note: string
}

export interface FactoryCandidate {
  id: string
  batch_id: string
  index: number
  suggested_name: string
  suggested_username: string
  username_status: string
  username_message: string
  creation_status: string
  creation_status_label: string
  queue_state: string
  queue_state_label: string
  attempts: number
  bot_id: string
  telegram_id: number | null
  token_mask: string
  deep_link: string
  error: string
}

export interface FactoryBatchDetail {
  batch: FactoryBatch
  candidates: FactoryCandidate[]
}

export interface FactoryBatchList {
  items: FactoryBatch[]
  total: number
}

export interface FactoryQueueProgress {
  total: number
  pending: number
  queued: number
  running: number
  success: number
  failed: number
  skipped: number
  cancelled: number
}

export interface FactoryDashboard {
  batch_id: string
  title: string
  status: string
  status_label: string
  requested_count: number
  created_count: number
  failed_count: number
  skipped_count: number
  queue_cancelled: boolean
  counts: Record<string, number>
  queue: FactoryQueueProgress
  manager_username: string
  channel_id: string
  limit_note: string
}

export interface FactoryBindResult {
  candidate_id: string
  bot_id: string
  username: string
  binding_id: string
  status: string
  status_label: string
}

// Editorial Workspace (v1.4)
export interface EditorialRoom {
  id: string
  channel_id: string
  channel_label: string
  bot_id: string
  group_chat_id: number | null
  group_title: string
  status: string
  status_label: string
  topics: Record<string, number>
  bot_is_member: boolean
  bot_is_admin: boolean
  can_send_messages: boolean
  can_manage_topics: boolean
  last_checked: string
  last_error: string
}

export interface EditorialRoomList {
  items: EditorialRoom[]
  status_titles: Record<string, string>
}

export interface EditorialRoomCheck {
  room_id: string
  status: string
  status_label: string
  message: string
  how_to_fix: string
  topics: Record<string, number>
}

export interface EditorialMember {
  id: string
  telegram_user_id: number
  display_name: string
  username: string
  role: string
  role_title: string
  enabled: boolean
}

export interface EditorialItem {
  id: string
  content_item_id: string
  channel_id: string
  channel_label: string
  title: string
  status: string
  status_title: string
  order_index: number
  assigned_user_id: number
  version: number
  error: string
  scheduled_at: string
  card_message_id: number | null
  topic_id: number | null
  available_actions: string[]
}

export interface EditorialBoard {
  room_id: string
  channel_id: string
  channel_label: string
  group_title: string
  status: string
  status_label: string
  topics: Record<string, number>
  counts: Record<string, number>
  columns: Record<string, EditorialItem[]>
  status_titles: Record<string, string>
}

export interface EditorialActionResult {
  ok: boolean
  action: string
  message: string
  item_id: string
  status: string
}

export interface EditorialAudit {
  id: string
  item_id: string
  actor_telegram_id: number
  actor_name: string
  action: string
  old_status: string
  new_status: string
  detail: string
  created_at: string
}

// Notification Center (v1.4)
export interface NotificationCategory {
  key: string
  label: string
  enabled: boolean
  destinations: string[]
}

export interface NotificationSettings {
  enabled: boolean
  categories: NotificationCategory[]
  quiet_hours_enabled: boolean
  quiet_hours_start: number
  quiet_hours_end: number
  quiet_hours_tz: string
  aggregation_enabled: boolean
  destinations: { key: string; label: string }[]
}

export interface NotificationItem {
  id: string
  category: string
  category_label: string
  priority: string
  priority_label: string
  destination: string
  destination_label: string
  event_key: string
  message: string
  how_to_fix: string
  status: string
  status_label: string
  error: string
  aggregate_count: number
  read: boolean
  postponed_until: string
  delivered_at: string
  created_at: string
}

export interface NotificationList {
  items: NotificationItem[]
  total: number
}

export interface NotificationDashboard {
  enabled: boolean
  pending: number
  failed: number
  quiet_hours_enabled: boolean
  in_quiet_hours: boolean
  status_counts: Record<string, number>
  category_counts: Record<string, number>
}

// Consistency ("Проверка целостности", v1.5)
export interface ConsistencyFinding {
  id: string
  category: string
  area: string
  severity: 'error' | 'warning' | 'info'
  confidence: 'high' | 'medium' | 'low'
  title: string
  detail: string
  why: string
  how_to_fix: string
  subsystem: string
}

export interface ConsistencyArea {
  key: string
  label: string
  status: 'pass' | 'warning' | 'fail' | 'not_tested'
}

export interface ConsistencyReport {
  generated_at: string
  overall: 'pass' | 'warning' | 'fail'
  counts: Record<string, number>
  areas: ConsistencyArea[]
  findings: ConsistencyFinding[]
}

// Capability graph (v1.5)
export interface CapabilityState {
  key: string
  title: string
  state: 'available' | 'partial' | 'needs_setup' | 'unavailable' | 'not_implemented'
  state_label: string
  requires: string[]
  satisfied: string[]
  missing: string[]
  missing_fixes: string[]
  note: string
  implemented: boolean
}

// Owner Auth + Config Sync (v1.6)
export interface OwnerStatus {
  exists: boolean
  enabled: boolean
  locked: boolean
  method: string
  method_title: string
  display_name: string
  last_login_at: string
  failed_attempts: number
  locked_until: string
  recovery_hint: string
  auth_required: boolean
  local_only_note: string
}

export interface OwnerToken {
  token: string
  status: OwnerStatus
}

export interface SyncStatus {
  state: string
  state_label: string
  provider: string
  provider_label: string
  connected: boolean
  enabled: boolean
  owner_ready: boolean
  local_revision: number
  cloud_revision: number
  device_id: string
  device_name: string
  cloud_device: string
  cloud_updated_at: string
  last_sync_at: string
  last_status: string
  message: string
  needs_reconnect: boolean
  conflict: boolean
  no_live_db_note: string
  appdata_scope_note: string
}

export interface SyncRestorePreview {
  revision: number
  device_id: string
  device_name: string
  updated_at: string
  settings: Record<string, unknown>
  ui: Record<string, unknown>
  bot_count: number
  channel_count: number
  differing: string[]
}

export interface SyncConflict {
  local_revision: number
  cloud_revision: number
  cloud_device: string
  cloud_updated_at: string
  local_device: string
  detected: boolean
}

export interface SyncGoogleAuth {
  configured: boolean
  authorization_url: string
  state: string
}

// AI Gateway (v1.8): one access layer over many providers + Web wrappers.
export interface GatewayCapability {
  text: boolean
  image: boolean
  file: boolean
  streaming: boolean
  structured: boolean
  verified: boolean
}

export interface GatewayProvider {
  provider: string
  kind: string
  kind_label: string
  model: string
  base_url: string
  auth_mode: string
  has_key: boolean
  enabled: boolean
  priority: number
  cost: string
  source: string
  capabilities: Record<string, boolean>
  wrapper_id: string
  region_status: string
  note: string
  status: string
  status_detail: string
  latency_ms: number
  last_error: string
  last_success: string
}

export interface GatewayProviderList {
  items: GatewayProvider[]
  kinds: { value: string; label: string }[]
  strategies: string[]
}

export interface GatewayStatus {
  enabled: boolean
  strategy: string
  providers: number
  enabled_providers: number
  available_providers: number
  browser_available: boolean
  browser_detail: string
  allow_paid: boolean
  web_enabled: boolean
  note: string
}

export interface GatewaySettings {
  strategy: string
  allow_paid: boolean
  web_enabled: boolean
  max_retries: number
  timeout_seconds: number
  history_limit: number
  enabled: boolean
}

export interface GatewayAttempt {
  provider: string
  status: string
  ok: boolean
  latency_ms: number
  detail: string
}

export interface GatewayChatResult {
  ok: boolean
  text: string
  provider_used: string
  model_used: string
  source: string
  fallback_used: boolean
  attempts: GatewayAttempt[]
  latency_ms: number
  status: string
  error: string
  error_category: string
  request_id: string
  structured: Record<string, unknown> | null
}

export interface GatewayWrapper {
  id: string
  name: string
  website: string
  capabilities: Record<string, boolean>
  auth_mode: string
  version: string
  enabled: boolean
  fallback_priority: number
  cost: string
  note: string
}

export interface GatewayBrowserStatus {
  available: boolean
  detail: string
  runtime: string
  docker_note: string
}

export interface GatewayUseCase {
  group: string
  id: string
  modality: string
  providers: string[]
  available: boolean
}

export interface GatewayRequestRecord {
  request_id: string
  provider: string
  model: string
  source: string
  strategy: string
  ok: boolean
  fallback_used: boolean
  attempts: number
  latency_ms: number
  status: string
  error_category: string
  at: string
}

// The owner token is a signed, opaque session value — never a password. It is
// kept in sessionStorage so closing the tab ends the browser session.
const OWNER_TOKEN_KEY = 'tcms.owner.token'

export function getOwnerToken(): string {
  try {
    return sessionStorage.getItem(OWNER_TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setOwnerToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(OWNER_TOKEN_KEY, token)
    else sessionStorage.removeItem(OWNER_TOKEN_KEY)
  } catch {
    // Storage may be unavailable; the header simply stays empty.
  }
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

  // Bot Factory (v1.3)
  factoryTemplates: () => request<FactoryTemplate[]>('/api/v1/bot-factory/templates'),
  factoryBatches: () => request<FactoryBatchList>('/api/v1/bot-factory/batches'),
  factoryBatch: (id: string) =>
    request<FactoryBatchDetail>(`/api/v1/bot-factory/batches/${id}`),
  createFactoryBatch: (payload: {
    prefix: string
    count: number
    title?: string
    topic?: string
    style?: string
    manager_bot_id?: string
    account_id?: string
    channel_id?: string
  }) =>
    request<FactoryBatchDetail>('/api/v1/bot-factory/batches', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteFactoryBatch: (id: string) =>
    request<null>(`/api/v1/bot-factory/batches/${id}`, { method: 'DELETE' }),
  checkFactoryBatch: (id: string, accountId = '') =>
    request<FactoryBatchDetail>(
      `/api/v1/bot-factory/batches/${id}/check?account_id=${encodeURIComponent(accountId)}`,
      { method: 'POST' },
    ),
  regenerateFactoryCandidate: (id: string) =>
    request<FactoryCandidate>(`/api/v1/bot-factory/candidates/${id}/regenerate`, {
      method: 'POST',
    }),
  createFactoryBots: (id: string, viaDeeplink = false) =>
    request<FactoryBatchDetail>(
      `/api/v1/bot-factory/batches/${id}/create?via_deeplink=${viaDeeplink}`,
      { method: 'POST' },
    ),
  adoptFactoryBot: (id: string, payload: { username: string; telegram_id: number; title?: string }) =>
    request<FactoryCandidate>(`/api/v1/bot-factory/batches/${id}/adopt`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  registerFactoryTokens: (id: string) =>
    request<{ imported: number; pending: number }>(
      `/api/v1/bot-factory/batches/${id}/tokens`,
      { method: 'POST' },
    ),
  bindFactoryBots: (id: string, payload: { channel_id: string; function?: string }) =>
    request<FactoryBindResult[]>(`/api/v1/bot-factory/batches/${id}/bind`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  factoryDashboard: (id: string) =>
    request<FactoryDashboard>(`/api/v1/bot-factory/batches/${id}/dashboard`),
  factoryEnqueue: (id: string, viaDeeplink = false) =>
    request<FactoryBatchDetail>(
      `/api/v1/bot-factory/batches/${id}/enqueue?via_deeplink=${viaDeeplink}`,
      { method: 'POST' },
    ),
  factoryCancel: (id: string) =>
    request<FactoryBatchDetail>(`/api/v1/bot-factory/batches/${id}/cancel`, {
      method: 'POST',
    }),
  factoryResume: (id: string) =>
    request<FactoryBatchDetail>(`/api/v1/bot-factory/batches/${id}/resume`, {
      method: 'POST',
    }),
  factoryRetryCandidate: (id: string) =>
    request<FactoryCandidate>(`/api/v1/bot-factory/candidates/${id}/retry`, {
      method: 'POST',
    }),
  factorySkipCandidate: (id: string) =>
    request<FactoryCandidate>(`/api/v1/bot-factory/candidates/${id}/skip`, {
      method: 'POST',
    }),

  // LAN Mesh (v1.3)
  meshStatus: () => request<MeshStatus>('/api/v1/mesh/status'),
  meshPeers: (trusted?: boolean) =>
    request<MeshPeerList>(
      '/api/v1/mesh/peers' + (trusted === undefined ? '' : `?trusted=${trusted}`),
    ),
  meshDiscover: () => request<MeshPeerList>('/api/v1/mesh/discover', { method: 'POST' }),
  meshAddPeer: (payload: { host: string; port: number; name?: string }) =>
    request<MeshPeer>('/api/v1/mesh/peers/manual', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  meshPairingCode: () =>
    request<PairingCode>('/api/v1/mesh/pairing-code', { method: 'POST' }),
  meshPair: (payload: {
    code: string
    node_id?: string
    host?: string
    port?: number
    name?: string
    capabilities?: string[]
    priority?: number
  }) => request<MeshPeer>('/api/v1/mesh/pair', { method: 'POST', body: JSON.stringify(payload) }),
  meshUnpair: (id: string) =>
    request<null>(`/api/v1/mesh/peers/${id}`, { method: 'DELETE' }),
  meshProbe: (id: string) =>
    request<MeshPeer>(`/api/v1/mesh/peers/${id}/probe`, { method: 'POST' }),
  meshElect: () =>
    request<{ coordinator_id: string }>('/api/v1/mesh/elect', { method: 'POST' }),
  meshLeases: () => request<MeshLeaseList>('/api/v1/mesh/leases'),

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
    channel_username?: string
    registry_channel_id?: string
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
  detectSessionImport: (payload: {
    path?: string
    string_session?: string
    api_id?: string
    api_hash?: string
  }) =>
    request<SessionImportDetect>('/api/v1/sessions/import/detect', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  importSessionArtifact: (payload: {
    path?: string
    string_session?: string
    api_id?: string
    api_hash?: string
    phone?: string
    display_name?: string
  }) =>
    request<SessionImportResult>('/api/v1/sessions/import/artifact', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sessionRisk: (id: string) => request<SessionRisk>(`/api/v1/sessions/${id}/risk`),
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
    target?: string
    channel_id?: string
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
    target?: string
    channel_id?: string
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
  aiEncoderStatus: () => request<EncoderStatus>('/api/v1/ai/encoder/status'),
  aiEncoderInstall: () =>
    request<EncoderActionResult>('/api/v1/ai/encoder/install', { method: 'POST' }),
  aiEncoderCheck: () =>
    request<EncoderActionResult>('/api/v1/ai/encoder/check', { method: 'POST' }),
  aiEncoderRemove: () =>
    request<EncoderStatus>('/api/v1/ai/encoder/remove', { method: 'POST' }),
  aiHistory: (params: Record<string, string> = {}) =>
    request<AiHistory>('/api/v1/ai/history?' + new URLSearchParams(params).toString()),

  // Audience & Sources (PHASE 5)
  audienceDashboard: () => request<AudienceDashboard>('/api/v1/audience/dashboard'),
  audienceFilterPresets: () =>
    request<FilterPreset[]>('/api/v1/audience/filters/presets'),
  audienceSources: (params: Record<string, string> = {}) =>
    request<SourceList>('/api/v1/audience/sources?' + new URLSearchParams(params).toString()),
  createSource: (payload: {
    reference?: string
    title?: string
    source_type?: string
    account_id?: string | null
    channel_id?: string
  }) =>
    request<AudienceSource>('/api/v1/audience/sources', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getSource: (id: string) => request<AudienceSource>(`/api/v1/audience/sources/${id}`),
  updateSource: (
    id: string,
    payload: { title?: string; enabled?: boolean; account_id?: string | null; source_type?: string },
  ) =>
    request<AudienceSource>(`/api/v1/audience/sources/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteSource: (id: string) =>
    request<null>(`/api/v1/audience/sources/${id}`, { method: 'DELETE' }),
  checkSource: (id: string) =>
    request<SourceCheck>(`/api/v1/audience/sources/${id}/check`, { method: 'POST' }),
  previewScan: (id: string) =>
    request<ScanPreview>(`/api/v1/audience/sources/${id}/scan/preview`, { method: 'POST' }),
  startScan: (id: string) =>
    request<ScanResult>(`/api/v1/audience/sources/${id}/scan`, { method: 'POST' }),
  scanProgress: (id: string) =>
    request<ScanResult>(`/api/v1/audience/sources/${id}/scan/progress`),
  pauseScan: (id: string) =>
    request<ScanResult>(`/api/v1/audience/sources/${id}/scan/pause`, { method: 'POST' }),
  resumeScan: (id: string) =>
    request<ScanResult>(`/api/v1/audience/sources/${id}/scan/resume`, { method: 'POST' }),
  cancelScan: (id: string) =>
    request<ScanResult>(`/api/v1/audience/sources/${id}/scan/cancel`, { method: 'POST' }),

  audienceUsers: (params: Record<string, string> = {}) =>
    request<AudienceUserList>('/api/v1/audience/users?' + new URLSearchParams(params).toString()),
  audienceUser: (id: string) => request<AudienceUserDetail>(`/api/v1/audience/users/${id}`),
  audienceTags: () => request<AudienceTag[]>('/api/v1/audience/tags'),
  assignTags: (userIds: string[], tags: string[]) =>
    request<{ updated: number }>('/api/v1/audience/tags/assign', {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds, tags }),
    }),
  removeTags: (userIds: string[], tags: string[]) =>
    request<{ updated: number }>('/api/v1/audience/tags/remove', {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds, tags }),
    }),
  renameTag: (oldName: string, newName: string) =>
    request<{ updated: number }>('/api/v1/audience/tags/rename', {
      method: 'POST',
      body: JSON.stringify({ old: oldName, new: newName }),
    }),
  deleteTag: (tag: string) =>
    request<{ updated: number }>('/api/v1/audience/tags/' + encodeURIComponent(tag), {
      method: 'DELETE',
    }),
  bulkUserStatus: (userIds: string[], status: string) =>
    request<{ updated: number }>('/api/v1/audience/users/bulk-status', {
      method: 'POST',
      body: JSON.stringify({ user_ids: userIds, status }),
    }),
  exportPreview: (payload: {
    format?: string
    source_id?: string | null
    tag?: string | null
    include_pii?: boolean
    limit?: number
  }) =>
    request<ExportPreview>('/api/v1/audience/export/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  exportAudience: (payload: {
    format?: string
    source_id?: string | null
    tag?: string | null
    include_pii?: boolean
    limit?: number
  }) =>
    request<ExportResult>('/api/v1/audience/export', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  importAudience: (payload: { data: string; format?: string; source_id?: string | null }) =>
    request<ImportResult>('/api/v1/audience/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Analytics (PHASE 8)
  analyticsOverview: (days = 30, channelId = '') =>
    request<AnalyticsOverview>(
      `/api/v1/analytics/overview?days=${days}&channel_id=${encodeURIComponent(channelId)}`,
    ),
  analyticsContent: (days = 30, channelId = '') =>
    request<ContentAnalytics>(
      `/api/v1/analytics/content?days=${days}&channel_id=${encodeURIComponent(channelId)}`,
    ),
  analyticsReactions: (days = 30, channelId = '') =>
    request<ReactionsAnalytics>(
      `/api/v1/analytics/reactions?days=${days}&channel_id=${encodeURIComponent(channelId)}`,
    ),
  analyticsAudience: (days = 30, channelId = '') =>
    request<AudienceAnalytics>(
      `/api/v1/analytics/audience?days=${days}&channel_id=${encodeURIComponent(channelId)}`,
    ),

  // Telegram Mini App (PHASE 9)
  miniappConfig: () => request<MiniAppConfig>('/api/v1/miniapp/config'),
  miniappAuth: (initData: string) =>
    request<MiniAppAuthResponse>('/api/v1/miniapp/auth', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData }),
    }),
  miniappMe: () => request<MiniAppMe>('/api/v1/miniapp/me'),
  miniappLogout: () => request<{ ok: boolean }>('/api/v1/miniapp/logout', { method: 'POST' }),
  miniappSetup: (publicUrl: string) =>
    request<MiniAppSetupResult>('/api/v1/miniapp/setup', {
      method: 'POST',
      body: JSON.stringify({ public_url: publicUrl }),
    }),

  // Backup / restore (PHASE 10)
  backupInfo: () => request<BackupInfo>('/api/v1/backup/info'),
  backups: () => request<BackupList>('/api/v1/backup'),
  createBackup: (payload: { include_sessions?: boolean | null; note?: string }) =>
    request<BackupEntry>('/api/v1/backup', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  restoreBackup: (filename: string) =>
    request<RestoreResult>(
      '/api/v1/backup/restore?filename=' + encodeURIComponent(filename),
      { method: 'POST' },
    ),
  deleteBackup: (filename: string) =>
    request<{ deleted: boolean }>('/api/v1/backup/' + encodeURIComponent(filename), {
      method: 'DELETE',
    }),
  backupDownloadUrl: (filename: string) =>
    '/api/v1/backup/download?filename=' + encodeURIComponent(filename),
  configExportUrl: () => '/api/v1/backup/config/export',

  // Post-1.0 hardening: permission probe
  permissionCheck: (payload: { account_id: string; target?: string; channel_id?: string }) =>
    request<PermissionResult>('/api/v1/permissions/check', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  permissionLatest: () => request<PermissionResult | null>('/api/v1/permissions/latest'),
  permissionHistory: (limit = 20) =>
    request<PermissionHistory>(`/api/v1/permissions/history?limit=${limit}`),

  // Post-1.0 hardening: manager bot runtime + notifications
  managerStatus: () => request<ManagerStatus>('/api/v1/manager/status'),
  managerNotifications: () =>
    request<NotificationSettings>('/api/v1/manager/notifications'),
  managerUpdateNotifications: (payload: { enabled?: boolean; categories?: Record<string, boolean> }) =>
    request<NotificationSettings>('/api/v1/manager/notifications', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  // Channel Registry (hardening: one shared channel identity)
  channels: (params: Record<string, string> = {}) =>
    request<ChannelList>('/api/v1/channels?' + new URLSearchParams(params).toString()),
  channel: (id: string) => request<Channel>(`/api/v1/channels/${id}`),
  channelsSummary: () => request<ChannelSummary>('/api/v1/channels/summary'),
  addChannel: (payload: {
    reference: string
    title?: string
    kind?: string
    make_default?: boolean
    note?: string
  }) => request<Channel>('/api/v1/channels', { method: 'POST', body: JSON.stringify(payload) }),
  updateChannel: (id: string, payload: Record<string, unknown>) =>
    request<Channel>(`/api/v1/channels/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  setChannelDefault: (id: string) =>
    request<Channel>(`/api/v1/channels/${id}/default`, { method: 'POST' }),
  setChannelModules: (id: string, modules: Record<string, boolean>) =>
    request<Channel>(`/api/v1/channels/${id}/modules`, {
      method: 'POST',
      body: JSON.stringify({ modules }),
    }),
  verifyChannel: (id: string, accountId: string) =>
    request<ChannelVerification>(`/api/v1/channels/${id}/verify`, {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId }),
    }),
  removeChannel: (id: string) =>
    request<null>(`/api/v1/channels/${id}`, { method: 'DELETE' }),

  // Diagnostics (product polish): status, safe actions, redacted report.
  diagnostics: () => request<DiagnosticsReport>('/api/v1/diagnostics'),
  diagnosticActions: () =>
    request<MaintenanceAction[]>('/api/v1/diagnostics/actions'),
  runDiagnosticAction: (key: string) =>
    request<MaintenanceResult>(`/api/v1/diagnostics/actions/${key}`, { method: 'POST' }),
  diagnosticsReportUrl: (format: 'json' | 'txt' | 'zip' = 'zip') =>
    `/api/v1/diagnostics/report?format=${format}`,

  // Help / explanations (novice mode): shared by Web UI, Mini App, Setup Wizard.
  helpTopics: () => request<HelpTopic[]>('/api/v1/help/topics'),
  helpPrefs: () => request<UiPrefs>('/api/v1/help/prefs'),
  updateHelpPrefs: (payload: { show_explanations?: boolean; language?: string }) =>
    request<UiPrefs>('/api/v1/help/prefs', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  // Product slice: bot↔channel bindings + reaction capabilities.
  bindings: (params: Record<string, string> = {}) =>
    request<BindingList>('/api/v1/bindings?' + new URLSearchParams(params).toString()),
  connectBinding: (payload: { bot_id: string; channel_id: string; function?: string }) =>
    request<Binding>('/api/v1/bindings', { method: 'POST', body: JSON.stringify(payload) }),
  checkBinding: (id: string) =>
    request<BindingCheck>(`/api/v1/bindings/${id}/check`, { method: 'POST' }),
  checkChannelBindings: (channelId: string) =>
    request<BindingCheck[]>(`/api/v1/bindings/channel/${channelId}/check`, { method: 'POST' }),
  removeBinding: (id: string) =>
    request<{ deleted: boolean }>(`/api/v1/bindings/${id}`, { method: 'DELETE' }),
  capability: (channelId: string) =>
    request<Capability>(`/api/v1/capabilities/${channelId}`),
  probeCapability: (channelId: string) =>
    request<Capability>(`/api/v1/capabilities/${channelId}/probe`, { method: 'POST' }),

  // Product slice: invite campaigns (no session required).
  campaigns: () => request<CampaignList>('/api/v1/campaigns'),
  campaign: (id: string) => request<CampaignDetail>(`/api/v1/campaigns/${id}`),
  createCampaign: (payload: {
    name: string
    channel_id?: string
    target?: string
    risk_mode?: string
    requires_approval?: boolean
    note?: string
  }) => request<Campaign>('/api/v1/campaigns', { method: 'POST', body: JSON.stringify(payload) }),
  setCampaignStatus: (id: string, status: string) =>
    request<Campaign>(`/api/v1/campaigns/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
  deleteCampaign: (id: string) =>
    request<{ deleted: boolean }>(`/api/v1/campaigns/${id}`, { method: 'DELETE' }),
  addCampaignLink: (
    id: string,
    payload: { label?: string; join_request?: boolean; member_limit?: number },
  ) =>
    request<CampaignLink>(`/api/v1/campaigns/${id}/links`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  revokeCampaignLink: (id: string, linkId: string) =>
    request<CampaignLink>(`/api/v1/campaigns/${id}/links/${linkId}/revoke`, { method: 'POST' }),

  // Product slice: donor quality indicators.
  donors: () => request<DonorList>('/api/v1/donors'),
  analyzeDonor: (sourceId: string) =>
    request<DonorMetric>(`/api/v1/donors/analyze/${sourceId}`, { method: 'POST' }),
  analyzeAllDonors: () => request<DonorList>('/api/v1/donors/analyze', { method: 'POST' }),

  // Product slice: backup destinations.
  destinations: () => request<DestinationList>('/api/v1/backup/destinations'),
  addDestination: (payload: {
    kind: string
    label?: string
    enabled?: boolean
    config?: Record<string, unknown>
    token?: string
  }) =>
    request<Destination>('/api/v1/backup/destinations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateDestination: (id: string, payload: Record<string, unknown>) =>
    request<Destination>(`/api/v1/backup/destinations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  checkDestination: (id: string) =>
    request<Destination>(`/api/v1/backup/destinations/${id}/check`, { method: 'POST' }),
  removeDestination: (id: string) =>
    request<{ deleted: boolean }>(`/api/v1/backup/destinations/${id}`, { method: 'DELETE' }),
  deliverToDestinations: () =>
    request<DeliveryResult[]>('/api/v1/backup/destinations/deliver', { method: 'POST' }),

  // Product slice: first-run promotion wizard.
  wizardPresets: () => request<WizardPreset[]>('/api/v1/promotion/presets'),
  wizardState: () => request<WizardState>('/api/v1/promotion'),
  setWizardPreset: (preset: string) =>
    request<WizardState>('/api/v1/promotion/preset', {
      method: 'POST',
      body: JSON.stringify({ preset }),
    }),
  setWizardStep: (step: string) =>
    request<WizardState>('/api/v1/promotion/step', {
      method: 'POST',
      body: JSON.stringify({ step }),
    }),
  finishWizard: () => request<WizardState>('/api/v1/promotion/finish', { method: 'POST' }),
  dismissWizard: () => request<WizardState>('/api/v1/promotion/dismiss', { method: 'POST' }),

  // Product slice: conservative auto-update.
  updateStatus: () => request<UpdateStatus>('/api/v1/update'),
  setUpdateEnabled: (enabled: boolean) =>
    request<UpdateStatus>('/api/v1/update/enabled', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  checkUpdate: () => request<UpdateStatus>('/api/v1/update/check', { method: 'POST' }),
  downloadUpdate: () => request<UpdateStatus>('/api/v1/update/download', { method: 'POST' }),

  // v1.1: proxy profiles (connection routes; never a Telegram limit bypass).
  proxies: () => request<ProxyList>('/api/v1/proxies'),
  addProxy: (payload: {
    name?: string
    kind: string
    host: string
    port: number
    username?: string
    password?: string
    enabled?: boolean
  }) => request<ProxyProfile>('/api/v1/proxies', { method: 'POST', body: JSON.stringify(payload) }),
  updateProxy: (id: string, payload: Record<string, unknown>) =>
    request<ProxyProfile>(`/api/v1/proxies/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  removeProxy: (id: string) =>
    request<null>(`/api/v1/proxies/${id}`, { method: 'DELETE' }),
  checkProxy: (id: string) =>
    request<ProxyCheck>(`/api/v1/proxies/${id}/check`, { method: 'POST' }),
  bindProxy: (accountId: string, profileId: string) =>
    request<{ account_id: string; proxy_id: string }>('/api/v1/proxies/bind', {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId, profile_id: profileId }),
    }),

  // v1.1: donor discovery (candidates are proposals; adding is explicit).
  discoveryProviders: () =>
    request<DiscoveryProviderStatus[]>('/api/v1/discovery/providers'),
  discoverySearch: (payload: {
    topic: string
    keywords?: string[]
    language?: string
    min_subscribers?: number
    max_subscribers?: number
    active_only?: boolean
    period_days?: number
    seed_channel?: string
    providers?: string[]
    account_id?: string
  }) => request<DiscoveryResult>('/api/v1/discovery/search', { method: 'POST', body: JSON.stringify(payload) }),
  discoveryCandidates: () => request<CandidateList>('/api/v1/discovery/candidates'),
  discoveryCompare: (candidateIds: string[]) =>
    request<DiscoveryCompare>('/api/v1/discovery/compare', {
      method: 'POST',
      body: JSON.stringify({ candidate_ids: candidateIds }),
    }),
  discoveryAdd: (candidateId: string) =>
    request<{ candidate: DonorCandidate; source_id: string }>(
      `/api/v1/discovery/candidates/${candidateId}/add`,
      { method: 'POST' },
    ),
  discoveryClear: () =>
    request<{ deleted: number }>('/api/v1/discovery/candidates/clear', { method: 'POST' }),

  // v1.2: Content Studio (sources → items → clean → plan → publish).
  contentProviders: () => request<ContentProviderStatus[]>('/api/v1/content/providers'),
  contentDashboard: () => request<ContentDashboard>('/api/v1/content/dashboard'),
  contentSources: () => request<ContentSourceList>('/api/v1/content/sources'),
  addContentSource: (payload: {
    kind: string
    reference: string
    title?: string
    enabled?: boolean
    channel_id?: string
    account_id?: string
  }) => request<ContentSource>('/api/v1/content/sources', { method: 'POST', body: JSON.stringify(payload) }),
  removeContentSource: (id: string) =>
    request<null>(`/api/v1/content/sources/${id}`, { method: 'DELETE' }),
  grabContentSource: (id: string, limit = 20) =>
    request<GrabResult>(`/api/v1/content/sources/${id}/grab?limit=${limit}`, { method: 'POST' }),
  contentModeration: (sourceId: string) =>
    request<ContentModeration>(`/api/v1/content/sources/${sourceId}/moderation`),
  updateContentModeration: (sourceId: string, payload: Partial<ContentModeration>) =>
    request<ContentModeration>(`/api/v1/content/sources/${sourceId}/moderation`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  contentItems: (params: Record<string, string> = {}) =>
    request<ContentItemList>('/api/v1/content/items?' + new URLSearchParams(params).toString()),
  contentItem: (id: string) => request<ContentItem>(`/api/v1/content/items/${id}`),
  updateContentItem: (id: string, payload: Record<string, unknown>) =>
    request<ContentItem>(`/api/v1/content/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  removeContentItem: (id: string) =>
    request<null>(`/api/v1/content/items/${id}`, { method: 'DELETE' }),
  contentCleanPreview: (id: string) =>
    request<CleanPreview>(`/api/v1/content/items/${id}/clean`),
  applyContentClean: (id: string, cleaned?: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/clean`, {
      method: 'POST',
      body: JSON.stringify(cleaned ? { cleaned } : {}),
    }),
  revertContentClean: (id: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/clean/revert`, { method: 'POST' }),
  contentRewrite: (id: string, mode: string) =>
    request<RewriteResult>(`/api/v1/content/items/${id}/rewrite`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
  applyContentRewrite: (id: string, mode: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/rewrite/apply`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
  contentRights: (id: string) => request<RightsInfo>(`/api/v1/content/items/${id}/rights`),
  releaseContentItem: (id: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/release`, { method: 'POST' }),
  contentValidate: (id: string) =>
    request<ContentValidation>(`/api/v1/content/items/${id}/validate`),
  contentPreview: (id: string) => request<ContentPreview>(`/api/v1/content/items/${id}/preview`),
  contentButtons: (id: string) => request<ContentButtonSet>(`/api/v1/content/items/${id}/buttons`),
  saveContentButtons: (id: string, rows: ContentButton[][]) =>
    request<ContentButtonSet>(`/api/v1/content/items/${id}/buttons`, {
      method: 'PUT',
      body: JSON.stringify({ rows }),
    }),
  planContent: (id: string, payload: { targets: { channel_id: string; scheduled_at?: string; text_override?: string; profile_key?: string; ai_instructions?: string }[]; mode?: string }) =>
    request<ContentPlan>(`/api/v1/content/items/${id}/plan`, { method: 'POST', body: JSON.stringify(payload) }),
  contentPublications: (id: string) =>
    request<ContentPlan>(`/api/v1/content/items/${id}/publications`),
  scheduleContentPublication: (id: string, scheduledAt: string | null) =>
    request<ContentPublication>(`/api/v1/content/publications/${id}/schedule`, {
      method: 'POST',
      body: JSON.stringify({ scheduled_at: scheduledAt }),
    }),
  cancelContentPublication: (id: string) =>
    request<ContentPublication>(`/api/v1/content/publications/${id}/cancel`, { method: 'POST' }),
  publishContentPublication: (id: string) =>
    request<PublishResult>(`/api/v1/content/publications/${id}/publish`, { method: 'POST' }),
  retryContentPublication: (id: string) =>
    request<PublishResult>(`/api/v1/content/publications/${id}/retry`, { method: 'POST' }),
  contentCalendar: (start?: string, end?: string) =>
    request<ContentCalendar>(
      '/api/v1/content/calendar?' +
        new URLSearchParams({ ...(start ? { start } : {}), ...(end ? { end } : {}) }).toString(),
    ),
  contentTick: () =>
    request<{ published: number; deleted: number; comments: number; due: number }>(
      '/api/v1/content/tick',
      { method: 'POST' },
    ),

  // v1.9: Content Operations pipeline (profiles, AI, moderation, rules).
  aiProfiles: () => request<AiProfile[]>('/api/v1/content/ai-profiles'),
  createAiProfile: (payload: Partial<AiProfile> & { key: string }) =>
    request<AiProfile>('/api/v1/content/ai-profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateAiProfile: (id: string, payload: Partial<AiProfile>) =>
    request<AiProfile>(`/api/v1/content/ai-profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteAiProfile: (id: string) =>
    request<null>(`/api/v1/content/ai-profiles/${id}`, { method: 'DELETE' }),
  classifyContentItem: (id: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/ai/classify`, { method: 'POST' }),
  processContentItem: (id: string, profileKey: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/ai/process`, {
      method: 'POST',
      body: JSON.stringify({ profile_key: profileKey }),
    }),
  moderateContentItem: (id: string, decision: string, note = '') =>
    request<ContentItem>(`/api/v1/content/items/${id}/moderate`, {
      method: 'POST',
      body: JSON.stringify({ decision, note }),
    }),
  applyContentRules: (id: string) =>
    request<ContentItem>(`/api/v1/content/items/${id}/apply-rules`, { method: 'POST' }),
  automationRules: () => request<AutomationRule[]>('/api/v1/content/automation-rules'),
  createAutomationRule: (payload: Partial<AutomationRule>) =>
    request<AutomationRule>('/api/v1/content/automation-rules', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateAutomationRule: (id: string, payload: Partial<AutomationRule>) =>
    request<AutomationRule>(`/api/v1/content/automation-rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  deleteAutomationRule: (id: string) =>
    request<null>(`/api/v1/content/automation-rules/${id}`, { method: 'DELETE' }),
  pipelineAnalytics: (limit = 50) =>
    request<PipelineAnalytics>(`/api/v1/content/pipeline/analytics?limit=${limit}`),

  // Editorial Workspace (v1.4)
  editorialRooms: () => request<EditorialRoomList>('/api/v1/editorial/rooms'),
  createEditorialRoom: (payload: {
    channel_id: string
    group_chat_id: number
    bot_id?: string
    group_title?: string
  }) =>
    request<EditorialRoom>('/api/v1/editorial/rooms', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteEditorialRoom: (id: string) =>
    request<{ ok: boolean }>(`/api/v1/editorial/rooms/${id}`, { method: 'DELETE' }),
  checkEditorialRoom: (id: string, createTopics = true) =>
    request<EditorialRoomCheck>(
      `/api/v1/editorial/rooms/${id}/check?create_topics=${createTopics}`,
      { method: 'POST' },
    ),
  editorialMembers: (id: string) =>
    request<EditorialMember[]>(`/api/v1/editorial/rooms/${id}/members`),
  setEditorialMember: (
    id: string,
    payload: {
      telegram_user_id: number
      role: string
      display_name?: string
      username?: string
      enabled?: boolean
    },
  ) =>
    request<EditorialMember>(`/api/v1/editorial/rooms/${id}/members`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  removeEditorialMember: (id: string, userId: number) =>
    request<{ ok: boolean }>(`/api/v1/editorial/rooms/${id}/members/${userId}`, {
      method: 'DELETE',
    }),
  editorialBoard: (id: string) => request<EditorialBoard>(`/api/v1/editorial/rooms/${id}/board`),
  editorialEnqueue: (
    id: string,
    payload: { content_item_id: string; channel_id?: string; title?: string },
  ) =>
    request<EditorialItem>(`/api/v1/editorial/rooms/${id}/items`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  editorialMove: (
    id: string,
    itemId: string,
    payload: { status: string; actor_telegram_id?: number; expected_version?: number },
  ) =>
    request<EditorialActionResult>(`/api/v1/editorial/rooms/${id}/items/${itemId}/move`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  editorialReorder: (
    id: string,
    payload: { status: string; ordered_ids: string[]; actor_telegram_id?: number },
  ) =>
    request<EditorialBoard>(`/api/v1/editorial/rooms/${id}/reorder`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  editorialAudit: (id: string, itemId = '') =>
    request<EditorialAudit[]>(
      `/api/v1/editorial/rooms/${id}/audit` + (itemId ? `?item_id=${itemId}` : ''),
    ),

  // Notification Center (v1.4)
  notificationSettings: () => request<NotificationSettings>('/api/v1/notifications/settings'),
  updateNotificationSettings: (payload: {
    enabled?: boolean
    categories?: Record<string, boolean>
    quiet_hours_enabled?: boolean
    quiet_hours_start?: number
    quiet_hours_end?: number
    quiet_hours_tz?: string
    aggregation_enabled?: boolean
  }) =>
    request<NotificationSettings>('/api/v1/notifications/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  notifications: (params: Record<string, string> = {}) =>
    request<NotificationList>(
      '/api/v1/notifications?' + new URLSearchParams(params).toString(),
    ),
  notificationDashboard: () =>
    request<NotificationDashboard>('/api/v1/notifications/dashboard'),
  sendTestNotification: (payload: { category?: string; priority?: string } = {}) =>
    request<NotificationItem>('/api/v1/notifications/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  markNotificationRead: (id: string) =>
    request<NotificationItem>(`/api/v1/notifications/${id}/read`, { method: 'POST' }),

  // Consistency ("Проверка целостности", v1.5)
  consistency: () => request<ConsistencyReport>('/api/v1/consistency'),

  // Capability graph (v1.5)
  capabilityGraph: () => request<CapabilityState[]>('/api/v1/capability-graph'),

  // Owner Auth (v1.6)
  ownerStatus: () => request<OwnerStatus>('/api/v1/owner/status'),
  ownerSetup: (payload: {
    secret: string
    method?: string
    display_name?: string
    recovery_hint?: string
  }) =>
    request<OwnerToken>('/api/v1/owner/setup', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  ownerLogin: (secret: string) =>
    request<OwnerToken>('/api/v1/owner/login', {
      method: 'POST',
      body: JSON.stringify({ secret }),
    }),
  ownerLogout: () => request<OwnerStatus>('/api/v1/owner/logout', { method: 'POST' }),
  ownerSetProtection: (enabled: boolean) =>
    request<OwnerStatus>('/api/v1/owner/protection', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  ownerChangePassword: (current: string, newSecret: string) =>
    request<OwnerStatus>('/api/v1/owner/password', {
      method: 'POST',
      body: JSON.stringify({ current, new_secret: newSecret }),
    }),

  // Config Sync (v1.6)
  syncStatus: () => request<SyncStatus>('/api/v1/owner/sync/status'),
  syncConfigure: (provider: string, enabled = true) =>
    request<SyncStatus>('/api/v1/owner/sync/configure', {
      method: 'POST',
      body: JSON.stringify({ provider, enabled }),
    }),
  syncUpload: (secret: string) =>
    request<SyncStatus>('/api/v1/owner/sync/upload', {
      method: 'POST',
      body: JSON.stringify({ secret }),
    }),
  syncDownloadPreview: (secret: string) =>
    request<SyncRestorePreview>('/api/v1/owner/sync/download/preview', {
      method: 'POST',
      body: JSON.stringify({ secret }),
    }),
  syncDownloadApply: (secret: string, keepLocal = false) =>
    request<SyncStatus>('/api/v1/owner/sync/download/apply', {
      method: 'POST',
      body: JSON.stringify({ secret, keep_local: keepLocal }),
    }),
  syncConflict: () => request<SyncConflict>('/api/v1/owner/sync/conflict'),
  syncDisconnect: () =>
    request<SyncStatus>('/api/v1/owner/sync/disconnect', { method: 'POST' }),
  syncGoogleAuth: () => request<SyncGoogleAuth>('/api/v1/owner/sync/google/auth'),
  syncGoogleConnect: (accessToken: string, refreshToken = '') =>
    request<SyncStatus>('/api/v1/owner/sync/google/connect', {
      method: 'POST',
      body: JSON.stringify({ access_token: accessToken, refresh_token: refreshToken }),
    }),

  // AI Gateway (v1.8): providers, routing, Web wrappers, use-case matrix.
  gatewayStatus: () => request<GatewayStatus>('/api/v1/ai-gateway/status'),
  gatewayProviders: () =>
    request<GatewayProviderList>('/api/v1/ai-gateway/providers'),
  gatewayUpsertProvider: (payload: {
    provider: string
    kind: string
    model?: string
    base_url?: string
    api_key?: string
    auth_mode?: string
    enabled?: boolean
    priority?: number
    cost?: string
    capabilities?: Partial<GatewayCapability>
    wrapper_id?: string
    note?: string
  }) =>
    request<GatewayProvider>('/api/v1/ai-gateway/providers', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  gatewayToggleProvider: (provider: string, enabled: boolean) =>
    request<GatewayProvider>(`/api/v1/ai-gateway/providers/${encodeURIComponent(provider)}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  gatewayRemoveProvider: (provider: string) =>
    request<null>(`/api/v1/ai-gateway/providers/${encodeURIComponent(provider)}`, {
      method: 'DELETE',
    }),
  gatewaySettings: () => request<GatewaySettings>('/api/v1/ai-gateway/settings'),
  gatewaySetSetting: (key: string, value: unknown) =>
    request<GatewaySettings>('/api/v1/ai-gateway/settings', {
      method: 'PUT',
      body: JSON.stringify({ key, value }),
    }),
  gatewayChat: (payload: {
    text: string
    system?: string
    strategy?: string
    provider?: string
    task?: string
    timeout_seconds?: number
    structured?: boolean
    modality?: string
  }) =>
    request<GatewayChatResult>('/api/v1/ai-gateway/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  gatewayWrappers: () =>
    request<{ items: GatewayWrapper[] }>('/api/v1/ai-gateway/wrappers'),
  gatewayBrowser: () =>
    request<GatewayBrowserStatus>('/api/v1/ai-gateway/browser'),
  gatewayUseCases: () =>
    request<{ items: GatewayUseCase[] }>('/api/v1/ai-gateway/use-cases'),
  gatewayRequests: (limit = 50) =>
    request<{ items: GatewayRequestRecord[] }>(`/api/v1/ai-gateway/requests?limit=${limit}`),
}
