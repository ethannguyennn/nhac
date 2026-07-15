/**
 * Fingerprint provider registry. Selects the adapter based on
 * FINGERPRINT_PROVIDER so the rest of the app stays provider-agnostic.
 */
import { FingerprintProvider } from '@nhac/shared';
import { env } from '../../config/env.js';
import { auddClient } from './audd.js';
import type { FingerprintClient } from './types.js';

// ACRCloud + AcoustID adapters are Phase-1 stretch / Phase-2. Add here when built.
const registry: Partial<Record<FingerprintProvider, FingerprintClient>> = {
  [FingerprintProvider.AudD]: auddClient,
};

export function getFingerprintClient(): FingerprintClient {
  const client = registry[env.FINGERPRINT_PROVIDER];
  if (!client) {
    throw new Error(
      `Fingerprint provider "${env.FINGERPRINT_PROVIDER}" has no adapter yet. ` +
        `Available: ${Object.keys(registry).join(', ')}`,
    );
  }
  return client;
}

export type { FingerprintClient, FingerprintMatch } from './types.js';
