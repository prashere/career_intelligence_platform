import { getStoredToken } from '../auth/storage';

const API_BASE = import.meta.env.VITE_API_URL || '';

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

function parseErrorDetail(text: string): string {
  if (!text) return '';
  try {
    const json = JSON.parse(text) as { detail?: unknown };
    if (typeof json.detail === 'string') return json.detail;
    if (Array.isArray(json.detail)) return json.detail.map(String).join(', ');
  } catch {
    /* plain text */
  }
  return text;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, message: string) {
    const detail = parseErrorDetail(message);
    super(detail || message);
    this.status = status;
    this.detail = detail;
  }
}

function shouldNotifyUnauthorized(path: string, status: number): boolean {
  if (status !== 401) return false;
  return !path.includes('/auth/login') && !path.includes('/auth/register');
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    if (shouldNotifyUnauthorized(path, res.status)) onUnauthorized?.();
    throw new ApiError(res.status, text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
