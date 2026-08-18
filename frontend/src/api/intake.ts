import { getStoredToken } from '../auth/storage';
import type {
  IntakeDraft,
  IntakeFormData,
  IntakePromptResult,
  IntakeStatus,
  IntakeSubmitResult,
  IntakeValidateResult,
  StructuredProfileResponse,
} from '../types/intake';

const API_BASE = import.meta.env.VITE_API_URL || '';

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extra,
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(options?.headers as Record<string, string> | undefined),
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const json = JSON.parse(text);
      throw new Error(json.detail?.errors?.join?.('\n') ?? json.detail ?? text);
    } catch {
      throw new Error(text || res.statusText);
    }
  }
  return res.json();
}

export const intakeApi = {
  status: () => request<IntakeStatus>('/api/v1/profile/intake/status'),

  getDraft: () => request<IntakeDraft>('/api/v1/profile/intake/draft'),

  saveDraft: (step: number, form: Record<string, unknown>, cv_text?: string) =>
    request<IntakeDraft>('/api/v1/profile/intake/draft', {
      method: 'PUT',
      body: JSON.stringify({ step, form, cv_text }),
    }),

  saveCv: (cv_text: string) =>
    request<{ ok: boolean; length: number }>('/api/v1/profile/intake/cv', {
      method: 'PUT',
      body: JSON.stringify({ cv_text }),
    }),

  uploadCvFile: async (file: File) => {
    const token = getStoredToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;

    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/v1/profile/intake/cv/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      try {
        const json = JSON.parse(text);
        throw new Error(typeof json.detail === 'string' ? json.detail : text);
      } catch (e) {
        if (e instanceof Error && e.message !== text) throw e;
        throw new Error(text || res.statusText);
      }
    }
    return res.json() as Promise<{ ok: boolean; text: string; length: number; filename: string }>;
  },

  submit: (step: number, form: Record<string, unknown>, cv_text: string) =>
    request<IntakeSubmitResult>('/api/v1/profile/intake/submit', {
      method: 'POST',
      body: JSON.stringify({ step, form, cv_text }),
    }),

  retryPipeline: () =>
    request<IntakeSubmitResult>('/api/v1/profile/intake/pipeline/retry', {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  deleteProfile: () =>
    request<{ ok: boolean }>('/api/v1/profile/intake', { method: 'DELETE' }),

  getStructuredProfile: () =>
    request<StructuredProfileResponse>('/api/v1/profile/intake/structured'),

  generateExtractionPrompt: (step: number, form: Partial<IntakeFormData>, cv_text: string) =>
    request<IntakePromptResult>('/api/v1/profile/intake/prompts/extraction', {
      method: 'POST',
      body: JSON.stringify({ step, form, cv_text }),
    }),

  validateExtraction: (data: Record<string, unknown>) =>
    request<IntakeValidateResult>('/api/v1/profile/intake/validate', {
      method: 'POST',
      body: JSON.stringify({ data }),
    }),

  confirmStructured: (data: Record<string, unknown>) =>
    request<{ ok: boolean; saved_to: string; confidence: string; fields_needing_review: string[] }>(
      '/api/v1/profile/intake/structured',
      { method: 'POST', body: JSON.stringify({ data }) },
    ),

  generateCompilePrompt: (data?: Record<string, unknown>) =>
    request<IntakePromptResult>('/api/v1/profile/intake/prompts/compile', {
      method: 'POST',
      body: JSON.stringify(data ? { data } : {}),
    }),
};
