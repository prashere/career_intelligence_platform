import { api } from '../api/client';
import { getStoredToken } from '../auth/storage';

export async function downloadCalendarFile(opportunityId: string, title: string): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_URL || '';
  const token = getStoredToken();

  const res = await fetch(`${API_BASE}/api/v1/opportunities/${opportunityId}/calendar`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error('Could not download calendar file');
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  const safe = title.slice(0, 48).replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'deadline';
  anchor.download = `${safe}.ics`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export async function openGoogleCalendar(opportunityId: string): Promise<void> {
  const { google_url } = await api.calendarLinks(opportunityId);
  window.open(google_url, '_blank', 'noopener,noreferrer');
}
