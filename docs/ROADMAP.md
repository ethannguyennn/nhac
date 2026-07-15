# Roadmap & Build Todos

Legend: `[ ]` todo · `[~]` partial · `[x]` done.

---

## Phase 0 — Foundations `[x]`

- [x] Python project (pyproject, ruff, pytest, env templates, gitignore)
- [x] Typed settings (pydantic-settings), logging
- [x] SQLAlchemy models + Pydantic schemas + enums/constants
- [x] Storage abstraction (local default, S3/R2 adapter)
- [x] ffmpeg module (probe, extract sample, thumbnail, quality)
- [x] Fingerprinter interface + mock/AudD/AcoustID + registry
- [x] Pipeline (process_clip, organize) + services layer
- [x] FastAPI app: JSON API + server-rendered web UI (mobile-first)
- [x] Demo seed (generates real playable clips) + pytest suite

## Phase 1 — MVP `[x] (local, single-user)`

- [x] Upload a video (web, mobile-first)
- [x] Extract audio (ffmpeg) end-to-end
- [x] Identify song (pluggable provider; mock default) with confidence gate
- [x] Manual-tag fallback
- [x] Auto-organize into concert + playlist
- [x] Playback UI + audio-reactive visualizer
- [x] Demo mode for cold start
- [x] End-to-end tested (pytest, live server verified)

**MVP exit criteria — met:** upload a real clip → identified (or manually
tagged) → auto-filed into a concert → played back with a visual. Demo mode shows
sample concerts to a brand-new user.

### To make the MVP "real" (your decisions — see NOTES.md)

- [ ] Pick + wire a real fingerprint provider (AudD or AcoustID) with a key
- [ ] Decide storage: stay local vs Cloudflare R2 / S3 (adapter ready)
- [ ] Decide DB: stay SQLite vs Postgres (change one env var)
- [ ] Real auth if this goes multi-user (currently one local user)
- [ ] Capture true `recorded_at` from video metadata for better grouping

## Phase 2 — Collaboration & polish

- [ ] **Collaborative concerts:** invite friends (`concert_members`), merge clips
- [ ] **Cleanest-audio selection:** finish `estimate_audio_quality` (SNR / HF
      crowd-noise), pick primary audio per concert-song
- [ ] **Multi-angle b-roll:** ffmpeg edit across angles synced to primary audio
- [ ] **Chapters/timestamps** within longer clips
- [ ] **Favorites/ratings** → auto "greatest hits" playlist (`favorites` table exists)
- [ ] **Short-clip export & social sharing** (review each platform's API ToS)
- [ ] **Search & filter:** artist / venue / date / vibe tag
- [ ] **Offline mode:** cache clips locally for playback

## Cross-cutting backlog

- [ ] Move the pipeline to a queue + worker when inline processing strains
- [ ] Live clip-status updates (poll or websockets) instead of blocking upload
- [ ] Transcode step (smaller playback renditions) + poster tuning
- [ ] Cache repeat fingerprint matches; rate-limit provider calls
- [ ] Alembic migrations for schema changes (dev uses `create_all` today)
- [ ] CI: ruff + pytest on push (GitHub Actions)
- [ ] More tests: storage backends, organize edge cases, provider adapters
- [ ] Native mobile app (if the responsive web app isn't enough) — see NOTES.md
- [ ] Surface the legal disclaimer prominently at first upload
