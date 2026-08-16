import { request } from './http';
import type { AuthUser } from '../auth/storage';

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export const authApi = {
  login: (email: string, password: string) =>
    request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, name?: string) =>
    request<TokenResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name: name || '' }),
    }),
  me: () => request<AuthUser>('/api/v1/auth/me'),
};

export interface SchedulerJob {
  id: string;
  key: string;
  name: string;
  description: string;
  task_path: string;
  schedule_kind: 'cron' | 'interval';
  cron_minute: string | null;
  cron_hour: string | null;
  cron_day_of_week: string | null;
  interval_seconds: number | null;
  is_enabled: boolean;
  category: string;
  last_run_at: string | null;
  updated_at: string;
}

export interface SchedulerUpdate {
  is_enabled?: boolean;
  schedule_kind?: 'cron' | 'interval';
  cron_minute?: string;
  cron_hour?: string;
  cron_day_of_week?: string;
  interval_seconds?: number;
}

export interface IngestionOverview {
  total_opportunities: number;
  total_sources: number;
  active_sources: number;
  sources_with_errors: number;
  last_run_at: string | null;
}

export interface SourceHealth {
  id: string;
  name: string;
  registry_id: string | null;
  fetch_mode: string;
  is_active: boolean;
  last_fetched_at: string | null;
  next_fetch_at: string | null;
  consecutive_failures: number;
  last_error: string | null;
  opportunity_count: number;
}

export interface IngestionRun {
  id: string;
  source_id: string | null;
  status: string;
  discovered: number;
  prefilter_drop: number;
  fetched: number;
  created: number;
  updated: number;
  rejected: number;
  errors: number;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
  meta: Record<string, unknown>;
}

export interface RejectedItem {
  id: string;
  run_id: string;
  source_id: string | null;
  stage: string;
  reason: string;
  url: string | null;
  title: string | null;
  snippet: string | null;
  meta?: Record<string, unknown>;
  created_at: string;
}

export interface IngestionFetchResult {
  ok?: boolean;
  error?: string;
  run_id?: string;
  created?: number;
  updated?: number;
  discovered?: number;
  prefilter_drop?: number;
  rejected?: number;
  errors?: number;
  skipped?: boolean;
  strategy_probes?: StrategyProbe[];
}

export interface TraceEvent {
  id: string;
  run_id: string;
  source_id: string | null;
  seq: number;
  stage: string;
  level: string;
  event: string;
  message: string;
  payload: Record<string, unknown>;
  duration_ms: number | null;
  created_at: string;
}

export interface IngestionRunDetail {
  run: IngestionRun;
  source_name: string | null;
  rejected_items: RejectedItem[];
  trace_events: TraceEvent[];
}

export interface RegistryAggregator {
  id: string;
  name: string;
  url: string | null;
  type: string | null;
  fetch_mode: string | null;
  default_active: boolean;
  discover_kind: string | null;
}

export interface StrategyProbe {
  kind: string;
  ok: boolean;
  item_count?: number;
  filtered_count?: number;
  error?: string | null;
  skipped?: boolean;
  skip_reason?: string | null;
  sample_urls?: string[];
  requires_browser?: boolean;
}

export type PlaygroundMode = 'discover' | 'dry_run' | 'persist';

export type RelevanceVerdict = 'admit' | 'investigate' | 'reject';

export interface RelevanceSignal {
  name: string;
  matched: boolean;
  strength: number;
  evidence: string[];
  found_in: string | null;
  note: string | null;
}

export interface PreviewItem {
  url: string;
  title: string;
  summary: string;
  verdict: RelevanceVerdict;
  score: number;
  corpus_score: number;
  fit_score: number;
  sufficiency: number;
  reason: string;
  stage: string;
  type_label?: string | null;
  matched?: string[];
  evidence?: string[];
  signals?: Record<string, RelevanceSignal>;
  resolved?: boolean;
  resolve_error?: string | null;
  /** Present on runs recorded before the relevance gate shipped. */
  prefilter_pass?: boolean | null;
  prefilter_reason?: string | null;
}

export interface PlaygroundRequest {
  source_id?: string;
  registry_id?: string;
  mode?: PlaygroundMode;
  max_items?: number;
  include_browser?: boolean;
  resolve_investigate?: boolean;
}

export interface PlaygroundResult {
  ok: boolean;
  run_id?: string;
  mode?: string;
  source_name?: string;
  registry_id?: string;
  discovered?: number;
  prefilter_drop?: number;
  admit?: number;
  investigate?: number;
  reject?: number;
  resolved?: number;
  winning_strategy?: string;
  strategy_probes?: StrategyProbe[];
  preview_items?: PreviewItem[];
  created?: number;
  updated?: number;
  rejected?: number;
  errors?: number;
  error?: string;
  dry_run?: boolean;
}

export const adminApi = {
  schedulers: () => request<SchedulerJob[]>('/api/v1/admin/schedulers'),
  updateScheduler: (key: string, body: SchedulerUpdate) =>
    request<SchedulerJob>(`/api/v1/admin/schedulers/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  seedSchedulers: () =>
    request<{ seeded: number }>('/api/v1/admin/schedulers/seed', { method: 'POST' }),
  ingestionOverview: () => request<IngestionOverview>('/api/v1/admin/ingestion/overview'),
  ingestionSources: () => request<SourceHealth[]>('/api/v1/admin/ingestion/sources'),
  ingestionRuns: (limit = 20) => request<IngestionRun[]>(`/api/v1/admin/ingestion/runs?limit=${limit}`),
  ingestionRunDetail: (runId: string) =>
    request<IngestionRunDetail>(`/api/v1/admin/ingestion/runs/${runId}`),
  ingestionRegistry: () => request<RegistryAggregator[]>('/api/v1/admin/ingestion/registry'),
  runPlayground: (body: PlaygroundRequest) =>
    request<PlaygroundResult>('/api/v1/admin/ingestion/playground', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  ingestionRejected: (limit = 50) => request<RejectedItem[]>(`/api/v1/admin/ingestion/rejected?limit=${limit}`),
  syncIngestionEnvelope: () => request<{ ok: boolean }>('/api/v1/admin/ingestion/sync-envelope', { method: 'POST' }),
  triggerIngestionFetchAll: () => request<{ status: string }>('/api/v1/admin/ingestion/fetch-all', { method: 'POST' }),
  triggerSourceFetch: (sourceId: string) =>
    request<IngestionFetchResult>(`/api/v1/admin/ingestion/sources/${sourceId}/fetch`, { method: 'POST' }),
};
