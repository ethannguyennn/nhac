/**
 * API request/response shapes (DTOs) shared between server and clients.
 * Keeping these here means the mobile/web apps get compile-time safety
 * against the API contract.
 */
import type { Clip, Concert, Playlist, Song } from './models.js';

/** Step 1 of upload: client asks the API where to put the file. */
export interface CreateUploadRequest {
  fileName: string;
  mimeType: string;
  sizeBytes: number;
  durationSeconds?: number;
  recordedAt?: string;
}

/** API returns a pre-signed URL the client PUTs the raw video to directly. */
export interface CreateUploadResponse {
  clipId: string;
  uploadUrl: string; // pre-signed R2 PUT URL
  storageKey: string;
  expiresInSeconds: number;
}

/** Step 2: client tells the API the upload finished; API kicks off processing. */
export interface CompleteUploadRequest {
  clipId: string;
}

/** Manual tagging fallback when fingerprinting misses. */
export interface TagClipRequest {
  clipId: string;
  artist: string;
  title: string;
  album?: string;
}

export interface ClipWithSong extends Clip {
  song: Song | null;
}

export interface ConcertWithClips extends Concert {
  clips: ClipWithSong[];
}

export interface PlaylistWithItems extends Playlist {
  items: ClipWithSong[];
}

/** Standard error envelope returned by the API. */
export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
