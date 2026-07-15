import { Router } from 'express';
import { asyncHandler, HttpError } from '../middleware/errors.js';

export const concertsRouter: Router = Router();

// GET /concerts — list caller's concerts (+ demo concerts for cold-start).
concertsRouter.get(
  '/',
  asyncHandler(async (_req, res) => {
    // TODO: select concerts where owner = caller OR is_demo = true, newest first.
    res.json({ concerts: [] });
  }),
);

// GET /concerts/:id — concert + grouped clips (ConcertWithClips).
concertsRouter.get(
  '/:id',
  asyncHandler(async (req, res) => {
    throw new HttpError(501, 'not_implemented', `GET /concerts/${req.params.id} not implemented`);
  }),
);
