# Setup

Get Nhạc running locally end-to-end.

## Prerequisites

| Tool                 | Notes                                            |
| -------------------- | ------------------------------------------------ |
| Node ≥ 20            | `node -v`                                        |
| npm ≥ 10             | ships with Node                                  |
| ffmpeg               | on PATH, or set `FFMPEG_PATH`; `ffmpeg -version` |
| Supabase project     | free tier — https://supabase.com                 |
| Cloudflare R2 bucket | S3-compatible — https://developers.cloudflare.com/r2 |
| Fingerprint API key  | AudD / ACRCloud / AcoustID (see DECISIONS)       |
| Expo Go (optional)   | to run the mobile app on a physical device       |

## 1. Install

```bash
npm install          # installs every workspace
npm run shared:build # compile @nhac/shared (other packages import its dist)
```

## 2. Environment files

Copy each template and fill in real values (never commit the `.env` copies):

```bash
cp .env.example .env                       # catalog of everything
cp services/api/.env.example services/api/.env
cp apps/web/.env.example apps/web/.env
cp apps/mobile/.env.example apps/mobile/.env
```

Keys quick-reference:

- **API** (`services/api/.env`): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
  all `R2_*`, `FINGERPRINT_PROVIDER` + provider key. **Server-only secrets.**
- **Web** (`apps/web/.env`): `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY`.
- **Mobile** (`apps/mobile/.env`): `EXPO_PUBLIC_API_BASE_URL` (use your machine's
  **LAN IP** for a physical device, not `localhost`), `EXPO_PUBLIC_SUPABASE_URL`,
  `EXPO_PUBLIC_SUPABASE_ANON_KEY`.

## 3. Supabase

1. Create a project; grab the URL, anon key, and service-role key.
2. Apply the schema — see [`infra/supabase/README.md`](../infra/supabase/README.md):
   ```bash
   supabase link --project-ref <ref>
   supabase db push
   ```
   (or paste `0001_init.sql` then `0002_rls.sql` into the SQL editor).
3. Enable Email auth. Optionally run `seed.sql` for demo mode.

## 4. Cloudflare R2

1. Create a bucket (e.g. `nhac-media`).
2. Create an R2 API token (access key + secret); note the account ID + S3
   endpoint. Fill the `R2_*` vars.
3. **CORS:** allow `PUT`/`GET` from your web + Expo origins so direct uploads
   work from the browser/device.

## 5. Run

```bash
npm run api:dev      # http://localhost:4000  (GET /health to check)
npm run web:dev      # http://localhost:5173
npm run mobile:start # Expo dev server → scan QR with Expo Go
```

## 6. Verify

```bash
curl http://localhost:4000/health
# → { "ok": true, "service": "nhac-api", ... }
```

Then upload a short concert clip from the web or mobile app and watch the API
logs move through extract → fingerprint → organize.

## Troubleshooting

- **API won't boot / env error:** `src/config/env.ts` validation printed the
  missing/invalid vars — fix `.env`.
- **`@nhac/shared` not found:** run `npm run shared:build` (and re-run after
  editing shared types).
- **Upload 403 to R2:** check the presigned URL hasn't expired and bucket CORS
  allows your origin + `PUT`.
- **ffmpeg errors:** confirm `ffmpeg -version`, or set `FFMPEG_PATH` to the
  binary.
- **Device can't reach API:** use your LAN IP in `EXPO_PUBLIC_API_BASE_URL`, and
  make sure phone + computer share a network.
