import { useState } from 'react';
import { completeUpload, createUpload, putToStorage } from './lib/api';

/**
 * Minimal web companion: drag/pick a concert video and push it through the
 * same upload pipeline the mobile app uses. Playback grid is a TODO.
 */
export function App() {
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      setStatus('Requesting upload URL…');
      const { clipId, uploadUrl } = await createUpload({
        fileName: file.name,
        mimeType: file.type as never,
        sizeBytes: file.size,
      });
      setStatus('Uploading…');
      await putToStorage(uploadUrl, file);
      setStatus('Identifying the song…');
      const { identified } = await completeUpload(clipId);
      setStatus(identified ? 'Identified! 🎶' : 'No match — tag it manually.');
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 640, margin: '0 auto', padding: 32 }}>
      <h1 style={{ fontSize: 40, margin: 0 }}>Nhạc</h1>
      <p style={{ color: 'var(--muted)', marginTop: 4 }}>Relive the moment.</p>

      <label
        style={{
          display: 'block',
          marginTop: 32,
          padding: 40,
          border: '1px dashed var(--border)',
          borderRadius: 16,
          background: 'var(--surface)',
          textAlign: 'center',
          cursor: busy ? 'default' : 'pointer',
        }}
      >
        <input type="file" accept="video/*" hidden disabled={busy} onChange={onFile} />
        <span>{busy ? 'Working…' : 'Click to choose a concert video'}</span>
      </label>

      {status && <p style={{ marginTop: 16 }}>{status}</p>}

      <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 48 }}>
        For personal use. You’re responsible for the footage you upload and share.
      </p>
    </main>
  );
}
