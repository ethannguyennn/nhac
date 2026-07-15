import type { FingerprintProvider } from '@nhac/shared';

/** Normalized fingerprint result, independent of which provider produced it. */
export interface FingerprintMatch {
  matched: boolean;
  title?: string;
  artist?: string;
  album?: string;
  isrc?: string;
  artworkUrl?: string;
  confidence?: number; // 0–1, normalized
  externalIds?: Record<string, string>;
  /** Provider's raw payload, stored on the Recognition row for audit/debug. */
  raw: unknown;
}

/** Every provider adapter implements this. */
export interface FingerprintClient {
  readonly provider: FingerprintProvider;
  /** Identify a song from a local audio sample file. */
  identify(audioFilePath: string): Promise<FingerprintMatch>;
}
