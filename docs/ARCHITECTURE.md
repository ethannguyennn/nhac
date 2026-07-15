# Architecture

## Goals & non-goals

**Goals:** cheap (runs free/local), simple, a fun working MVP; ~90% song
detection with a manual fallback; mobile-first. **Non-goals (now):** 100%
accuracy, AI/LLM audio models, Spotify integration, mass redistribution,
production hardening.

## System overview

```
                         ┌─────────────────────────────┐
  Browser / phone  ─────▶│         FastAPI app         │
  (Jinja2 pages +        │          nhac.main          │
   JSON API)             ├─────────────┬───────────────┤
                         │  routers/web │  routers/api  │
                         └──────┬───────┴───────┬───────┘
                                │ uploads.ingest │
                                ▼                ▼
                    ┌───────────────────┐  ┌──────────────────┐
                    │  pipeline/        │  │  services/       │
                    │  process_clip     │  │  clips, songs,   │
                    │  organize         │  │  concerts, ...   │
                    └───┬───────────┬───┘  └────────┬─────────┘
          ffmpeg extract│           │fingerprint    │ SQLAlchemy
                        ▼           ▼               ▼
                 ┌────────────┐ ┌──────────────┐ ┌──────────────┐
                 │  audio/    │ │ fingerprint/ │ │  Database    │
                 │  ffmpeg    │ │ mock|audd|.. │ │  SQLite/PG   │
                 └────────────┘ └──────────────┘ └──────────────┘
                        │
                        ▼
                 ┌────────────┐
                 │  storage/  │  local disk  (→ R2/S3)
                 └────────────┘
```

## Request → pipeline flow

1. **Upload** (`routers/web.py` or `routers/api.py`) receives a multipart video.
2. **`uploads.ingest_upload`** validates it, stores the raw bytes via the
   storage backend, creates a `Clip` row, then runs the pipeline in a threadpool
   (`run_in_threadpool`) so ffmpeg/network don't block the event loop.
3. **`pipeline/process_clip`** (its own DB session): probe → thumbnail → extract
   audio sample → fingerprint → log `Recognition` → upsert `Song` + link `Clip`
   → `organize`.
4. **`pipeline/organize`** groups the clip into a `Concert` (by artist + date)
   and its auto `Playlist`.
5. The route redirects (web) or returns the clip + result (API).

## Modules

| Module                | Responsibility                                             |
| --------------------- | ---------------------------------------------------------- |
| `config.py`           | Typed settings (pydantic-settings), validated at startup   |
| `db.py` / `models.py` | Engine/session + SQLAlchemy ORM (the persistent domain)    |
| `schemas.py`          | Pydantic request/response contracts                        |
| `storage/`            | `Storage` protocol + `local` and `s3` backends             |
| `audio/ffmpeg.py`     | probe, extract audio sample, thumbnail, quality estimate   |
| `fingerprint/`        | `Fingerprinter` ABC + `mock`/`audd`/`acoustid` + registry  |
| `pipeline/`           | `process_clip` (orchestration) + `organize` (grouping)     |
| `services/`           | Focused DB logic: clips, songs, concerts, playlists, users |
| `routers/`            | `api` (JSON under `/api`) and `web` (HTML pages)            |
| `uploads.py`          | Shared upload orchestration for web + API                  |
| `templating.py`       | Jinja2 env + helpers (`media_url`)                          |

Every seam is a swap point: `Storage`, `Fingerprinter`, and the DB URL are all
chosen by config, so local→cloud and mock→real are config changes, not rewrites.

## Data model

`users · songs · concerts · concert_members · clips · recognitions ·
playlists · playlist_items · favorites`

`clips` is the hub: it points at a `song` (once identified) and a `concert`
(once grouped); each fingerprint attempt is recorded in `recognitions` for
audit/debug. Enum values live in `nhac/enums.py`.

## Concurrency & the pipeline

MVP processes each upload **inline** (in a threadpool) and returns when done —
simple, fine at low volume. Scale path when uploads outpace that:

1. `ingest_upload` enqueues a job and returns immediately (202 + "processing").
2. A worker process runs the pipeline and writes results back.
3. The UI polls clip status (or subscribes) to update.

ffmpeg needs a real runtime — a small worker/container, not a thin serverless
function without an ffmpeg build.

## Auth (MVP)

Single seeded local user (`services/users.get_or_create_default_user`), injected
via the `get_current_user` dependency. Swapping in real session/JWT auth touches
only that dependency — routers are unaffected. See [NOTES.md](NOTES.md).

## Security notes

- Config validated at boot; storage keys are path-traversal-guarded (`storage/local.py`).
- Upload type/size limits in `constants.py`, enforced in `uploads.py`.
- The `s3` backend can hand out short-lived presigned URLs instead of public ones.
- Secrets come from env/`.env` (gitignored); only `.env.example` is committed.
