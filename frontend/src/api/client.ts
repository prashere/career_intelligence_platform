import { getStoredToken } from '../auth/storage';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface ScoreBreakdown {
  semantic?: number;
  eligibility?: number;
  urgency?: number;
  affinity?: number;
  composite?: number;
  semantic_raw?: number | null;
  semantic_method?: string | null;
  semantic_degraded?: boolean;
  components_available?: string[];
  weights_applied?: Record<string, number>;
  eligibility_reasons?: Array<{
    code: string;
    label: string;
    direction: string;
    weight: number;
  }>;
  reasons?: Array<{
    code: string;
    label: string;
    direction: string;
    weight?: number;
    source?: string;
  }>;
  evidence_terms?: string[];
  derived_facts?: {
    deadline?: string | null;
    deadline_note?: string | null;
    deadline_source?: string;
    funding_type?: string | null;
    funding_amount?: string | null;
    degree_levels?: string[];
    regions?: string[];
    themes?: string[];
    formats?: string[];
    remote?: boolean | null;
  };
  hide_match_percent?: boolean;
  hard_eligibility_failed?: boolean;
}

export interface OpportunityListResponse {
  items: Opportunity[];
  total: number;
  next_cursor?: string | null;
  unknown_deadline_count?: number | null;
}

export type DeadlineBucket =
  | 'overdue'
  | 'today'
  | 'within_3_days'
  | 'within_7_days'
  | 'within_30_days'
  | 'later'
  | 'unknown';

export interface OpportunityTrust {
  state: 'verified' | 'aggregator_only' | 'unchecked' | 'conflict';
  label: string;
  hint: string;
  checked_at?: string;
  primary_url?: string;
}

export interface Opportunity {
  id: string;
  title: string;
  summary?: string;
  institution?: string;
  program?: string;
  opportunity_type: string;
  url: string;
  deadline?: string;
  opens_at?: string;
  tags?: string[];
  requirements: string[];
  status?: string;
  dismiss_reason?: string;
  fit_score?: number;
  fit_percent?: number;
  fit_level?: string;
  fit_explanation?: string;
  score_breakdown?: ScoreBreakdown;
  rank_position?: number;
  trust: OpportunityTrust;
  verification_status?: string;
  verified_at?: string;
  days_until_deadline?: number;
  urgency_label?: string;
  deadline_bucket?: DeadlineBucket;
}

export interface FeedResponse {
  summary: {
    new_since: number;
    deadlines_this_week: number;
    prep_milestones_due: number;
  };
  scholarships: Opportunity[];
  fellowships: Opportunity[];
  other: Opportunity[];
}

export interface DashboardResponse {
  updated_cards: Opportunity[];
  in_progress: Opportunity[];
  upskilling: LearningItem[];
  notifications: Notification[];
}

export interface LearningItem {
  id: string;
  title: string;
  item_type: string;
  progress_percent: number;
  status: string;
  outcome_notes?: string;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
}

export interface UserProfile {
  id: string;
  name: string;
  long_term_goals: string;
  research_interests: string[];
  skills: string[];
  target_regions: string[];
  target_universities: string[];
  degree_level?: string;
}

export interface ChatResponse {
  reply: string;
  citations: string[];
  pending_actions?: { action: string; title: string; requires_approval?: boolean }[];
}

export interface WeeklyFocus {
  deadlines: { title: string; deadline: string; id: string }[];
  prep_tasks: { title: string; due?: string }[];
  learning_tasks: { title: string; progress: number; status: string }[];
  focus_summary: string;
}

export const api = {
  health: () => request<{ status: string }>('/api/v1/health'),
  feed: (params?: { search?: string; funding_type?: string; opportunity_type?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.search) qs.set('search', params.search);
    if (params?.funding_type) qs.set('funding_type', params.funding_type);
    if (params?.opportunity_type) qs.set('opportunity_type', params.opportunity_type);
    if (params?.status) qs.set('status', params.status);
    const q = qs.toString();
    return request<FeedResponse>(`/api/v1/feed${q ? `?${q}` : ''}`);
  },
  opportunities: (params?: {
    bucket?: string;
    sort?: string;
    search?: string;
    opportunity_type?: string;
    funding_type?: string;
    verified_only?: boolean;
    limit?: number;
    cursor?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.bucket) qs.set('bucket', params.bucket);
    if (params?.sort) qs.set('sort', params.sort);
    if (params?.search) qs.set('search', params.search);
    if (params?.opportunity_type) qs.set('opportunity_type', params.opportunity_type);
    if (params?.funding_type) qs.set('funding_type', params.funding_type);
    if (params?.verified_only) qs.set('verified_only', 'true');
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.cursor) qs.set('cursor', params.cursor);
    const q = qs.toString();
    return request<OpportunityListResponse>(`/api/v1/opportunities${q ? `?${q}` : ''}`);
  },
  opportunity: (id: string) => request<Opportunity>(`/api/v1/opportunities/${id}`),
  updateStatus: (
    id: string,
    body: { status: string; dismiss_reason?: string; notes?: string },
  ) =>
    request<{
      id: string;
      status: string;
      dismiss_reason?: string | null;
      fit_score?: number;
      fit_level?: string;
      score_breakdown?: ScoreBreakdown;
      status_changed_at?: string;
      status_history?: Array<Record<string, string>>;
    }>(`/api/v1/opportunities/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  chat: (id: string, message: string) =>
    request<ChatResponse>(`/api/v1/opportunities/${id}/chat`, { method: 'POST', body: JSON.stringify({ message }) }),
  agentChat: (id: string, message: string) =>
    request<ChatResponse>(`/api/v1/opportunities/${id}/agent`, { method: 'POST', body: JSON.stringify({ message }) }),
  dashboard: () => request<DashboardResponse>('/api/v1/dashboard'),
  profile: () => request<UserProfile>('/api/v1/profile'),
  updateProfile: (data: Partial<UserProfile>) =>
    request<UserProfile>('/api/v1/profile', { method: 'PATCH', body: JSON.stringify(data) }),
  rerank: () => request('/api/v1/profile/rank', { method: 'POST' }),
  weeklyFocus: () => request<WeeklyFocus>('/api/v1/planning/weekly'),
  learning: () => request<LearningItem[]>('/api/v1/learning'),
  createLearning: (data: Partial<LearningItem>) =>
    request<LearningItem>('/api/v1/learning', { method: 'POST', body: JSON.stringify(data) }),
  notifications: () => request<Notification[]>('/api/v1/notifications'),
  markRead: (id: string) => request(`/api/v1/notifications/${id}/read`, { method: 'PATCH' }),
  calendarLinks: (id: string) =>
    request<{ google_url: string; has_deadline: boolean }>(
      `/api/v1/opportunities/${id}/calendar/links`,
    ),
  people: () => request<Person[]>('/api/v1/people'),
  createPerson: (data: Partial<Person>) =>
    request<Person>('/api/v1/people', { method: 'POST', body: JSON.stringify(data) }),
  communities: () => request<Community[]>('/api/v1/communities'),
  createCommunity: (data: Partial<Community>) =>
    request<Community>('/api/v1/communities', { method: 'POST', body: JSON.stringify(data) }),
  experiences: () => request<Experience[]>('/api/v1/experiences'),
  createExperience: (data: Partial<Experience>) =>
    request<Experience>('/api/v1/experiences', { method: 'POST', body: JSON.stringify(data) }),
};

export interface Person {
  id: string;
  name: string;
  role: string;
  affiliation?: string;
  research_areas: string[];
  relationship_notes?: string;
}

export interface Community {
  id: string;
  name: string;
  community_type: string;
  description?: string;
  relevance_notes?: string;
}

export interface Experience {
  id: string;
  title: string;
  experience_type: string;
  description?: string;
  status: string;
}
