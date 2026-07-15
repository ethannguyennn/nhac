/**
 * The core processing pipeline for a single uploaded clip.
 *
 *   raw video in R2
 *      → download to tmp
 *      → ffmpeg: extract short audio sample
 *      → fingerprint provider: identify song
 *      → upsert Song, link Clip, write Recognition row
 *      → set status = identified | unidentified
 *
 * MVP runs this inline after upload completes. As volume grows, move it behind
 * a queue/worker (see docs/ARCHITECTURE.md → "Scaling the pipeline").
 *
 * This is intentionally a well-commented SKELETON — each step is wired but
 * marked TODO where real glue (tmp file handling, Song upsert) goes.
 */
import { MatchSource, MIN_MATCH_CONFIDENCE } from '@nhac/shared';
import { logger } from '../lib/logger.js';
import { getFingerprintClient } from '../providers/fingerprint/index.js';

export interface ProcessClipResult {
  clipId: string;
  identified: boolean;
  songId?: string;
  confidence?: number;
}

export async function processClip(clipId: string): Promise<ProcessClipResult> {
  const log = logger.child({ clipId });
  log.info('processClip: start');

  // 1. Load clip row, mark status = processing.
  // TODO: const clip = await getClipOrThrow(clipId); await setStatus(clipId, ClipStatus.Processing);

  // 2. Get a readable URL for the raw video and download to a tmp file.
  // TODO: const url = await createPresignedDownload(clip.rawVideoKey);
  //       const localVideo = await downloadToTmp(url);

  // 3. Extract a short audio sample with ffmpeg.
  // TODO: const localAudio = await extractAudioSample(localVideo, tmpAudioPath);

  // 4. Fingerprint it.
  const client = getFingerprintClient();
  log.info({ provider: client.provider }, 'processClip: fingerprinting');
  // TODO: const match = await client.identify(localAudio);
  const match = { matched: false, confidence: 0, raw: null } as Awaited<
    ReturnType<typeof client.identify>
  >;

  // 5. Persist recognition + decide outcome.
  const confident = match.matched && (match.confidence ?? 0) >= MIN_MATCH_CONFIDENCE;
  if (confident) {
    // TODO: const songId = await upsertSong(match);
    //       await linkClipToSong(clipId, songId, MatchSource.Fingerprint, match.confidence);
    //       await setStatus(clipId, ClipStatus.Identified);
    //       await autoGroupIntoConcert(clipId); // see organize.ts
    log.info({ source: MatchSource.Fingerprint }, 'processClip: identified');
    return { clipId, identified: true, confidence: match.confidence };
  }

  // TODO: await writeRecognition(clipId, client.provider, match);
  //       await setStatus(clipId, ClipStatus.Unidentified); // client prompts for manual tag
  log.warn('processClip: no confident match — awaiting manual tag');
  return { clipId, identified: false };
}
