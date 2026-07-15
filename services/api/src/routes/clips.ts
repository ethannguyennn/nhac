/**
 * Clip routes — the heart of the MVP upload/identify flow.
 *
 *   POST /clips/uploads          → CreateUploadResponse (presigned R2 URL)
 *   POST /clips/uploads/complete → kick off processClip()
 *   POST /clips/:id/tag          → manual song fallback
 *   GET  /clips/:id              → clip + resolved song + playback URL
 *
 * Handlers are wired to the pipeline but leave DB writes as TODOs so the
 * scaffold compiles without a live Supabase/R2 connection.
 */
import { randomUUID } from 'node:crypto';
import { Router } from 'express';
import {
  ALLOWED_VIDEO_MIME,
  MAX_UPLOAD_BYTES,
  StoragePrefix,
  type CreateUploadResponse,
} from '@nhac/shared';
import { z } from 'zod';
import { createPresignedUpload } from '../lib/storage.js';
import { processClip } from '../pipeline/processClip.js';
import { asyncHandler, HttpError } from '../middleware/errors.js';

export const clipsRouter: Router = Router();

const createUploadSchema = z.object({
  fileName: z.string().min(1),
  mimeType: z.enum(ALLOWED_VIDEO_MIME),
  sizeBytes: z.number().int().positive().max(MAX_UPLOAD_BYTES),
  durationSeconds: z.number().positive().optional(),
  recordedAt: z.string().datetime().optional(),
});

clipsRouter.post(
  '/uploads',
  asyncHandler(async (req, res) => {
    const input = createUploadSchema.parse(req.body);
    const clipId = randomUUID();
    const ext = input.fileName.split('.').pop() ?? 'mp4';
    const storageKey = `${StoragePrefix.RawVideo}/${clipId}.${ext}`;

    const uploadUrl = await createPresignedUpload(storageKey, input.mimeType);

    // TODO: insert Clip row (status = uploading, uploaderId from auth, storageKey, metadata).

    const body: CreateUploadResponse = {
      clipId,
      uploadUrl,
      storageKey,
      expiresInSeconds: 900,
    };
    res.status(201).json(body);
  }),
);

const completeSchema = z.object({ clipId: z.string().uuid() });

clipsRouter.post(
  '/uploads/complete',
  asyncHandler(async (req, res) => {
    const { clipId } = completeSchema.parse(req.body);
    // TODO: verify the object exists in R2 and belongs to the caller.
    // MVP: run inline. Later: enqueue and return 202 immediately.
    const result = await processClip(clipId);
    res.status(202).json(result);
  }),
);

const tagSchema = z.object({
  artist: z.string().min(1),
  title: z.string().min(1),
  album: z.string().optional(),
});

clipsRouter.post(
  '/:id/tag',
  asyncHandler(async (req, res) => {
    const clipId = z.string().uuid().parse(req.params.id);
    const input = tagSchema.parse(req.body);
    // TODO: upsert Song(input), link clip with MatchSource.Manual, status = manually_tagged,
    //       then autoGroupIntoConcert(clipId).
    res.json({ clipId, ...input, status: 'manually_tagged' });
  }),
);

clipsRouter.get(
  '/:id',
  asyncHandler(async (req, res) => {
    const clipId = z.string().uuid().parse(req.params.id);
    // TODO: load ClipWithSong + presigned playback URL.
    throw new HttpError(501, 'not_implemented', `GET /clips/${clipId} not implemented yet`);
  }),
);
