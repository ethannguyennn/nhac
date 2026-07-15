import cors from 'cors';
import express, { type Express } from 'express';
import { pinoHttp } from 'pino-http';
import { corsOrigins } from './config/env.js';
import { logger } from './lib/logger.js';
import { errorHandler, notFound } from './middleware/errors.js';
import { clipsRouter } from './routes/clips.js';
import { concertsRouter } from './routes/concerts.js';
import { healthRouter } from './routes/health.js';
import { playlistsRouter } from './routes/playlists.js';

export function createServer(): Express {
  const app = express();

  app.use(pinoHttp({ logger }));
  app.use(cors({ origin: corsOrigins }));
  app.use(express.json({ limit: '1mb' }));

  app.use(healthRouter);
  app.use('/clips', clipsRouter);
  app.use('/concerts', concertsRouter);
  app.use('/playlists', playlistsRouter);

  app.use(notFound);
  app.use(errorHandler);

  return app;
}
