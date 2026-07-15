import { env } from './config/env.js';
import { logger } from './lib/logger.js';
import { createServer } from './server.js';

const app = createServer();

const server = app.listen(env.API_PORT, env.API_HOST, () => {
  logger.info(`🎵 nhac-api listening on http://${env.API_HOST}:${env.API_PORT}`);
});

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => {
    logger.info({ signal }, 'shutting down');
    server.close(() => process.exit(0));
  });
}
