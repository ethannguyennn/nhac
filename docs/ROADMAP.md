# Roadmap & Build Todos

Ordered, checkable build plan. **Finish MVP end-to-end before starting Phase 2.**
Legend: `[ ]` todo · `[~]` scaffolded/stubbed · `[x]` done.

---

## Phase 0 — Foundations `[x]`

- [x] Monorepo + workspaces, TS config, Prettier, `.gitignore`, env templates
- [x] Shared domain types / enums / constants / DTOs (`packages/shared`)
- [x] API skeleton (Express, zod env, logger, error handling, routes)
- [x] Fingerprint provider interface + AudD adapter
- [x] Pipeline skeleton (`processClip`, `organize`)
- [x] Mobile scaffold (Expo Router: library/upload/concert/player)
- [x] Web scaffold (Vite upload flow)
- [x] Supabase schema + RLS + seed

---

## Phase 1 — MVP (make it actually work)

Build in this order; each item should be demoable before moving on.

### 1. Video upload `[~]`

- [ ] Wire Supabase Auth (magic link) in mobile + web; attach JWT to API calls
- [ ] API auth middleware: verify Supabase JWT → `req.userId`
- [ ] `POST /clips/uploads`: insert `clips` row (status=uploading, uploader, key)
- [ ] Confirm direct-to-R2 `PUT` works from device + browser (CORS on the bucket)
- [ ] Capture `recorded_at`/duration/size from the picked asset

### 2. Audio extraction pipeline `[~]`

- [ ] `processClip`: download raw from R2 to a tmp file
- [ ] `extractAudioSample()` end-to-end (verify ffmpeg on the deploy target)
- [ ] Tmp-file lifecycle + cleanup; handle extraction failure → status=failed

### 3. Song fingerprinting + manual fallback `[~]`

- [ ] Get an AudD (or chosen provider) key; confirm current free limits
- [ ] Real `identify()` call; normalize into `FingerprintMatch`
- [ ] Upsert `songs`; write `recognitions`; apply `MIN_MATCH_CONFIDENCE` gate
- [ ] `POST /clips/:id/tag` manual path (upsert song, link, status)
- [ ] Client: prompt manual tag when `identified === false`

### 4. Auto-organization `[~]`

- [ ] `autoGroupIntoConcert()`: grouping-window query + create/attach concert
- [ ] Ensure one `type=concert` playlist per concert; add `playlist_items`
- [ ] `GET /concerts`, `GET /concerts/:id` (ConcertWithClips), `GET /clips/:id`

### 5. Playback UI + basic visuals `[~]`

- [ ] Mobile player: `<Video>` (expo-av) from presigned URL + controls
- [ ] Web player grid + `<video>`
- [ ] Simple warm gradient / audio-reactive visualizer behind playback
- [ ] Concert "album" view grouped by song

### MVP exit criteria

- [ ] Upload a real phone clip → song auto-identified (or manually tagged)
- [ ] Clip auto-lands in the right concert playlist
- [ ] Play it back with a visual, on a phone
- [ ] Demo mode shows sample concerts to a brand-new user

---

## Phase 2 — Collaboration & polish (after MVP)

- [ ] **Collaborative playlists:** invite friends (`concert_members`), merge clips
- [ ] **Cleanest-audio selection:** `estimateAudioQuality()` (volumedetect + HF
      crowd-noise proxy) → pick primary audio per concert-song
- [ ] **Multi-angle b-roll:** ffmpeg edit across angles synced to primary audio
- [ ] **Chapters/timestamps** within longer clips
- [ ] **Favorites/ratings** → auto "greatest hits" playlist across concerts
- [ ] **Short-clip export & social sharing** (Instagram/TikTok) — review each
      platform's sharing API ToS (see DECISIONS/LEGAL)
- [ ] **Search & filter:** artist / venue / date / vibe tag
- [ ] **Offline mode:** cache clips locally for playback

---

## Cross-cutting / infra backlog

- [ ] Move pipeline to a queue + worker once inline processing strains (ARCH)
- [ ] Supabase Realtime for live clip-status updates
- [ ] Thumbnail + transcode step (poster frames, smaller playback renditions)
- [ ] Rate-limit fingerprint calls; cache repeat matches to save quota
- [ ] Observability: structured logs → a log drain; basic error alerting
- [ ] CI: typecheck + lint + `shared` build on PR
- [ ] Tests: pipeline unit tests, provider adapter contract tests
- [ ] EAS build config for mobile store distribution
- [ ] In-app legal disclaimer surfaced at upload (partly stubbed in UI)
