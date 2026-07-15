/**
 * Canonical status/enum values shared across the DB, API, and clients.
 * Keep these in sync with the CHECK constraints in
 * infra/supabase/migrations/0001_init.sql.
 */

/** Lifecycle of an uploaded clip as it moves through the pipeline. */
export const ClipStatus = {
  /** Row created, waiting for the raw file to finish uploading to object storage. */
  Uploading: 'uploading',
  /** File in storage, queued for audio extraction + fingerprinting. */
  Processing: 'processing',
  /** Fingerprinting ran and returned a confident match. */
  Identified: 'identified',
  /** Fingerprinting ran but found nothing / low confidence — needs manual tag. */
  Unidentified: 'unidentified',
  /** User manually supplied the song. */
  ManuallyTagged: 'manually_tagged',
  /** Something failed (extraction/transcode/provider error). */
  Failed: 'failed',
} as const;
export type ClipStatus = (typeof ClipStatus)[keyof typeof ClipStatus];

/** How a clip's song was determined. */
export const MatchSource = {
  Fingerprint: 'fingerprint',
  Manual: 'manual',
  /** Copied from another clip in the same concert/song group. */
  Inherited: 'inherited',
} as const;
export type MatchSource = (typeof MatchSource)[keyof typeof MatchSource];

/** Fingerprinting providers we support. See docs/DECISIONS.md. */
export const FingerprintProvider = {
  AudD: 'audd',
  ACRCloud: 'acrcloud',
  AcoustID: 'acoustid',
} as const;
export type FingerprintProvider = (typeof FingerprintProvider)[keyof typeof FingerprintProvider];

/** Role of a user within a (potentially collaborative) concert. */
export const ConcertRole = {
  Owner: 'owner',
  Contributor: 'contributor',
  Viewer: 'viewer',
} as const;
export type ConcertRole = (typeof ConcertRole)[keyof typeof ConcertRole];

/** Kinds of playlist Nhạc generates or the user creates. */
export const PlaylistType = {
  /** Auto-generated: all clips from one concert. */
  Concert: 'concert',
  /** Auto-generated: greatest hits / favorites across concerts. */
  GreatestHits: 'greatest_hits',
  /** User-curated custom playlist. */
  Custom: 'custom',
} as const;
export type PlaylistType = (typeof PlaylistType)[keyof typeof PlaylistType];
