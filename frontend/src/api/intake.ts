import type {
  IntakeDraft,
  IntakeFormData,
  IntakePromptResult,
  IntakeStatus,
  IntakeValidateResult,
} from '../types/intake';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
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

  saveDraft: (step: number, form: Partial<IntakeFormData>, cv_text?: string) =>
    request<IntakeDraft>('/api/v1/profile/intake/draft', {
      method: 'PUT',
      body: JSON.stringify({ step, form, cv_text }),
    }),

  saveCv: (cv_text: string) =>
    request<{ ok: boolean; length: number }>('/api/v1/profile/intake/cv', {
      method: 'PUT',
      body: JSON.stringify({ cv_text }),
    }),

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
