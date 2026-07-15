import type { NextFunction, Request, Response } from 'express';
import type { ApiError } from '@nhac/shared';
import { logger } from '../lib/logger.js';

/** Throw this from handlers for controlled error responses. */
export class HttpError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export function notFound(_req: Request, res: Response): void {
  const body: ApiError = { error: { code: 'not_found', message: 'Route not found' } };
  res.status(404).json(body);
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function errorHandler(err: unknown, _req: Request, res: Response, _next: NextFunction): void {
  if (err instanceof HttpError) {
    const body: ApiError = { error: { code: err.code, message: err.message, details: err.details } };
    res.status(err.status).json(body);
    return;
  }
  logger.error({ err }, 'Unhandled error');
  const body: ApiError = { error: { code: 'internal_error', message: 'Something went wrong' } };
  res.status(500).json(body);
}

/** Wrap async handlers so rejections reach the error middleware. */
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<unknown>,
) {
  return (req: Request, res: Response, next: NextFunction): void => {
    fn(req, res, next).catch(next);
  };
}
