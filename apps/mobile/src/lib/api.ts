/**
 * Typed API client. Uses the shared DTOs so the app can't drift from the
 * server contract. Auth token wiring (Supabase session JWT) is a TODO.
 */
import type {
  CompleteUploadRequest,
  CreateUploadRequest,
  CreateUploadResponse,
  TagClipRequest,
} from '@nhac/shared';
import { API_BASE_URL } from './config';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      // TODO: Authorization: `Bearer ${supabaseSession.access_token}`
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createUpload(input: CreateUploadRequest): Promise<CreateUploadResponse> {
    return request('/clips/uploads', { method: 'POST', body: JSON.stringify(input) });
  },

  /** Upload the raw file straight to R2 via the pre-signed URL (no API relay). */
  async uploadToStorage(uploadUrl: string, fileUri: string, mimeType: string): Promise<void> {
    const blob = await (await fetch(fileUri)).blob();
    const res = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': mimeType },
      body: blob,
    });
    if (!res.ok) throw new Error(`Storage upload failed: ${res.status}`);
  },

  completeUpload(input: CompleteUploadRequest): Promise<{ identified: boolean }> {
    return request('/clips/uploads/complete', { method: 'POST', body: JSON.stringify(input) });
  },

  tagClip(clipId: string, input: Omit<TagClipRequest, 'clipId'>): Promise<unknown> {
    return request(`/clips/${clipId}/tag`, { method: 'POST', body: JSON.stringify(input) });
  },

  listConcerts(): Promise<{ concerts: unknown[] }> {
    return request('/concerts');
  },
};
