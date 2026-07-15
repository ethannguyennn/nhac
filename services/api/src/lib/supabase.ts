/**
 * Server-side Supabase client using the service-role key.
 * This BYPASSES row-level security — only use it in trusted server code,
 * never expose the key or this client to the browser/mobile app.
 */
import { createClient } from '@supabase/supabase-js';
import { env } from '../config/env.js';

export const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});
