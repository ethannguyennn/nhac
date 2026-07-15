import { Router } from 'express';
import { asyncHandler, HttpError } from '../middleware/errors.js';

export const playlistsRouter: Router = Router();

// GET /playlists — caller's playlists (concert + greatest-hits + custom).
playlistsRouter.get(
  '/',
  asyncHandler(async (_req, res) => {
    res.json({ playlists: [] });
  }),
);

// GET /playlists/:id — playlist + ordered clips (PlaylistWithItems).
playlistsRouter.get(
  '/:id',
  asyncHandler(async (req, res) => {
    throw new HttpError(501, 'not_implemented', `GET /playlists/${req.params.id} not implemented`);
  }),
);
