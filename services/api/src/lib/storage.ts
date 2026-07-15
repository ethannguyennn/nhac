/**
 * Cloudflare R2 (S3-compatible) object storage.
 * We hand out pre-signed PUT URLs so clients upload raw video DIRECTLY to R2,
 * keeping large files off the API server. The API only ever touches metadata
 * and short audio samples.
 */
import { GetObjectCommand, PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { env } from '../config/env.js';

export const r2 = new S3Client({
  region: 'auto',
  endpoint: env.R2_ENDPOINT,
  credentials: {
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  },
});

/** Pre-signed URL the client uses to PUT a raw upload straight to R2. */
export async function createPresignedUpload(
  key: string,
  contentType: string,
  expiresInSeconds = 900,
): Promise<string> {
  const command = new PutObjectCommand({
    Bucket: env.R2_BUCKET,
    Key: key,
    ContentType: contentType,
  });
  return getSignedUrl(r2, command, { expiresIn: expiresInSeconds });
}

/** Pre-signed URL for reading a private object (playback, processing). */
export async function createPresignedDownload(
  key: string,
  expiresInSeconds = 3600,
): Promise<string> {
  const command = new GetObjectCommand({ Bucket: env.R2_BUCKET, Key: key });
  return getSignedUrl(r2, command, { expiresIn: expiresInSeconds });
}

/** Public URL when a custom R2 domain is configured; else null (use presigned). */
export function publicUrl(key: string): string | null {
  return env.R2_PUBLIC_BASE_URL ? `${env.R2_PUBLIC_BASE_URL.replace(/\/$/, '')}/${key}` : null;
}
