/**
 * AudD adapter (https://docs.audd.io).
 * Chosen as the MVP default: dead-simple REST, returns Apple Music / Spotify
 * metadata + artwork. Verify current free-trial limits before launch
 * (see docs/DECISIONS.md).
 */
import { readFile } from 'node:fs/promises';
import { basename } from 'node:path';
import { FingerprintProvider } from '@nhac/shared';
import { env } from '../../config/env.js';
import type { FingerprintClient, FingerprintMatch } from './types.js';

const AUDD_ENDPOINT = 'https://api.audd.io/';

export const auddClient: FingerprintClient = {
  provider: FingerprintProvider.AudD,

  async identify(audioFilePath: string): Promise<FingerprintMatch> {
    if (!env.AUDD_API_TOKEN) {
      throw new Error('AUDD_API_TOKEN is not set');
    }

    const fileBuffer = await readFile(audioFilePath);
    const form = new FormData();
    form.append('api_token', env.AUDD_API_TOKEN);
    form.append('return', 'apple_music,spotify');
    form.append('file', new Blob([new Uint8Array(fileBuffer)]), basename(audioFilePath));

    const res = await fetch(AUDD_ENDPOINT, { method: 'POST', body: form });
    const json = (await res.json()) as AuddResponse;

    if (json.status !== 'success' || !json.result) {
      return { matched: false, raw: json };
    }

    const r = json.result;
    return {
      matched: true,
      title: r.title,
      artist: r.artist,
      album: r.album,
      isrc: r.isrc ?? undefined,
      artworkUrl: r.apple_music?.artwork?.url?.replace('{w}x{h}', '600x600'),
      // AudD does not return a numeric confidence; treat a hit as reasonably confident.
      confidence: 0.8,
      externalIds: {
        ...(r.spotify?.id ? { spotify: r.spotify.id } : {}),
        ...(r.apple_music?.id ? { apple_music: r.apple_music.id } : {}),
      },
      raw: json,
    };
  },
};

// Minimal shape of the AudD response we rely on.
interface AuddResponse {
  status: 'success' | 'error';
  result?: {
    title: string;
    artist: string;
    album?: string;
    isrc?: string | null;
    spotify?: { id?: string };
    apple_music?: { id?: string; artwork?: { url?: string } };
  } | null;
}
