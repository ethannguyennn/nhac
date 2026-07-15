/**
 * Thin ffmpeg wrapper for audio extraction + quality analysis.
 *
 * MVP strategy: extract a short mono audio sample (see FINGERPRINT_SAMPLE_*
 * constants) rather than the full track — cheaper for the fingerprint API and
 * usually enough for a match. Phase 2 adds loudness/SNR analysis for the
 * cleanest-audio ranking.
 *
 * NOTE: these run ffmpeg as a child process. In a serverless deployment you
 * either need an ffmpeg layer or a dedicated worker (see docs/ARCHITECTURE.md).
 */
import { spawn } from 'node:child_process';
import {
  FINGERPRINT_SAMPLE_SECONDS,
  FINGERPRINT_SAMPLE_START_SECONDS,
} from '@nhac/shared';
import { env } from '../config/env.js';
import { logger } from './logger.js';

const FFMPEG_BIN = env.FFMPEG_PATH || 'ffmpeg';

function run(args: string[]): Promise<{ code: number; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = spawn(FFMPEG_BIN, args);
    let stderr = '';
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('error', reject);
    proc.on('close', (code) => resolve({ code: code ?? -1, stderr }));
  });
}

/**
 * Extract a short mono MP3 sample from a local video file for fingerprinting.
 * @returns path to the extracted audio file
 */
export async function extractAudioSample(inputPath: string, outputPath: string): Promise<string> {
  const args = [
    '-ss',
    String(FINGERPRINT_SAMPLE_START_SECONDS),
    '-t',
    String(FINGERPRINT_SAMPLE_SECONDS),
    '-i',
    inputPath,
    '-vn', // no video
    '-ac',
    '1', // mono
    '-ar',
    '44100',
    '-y',
    outputPath,
  ];
  const { code, stderr } = await run(args);
  if (code !== 0) {
    logger.error({ stderr }, 'ffmpeg audio extraction failed');
    throw new Error(`ffmpeg exited ${code}`);
  }
  return outputPath;
}

/**
 * Phase 2: estimate audio "cleanliness" for cleanest-clip selection.
 * TODO: parse `volumedetect` (mean/max volume) and a high-frequency energy
 * proxy for crowd noise, then combine into a single score. Higher = cleaner.
 * See docs/WORKFLOWS.md → "Cleanest-audio selection".
 */
export async function estimateAudioQuality(_inputPath: string): Promise<number> {
  throw new Error('estimateAudioQuality not implemented — Phase 2');
}
