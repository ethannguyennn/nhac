# CLAUDE.md

Guidance for Claude (or any agent) working in this repository.

## What this is

Nhạc — a concert-memory video app. Users upload their own concert clips; the
app extracts audio, identifies the song (fingerprinting, not AI), auto-groups
clips into per-concert playlists, and plays them back in a "theater mode" with
shuffle-by-default autoplay, an excitement-detection engine (flashing lights +
crowd loudness), and an on-demand "hype cut" montage of each clip's best
moments.

Full narrative docs live in `docs/` — read `docs/ARCHITECTURE.md` and
`docs/WORKFLOWS.md` before making non-trivial changes. This file is the
fast-orientation cheat sheet, not a replacement for those.

## CRITICAL: never commit or push

**Do not run `git commit`, `git push`, or any other write git command in this
repo unless explicitly asked in that exact conversation turn.** The owner
commits and pushes himself. Finish the work, verify it (tests/lint/live
check), report status, and leave the working tree as-is. If asked to commit,
do not add a Claude/AI co-author trailer to the message.

## Stack

Python only — no JS/TS build step, no frontend framework.

- **FastAPI** (+ Uvicorn) — JSON API under `/api` and server-rendered pages
- **Jinja2** templates + **vanilla JS** (`nhac/static/js/*.js`) + plain CSS
- **SQLAlchemy 2.0** ORM — SQLite by default (`NHAC_DATABASE_URL` swaps to Postgres)
- **ffmpeg / ffprobe** — audio extraction, thumbnails, excitement analysis,
  montage rendering (hard dependency, must be on PATH or set via
  `NHAC_FFMPEG_PATH`/`NHAC_FFPROBE_PATH`)
- **pytest** + **ruff**

## Quick start

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # if not already installed
.venv\Scripts\python.exe scripts\seed_demo.py                     # optional demo data
.venv\Scripts\python.exe run.py                                   # http://127.0.0.1:8000
```

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check nhac scripts tests
```

Always invoke `.venv\Scripts\python.exe` / `.venv\Scripts\ruff.exe` explicitly
— there's no global install, and a fresh session has no active venv.

## Architecture in one picture

```
upload → uploads.ingest_upload → pipeline.process_clip (own DB session, runs in a threadpool)
    1. ffmpeg.probe                 → duration/width/height
    2. ffmpeg.extract_thumbnail     → thumbnails/<id>.jpg
    3. ffmpeg.extract_audio_sample  → audio/<id>.mp3 (short sample, not the whole track)
    4. ffmpeg.estimate_audio_quality (best-effort)
    4.5 analysis.excitement.analyze_and_store → clip_highlights rows
    5. fingerprint.identify(sample)  [mock | audd | acoustid, via NHAC_FINGERPRINT_PROVIDER]
    6. write Recognition row
    7. confident? → upsert Song, link Clip, organize.auto_group_into_concert
              : → status=unidentified, user manually tags via /clips/<id>/tag
```

Theater mode (`/play/<playlist_id>`): `services/playback.build_queue` resolves
a playlist into a JSON queue (media/montage/thumbnail URLs + highlight
segments), embedded into `play.html`, driven client-side by
`static/js/player.js` (`NhacPlayer`) — shuffle-by-default autoplay,
auto-hiding controls, hype-cut toggle, progress-bar highlight tick marks,
buffering indicator.

Hype cut (`pipeline/montage.py`): trims+concats a clip's highlight segments
(hard cuts) and muxes them under the clip's ORIGINAL continuous audio, looping
the visuals if shorter than the song. Cached on `clips.montage_key`;
concurrent builds for the same clip are serialized with a per-clip lock
(`_lock_for` in that file) — a real Windows race was found and fixed here,
don't remove it (see `docs/WORKFLOWS.md`).

Module map:

| Module | Responsibility |
| --- | --- |
| `config.py` | pydantic-settings, `NHAC_`-prefixed env vars, validated at boot |
| `db.py` / `models.py` | engine/session + ORM; `db.py` also has a small ad-hoc SQLite column-migration shim (`_ensure_added_columns`) — extend `_ADDED_COLUMNS` when adding a column to an existing table |
| `storage/` | `Storage` protocol; `local` (default) and `s3` (R2/S3) backends |
| `audio/ffmpeg.py` | probe, extract audio sample, thumbnail, quality estimate |
| `analysis/excitement.py` | flash (luma-delta) + loudness (RMS) → highlight segments |
| `fingerprint/` | `Fingerprinter` ABC + `mock`/`audd`/`acoustid` + registry |
| `pipeline/` | `process_clip`, `organize` (concert/playlist grouping), `montage` (hype cut) |
| `services/` | DB-facing logic: clips, songs, concerts, playlists, playback, users |
| `routers/api.py` | JSON API (`/api/...`) |
| `routers/web.py` | server-rendered pages, incl. `/play/<playlist_id>` theater mode |
| `templates/`, `static/` | Jinja2 HTML + vanilla JS/CSS |

## Conventions & gotchas (learned the hard way — don't reintroduce these)

- **`LocalStorage._path` must stay pure-lexical** (no `Path.resolve()` on the
  target path). `resolve()` touches the filesystem and can race with a
  sibling thread's `mkdir()` of the same not-yet-existing directory — this
  caused a real intermittent 500 under concurrent montage builds on Windows.
  Safety checks use `os.path.normpath` + string prefix comparison instead.
- **Derived storage writes must be tracked for cleanup.** `process_clip`
  writes `thumbnails/<id>.jpg` and `audio/<id>.mp3` to storage *before* the
  commit that persists their keys, so the failure handler's `rollback()` used
  to strand the files with no row referencing them. It now records each
  derived key and, after committing the terminal state, deletes the ones the
  persisted row doesn't reference (`_discard_unreferenced`). Add any new
  derived artifact to that list — the raw upload deliberately stays.
- **Single-user MVP.** `deps.get_current_user` always returns one seeded
  local account (`services/users.get_or_create_default_user`). There is no
  real auth yet — don't assume multi-user isolation.
- **The mock fingerprinter is deterministic per audio-content hash**, not
  random. Re-uploading similar synthetic test clips will often match the same
  fake song and land in the same concert — expected, not a bug. `var/` is
  gitignored local state; wipe it (`rm -rf var`) for a clean slate when testing.
- **Windows console encoding**: terminal output may mangle non-ASCII
  characters (em-dashes etc.) via cp1252 — this is a display artifact of the
  shell, not data corruption. Verify actual bytes (DB row / raw HTTP response)
  before concluding something is a real encoding bug.
- Enum columns use `Enum(..., native_enum=False)` (plain string columns), so
  adding a new enum value never needs a DB-level migration.

## Testing patterns

- `tests/conftest.py` builds real short mp4s via ffmpeg (`sample_video`,
  `flashy_video` fixtures) rather than mocking media — the pipeline is
  exercised for real end to end. Only the fingerprint provider is
  monkeypatched (a stub `Fingerprinter`) for deterministic song matches.
- Prefer testing through the HTTP layer (`TestClient`) over calling service
  functions directly — it catches wiring bugs unit tests miss. This is how
  the montage race condition and several route bugs were actually caught.
- For anything touching concurrency (see the montage lock above), write a
  regression test with `concurrent.futures.ThreadPoolExecutor` against
  `TestClient`, not just a sequential call.
- There's no browser/JS test runner in this repo. Verify JS changes with
  `node --check <file>` (syntax only) plus live server checks, and say so
  explicitly when reporting — it's weaker coverage than the Python side.

## Where to go deeper

- `docs/ARCHITECTURE.md` — system diagram, module responsibilities, scaling notes
- `docs/WORKFLOWS.md` — every pipeline traced to exact functions, with a status table
- `docs/ROADMAP.md` — phased build plan / what's done vs. Phase 2
- `docs/TODO.md` — cross-cutting checklist (correctness, tests, security,
  perf, UX/a11y, ops, docs) that ROADMAP/NOTES don't already cover
- `docs/DECISIONS.md` — why SQLite / local storage / mock fingerprint / etc. were chosen
- `docs/SETUP.md` — full environment setup, incl. real fingerprint providers, R2/S3
- `docs/NOTES.md` — decisions explicitly left for the owner (provider choice, auth, native app)
- `docs/LEGAL.md` — copyright / personal-use stance
