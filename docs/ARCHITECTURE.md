# Architecture

## Goals & non-goals

**Goals:** cheap (free tiers), simple, fun MVP; ~90% song-detection with a
manual fallback; mobile-first. **Non-goals (now):** 100% accuracy, AI/LLM audio
models, Spotify integration, mass redistribution features, production hardening.

## System overview

```
┌─────────────┐         ┌─────────────┐
│  Mobile     │         │  Web        │
│  (Expo RN)  │         │  (Vite)     │
└──────┬──────┘         └──────┬──────┘
       │  1. POST /clips/uploads (metadata)      │
       │  3. POST /clips/uploads/complete        │
       └───────────────┬─────────────────────────┘
                       ▼
              ┌───────────────────┐        ┌──────────────────────┐
              │   API (Express)   │◀──────▶│  Supabase (Postgres) │
              │  services/api     │  meta  │  users, clips, songs │
              └───┬───────────┬───┘        │  playlists, RLS      │
     2. presign   │           │            └──────────────────────┘
        PUT URL   │           │ 4. process pipeline
                  ▼           ▼
         ┌────────────────┐  ┌──────────────────────────────┐
         │ Cloudflare R2  │  │  ffmpeg → fingerprint API     │
         │ raw video/     │  │  (AudD / ACRCloud / AcoustID) │
         │ audio/exports  │  └──────────────────────────────┘
         └────────────────┘
```

- **Clients never stream large files through the API.** They ask the API for a
  pre-signed R2 URL and `PUT` the video straight to object storage. The API
  handles only metadata + short audio samples.
- **The API owns the pipeline:** on upload-complete it extracts a short audio
  sample with ffmpeg, calls the fingerprint provider, upserts the `Song`, links
  the `Clip`, and groups it into a concert/playlist.

## Components

### `packages/shared`

Single source of truth for domain types, enums, constants, and API DTOs.
Imported by API, web, and mobile so the contract can't drift. Enum values are
mirrored by the SQL in `infra/supabase/migrations/0001_init.sql`.

### `services/api` (Node + Express + TypeScript)

| Area                         | File(s)                                   |
| ---------------------------- | ----------------------------------------- |
| Config (zod-validated env)   | `src/config/env.ts`                       |
| Storage (R2 presign)         | `src/lib/storage.ts`                      |
| DB (service-role client)     | `src/lib/supabase.ts`                     |
| Audio (ffmpeg wrapper)       | `src/lib/ffmpeg.ts`                       |
| Fingerprint providers        | `src/providers/fingerprint/*`             |
| Pipeline                     | `src/pipeline/processClip.ts`, `organize.ts` |
| Routes                       | `src/routes/*`                            |

Provider adapters implement a common `FingerprintClient` interface, so swapping
AudD → ACRCloud is a one-line registry change.

### `apps/mobile` (Expo Router)

File-based routes: `index` (library), `upload`, `concert/[id]`,
`player/[clipId]`. Talks to the API via the typed client in `src/lib/api.ts`.

### `apps/web` (Vite + React)

Minimal upload/playback companion sharing the same DTOs and pipeline.

### `infra/supabase`

Postgres schema + RLS. Auth via Supabase; a trigger auto-creates a `profiles`
row per user.

## Data model (summary)

`profiles · songs · concerts · concert_members · clips · recognitions ·
playlists · playlist_items · favorites · tags · clip_tags`

`clips` is the hub: it references a `song` (once identified) and a `concert`
(once grouped), and every fingerprint attempt is logged in `recognitions` for
debugging/audit. Full definitions in `packages/shared/src/models.ts` and the
migrations.

## Scaling the pipeline (later)

MVP runs `processClip` **inline** on the request (simple, fine at low volume).
When uploads outpace that:

1. `uploads/complete` enqueues a job and returns `202` immediately.
2. A worker (or Supabase Edge Function / queue consumer) runs ffmpeg +
   fingerprinting and writes results back.
3. Clients subscribe to clip status (Supabase Realtime) to update the UI.

ffmpeg needs a real runtime — a small always-on worker or a container, not a
thin serverless function without an ffmpeg layer.

## Security posture

- Service-role key stays server-side only.
- Clients use the anon key; RLS enforces per-user access (`0002_rls.sql`).
- Pre-signed URLs are short-lived and scoped to one object.
- Env is validated at boot; the app refuses to start misconfigured.
