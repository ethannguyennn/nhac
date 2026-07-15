/** Cross-cutting constants shared by API and clients. */

/** Object-storage key prefixes (folders) inside the media bucket. */
export const StoragePrefix = {
  RawVideo: 'raw',
  ExtractedAudio: 'audio',
  Transcoded: 'transcoded',
  Thumbnails: 'thumbnails',
  Exports: 'exports',
} as const;

/** Minimum fingerprint confidence (0–1) to auto-accept a match. */
export const MIN_MATCH_CONFIDENCE = 0.5;

/** Clips recorded within this many minutes are candidates for the same concert. */
export const CONCERT_GROUPING_WINDOW_MINUTES = 6 * 60;

/** Upload limits (MVP). Tune as storage costs allow. */
export const MAX_UPLOAD_BYTES = 500 * 1024 * 1024; // 500 MB per clip
export const ALLOWED_VIDEO_MIME = [
  'video/mp4',
  'video/quicktime',
  'video/webm',
] as const;

/** Sample-rate/duration we send to the fingerprinter (trimming saves cost + noise). */
export const FINGERPRINT_SAMPLE_SECONDS = 15;
export const FINGERPRINT_SAMPLE_START_SECONDS = 5;
