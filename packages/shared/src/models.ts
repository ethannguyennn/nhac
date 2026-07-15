/**
 * Core domain models for Nhạc.
 *
 * These mirror the Postgres tables in
 * infra/supabase/migrations/0001_init.sql. Timestamps are ISO-8601 strings
 * as returned by the API/PostgREST.
 */
import type {
  ClipStatus,
  ConcertRole,
  FingerprintProvider,
  MatchSource,
  PlaylistType,
} from './enums.js';

export type UUID = string;
export type ISODateString = string;

/** Public profile linked 1:1 to a Supabase auth user. */
export interface Profile {
  id: UUID; // == auth.users.id
  username: string | null;
  displayName: string | null;
  avatarUrl: string | null;
  createdAt: ISODateString;
}

/** A show a user attended. May be collaborative (multiple members). */
export interface Concert {
  id: UUID;
  ownerId: UUID;
  title: string; // e.g. "Beabadoobee — Fonda Theatre"
  artist: string | null;
  venue: string | null;
  city: string | null;
  performedOn: ISODateString | null; // date of the show
  coverImageUrl: string | null;
  isDemo: boolean; // seeded sample data for cold-start
  createdAt: ISODateString;
  updatedAt: ISODateString;
}

/** Membership row for collaborative concerts (Phase 2). */
export interface ConcertMember {
  concertId: UUID;
  userId: UUID;
  role: ConcertRole;
  invitedBy: UUID | null;
  createdAt: ISODateString;
}

/** A canonical song, deduped across clips/concerts. */
export interface Song {
  id: UUID;
  title: string;
  artist: string;
  album: string | null;
  artworkUrl: string | null;
  isrc: string | null; // international standard recording code, when known
  externalIds: Record<string, string>; // { audd: '...', musicbrainz: '...' }
  createdAt: ISODateString;
}

/** One uploaded video clip. The central entity of the app. */
export interface Clip {
  id: UUID;
  concertId: UUID | null; // null until grouped
  uploaderId: UUID;
  status: ClipStatus;

  // Storage (Cloudflare R2 keys, not public URLs — resolve via API)
  rawVideoKey: string | null;
  audioKey: string | null;
  transcodedKey: string | null;
  thumbnailKey: string | null;

  // Media metadata
  durationSeconds: number | null;
  recordedAt: ISODateString | null; // from video metadata if available
  width: number | null;
  height: number | null;
  sizeBytes: number | null;

  // Song match
  songId: UUID | null;
  matchSource: MatchSource | null;
  matchConfidence: number | null; // 0–1
  /** Free-text fallback if the user typed a song we couldn't resolve to a Song row. */
  manualArtist: string | null;
  manualTitle: string | null;

  // Phase 2 — cleanest-audio ranking
  audioQualityScore: number | null; // higher = cleaner (see WORKFLOWS.md)

  createdAt: ISODateString;
  updatedAt: ISODateString;
}

/** Raw + parsed result of a fingerprinting attempt against a clip. */
export interface Recognition {
  id: UUID;
  clipId: UUID;
  provider: FingerprintProvider;
  matchedSongId: UUID | null;
  confidence: number | null;
  rawResponse: unknown; // JSONB — provider payload for debugging/audit
  createdAt: ISODateString;
}

export interface Playlist {
  id: UUID;
  ownerId: UUID;
  concertId: UUID | null; // set for type === 'concert'
  type: PlaylistType;
  title: string;
  description: string | null;
  createdAt: ISODateString;
  updatedAt: ISODateString;
}

export interface PlaylistItem {
  id: UUID;
  playlistId: UUID;
  clipId: UUID;
  position: number;
  createdAt: ISODateString;
}

/** A user's rating/favorite of a clip. */
export interface Favorite {
  userId: UUID;
  clipId: UUID;
  stars: number; // 1–5; presence also means "favorited"
  createdAt: ISODateString;
}

export interface Tag {
  id: UUID;
  label: string;
}
