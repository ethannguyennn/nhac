import type { CreateUploadRequest, CreateUploadResponse } from '@nhac/shared';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:4000';

export async function createUpload(input: CreateUploadRequest): Promise<CreateUploadResponse> {
  const res = await fetch(`${API_BASE_URL}/clips/uploads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`Upload init failed: ${res.status}`);
  return res.json();
}

export async function putToStorage(uploadUrl: string, file: File): Promise<void> {
  const res = await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': file.type },
    body: file,
  });
  if (!res.ok) throw new Error(`Storage PUT failed: ${res.status}`);
}

export async function completeUpload(clipId: string): Promise<{ identified: boolean }> {
  const res = await fetch(`${API_BASE_URL}/clips/uploads/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clipId }),
  });
  if (!res.ok) throw new Error(`Complete failed: ${res.status}`);
  return res.json();
}
