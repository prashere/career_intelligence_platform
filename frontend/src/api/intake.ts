import type {
  IntakeDraft,
  IntakeFormData,
  IntakeStatus,
  IntakeSubmitResult,
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
      const detail = json.detail;
      if (typeof detail === 'object' && detail?.errors) {
        throw new Error(detail.errors.join('\n'));
      }
      throw new Error(typeof detail === 'string' ? detail : text);
    } catch (e) {
      if (e instanceof Error && e.message !== text) throw e;
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

  submit: (form: IntakeFormData, cv_text: string) =>
    request<IntakeSubmitResult>('/api/v1/profile/intake/submit', {
      method: 'POST',
      body: JSON.stringify({ form, cv_text }),
    }),

  uploadCvFile: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/v1/profile/intake/cv/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || 'Upload failed');
    }
    return res.json() as Promise<{ ok: boolean; text: string; length: number }>;
  },

  getSubmission: () =>
    request<Record<string, unknown>>('/api/v1/profile/intake/submission'),
};
