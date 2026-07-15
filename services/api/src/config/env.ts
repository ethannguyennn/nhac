/**
 * Validated, typed environment. Fail fast at boot if config is missing.
 * Loads .env from the service dir first, then the repo root as a fallback.
 */
import { config as loadEnv } from 'dotenv';
import { z } from 'zod';
import { FingerprintProvider } from '@nhac/shared';

loadEnv(); // services/api/.env
loadEnv({ path: '../../.env' }); // repo root fallback (won't override already-set vars)

const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
  API_PORT: z.coerce.number().int().positive().default(4000),
  API_HOST: z.string().default('0.0.0.0'),
  API_CORS_ORIGINS: z.string().default('http://localhost:5173,http://localhost:8081'),

  SUPABASE_URL: z.string().url(),
  SUPABASE_SERVICE_ROLE_KEY: z.string().min(1),

  R2_ACCOUNT_ID: z.string().min(1),
  R2_ACCESS_KEY_ID: z.string().min(1),
  R2_SECRET_ACCESS_KEY: z.string().min(1),
  R2_BUCKET: z.string().min(1),
  R2_ENDPOINT: z.string().url(),
  R2_PUBLIC_BASE_URL: z.string().url().optional().or(z.literal('')),

  FINGERPRINT_PROVIDER: z
    .nativeEnum(FingerprintProvider)
    .default(FingerprintProvider.AudD),
  AUDD_API_TOKEN: z.string().optional().default(''),
  ACRCLOUD_HOST: z.string().optional().default(''),
  ACRCLOUD_ACCESS_KEY: z.string().optional().default(''),
  ACRCLOUD_ACCESS_SECRET: z.string().optional().default(''),
  ACOUSTID_API_KEY: z.string().optional().default(''),

  FFMPEG_PATH: z.string().optional().default(''),
});

const parsed = EnvSchema.safeParse(process.env);

if (!parsed.success) {
  // eslint-disable-next-line no-console
  console.error('❌ Invalid environment configuration:\n', z.treeifyError(parsed.error));
  throw new Error('Environment validation failed — see messages above.');
}

export const env = parsed.data;

export const corsOrigins = env.API_CORS_ORIGINS.split(',')
  .map((o) => o.trim())
  .filter(Boolean);
