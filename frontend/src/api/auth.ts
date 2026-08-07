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

export const adminApi = {
  schedulers: () => request<SchedulerJob[]>('/api/v1/admin/schedulers'),
  updateScheduler: (key: string, body: SchedulerUpdate) =>
    request<SchedulerJob>(`/api/v1/admin/schedulers/${encodeURIComponent(key)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  seedSchedulers: () =>
    request<{ seeded: number }>('/api/v1/admin/schedulers/seed', { method: 'POST' }),
};
