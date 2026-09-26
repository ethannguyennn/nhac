# Workflows

Pipelines with the exact modules/functions that implement each step.

Legend: ✅ implemented & tested · 🟡 implemented, needs a real provider/key · ⛔ Phase 2.

---

## 1. Upload → identify → organize ✅

```
CLIENT                          APP
──────                          ───
pick video ──POST /upload─────▶ routers/web.upload_submit (or api.upload_clip)
                                 └─ uploads.ingest_upload
                                     • validate type/size
                                     • storage.save_bytes(raw/<id>.ext)
                                     • services.clips.create_clip
                                     • run_in_threadpool(process_clip) ──┐
                                                                          ▼
                                 pipeline.process_clip (own DB session)
                                   1 ffmpeg.probe            → duration/w/h
                                   2 ffmpeg.extract_thumbnail→ thumbnails/<id>.jpg
                                   3 ffmpeg.extract_audio_sample → audio/<id>.mp3
                                   4 ffmpeg.estimate_audio_quality (best-effort)
                                   5 fingerprint.identify(sample)
                                       (retried on transient provider errors;
                                        unreachable → unidentified + dead letter)
                                   6 write Recognition row
                                   7 if confident: upsert Song, link Clip,
                                       status=identified, organize()
                                     else: status=unidentified
◀── redirect to concert / tag ──┘   (API: 201 + UploadResultOut)
```

**Decision gate:** accept only if `confidence ≥ MIN_MATCH_CONFIDENCE` (0.5,
`constants.py`). Below → `unidentified` → manual tag. This is the
~90%-not-100% philosophy in code.

**Sample, not full track:** ~15s starting 5s in (`FINGERPRINT_SAMPLE_*`) —
cheaper per API call, skips the noisy intro.

**Failure path:** any exception mid-pipeline → rollback, then `status=failed`
+ `error_message` committed, so a clip never sits in `processing` forever.
That rollback also discards the not-yet-committed `thumbnail_key`/`audio_key`,
so the files those steps already wrote would be orphaned — `process_clip`
therefore deletes the derived objects this run wrote that the persisted row
doesn't reference (`_discard_unreferenced`). The raw upload is kept (user's
footage, and what a retry re-reads); undeletable keys are logged at WARNING
for a later sweep.

**Provider-outage path:** `audd`/`acoustid` are HTTP calls to someone else's
server, so their failures say nothing about the clip. `RetryingFingerprinter`
(`fingerprint/retry.py`, applied in the registry so every network provider
inherits it) retries what a retry could fix — timeouts, connection errors,
5xx, 429 — with exponential backoff (`FINGERPRINT_*` in `constants.py`), and
normalizes anything left into `FingerprintUnavailable`. Answers (including a
clean "no match") and permanent errors (4xx, malformed payload, missing
`fpcalc`) are never retried.

If the provider is still unreachable, `process_clip._record_provider_failure`
degrades the clip to `unidentified` — the manual-tag path — instead of
`failed`, which would be a dead end offering the uploader nothing. It
**commits** rather than rolling back, so the thumbnail and audio sample
survive (the failure path above would have swept them as orphans, destroying
the very sample a retry needs). The attempt is kept as a dead-letter
`Recognition` row (`error` set, plus `attempts`/`transient` in
`raw_response`), which is what makes an outage a queryable backlog instead of
a silent pile of clips indistinguishable from genuine misses.

Covered by `tests/test_upload_flow.py::test_upload_identifies_and_organizes`,
`tests/test_upload_failure_cleanup.py`, and
`tests/test_fingerprint_failures.py`.

---

## 1b. Replaying the dead-letter queue ✅

```
services.clips.list_provider_failures   → clips whose LATEST recognition errored
  (transient_only=True skips what a retry can't fix, e.g. a rejected API key)
  → pipeline.process_clip.retry_fingerprint(clip_id)
      • re-sends the audio sample ALREADY in storage — no ffmpeg, no
        re-analysis (that's why the degraded path preserves it)
      • identified → upsert Song, link, organize(), clear error_message
      • answered-but-missed → clear error_message, leave to manual tagging
      • still unreachable → another dead-letter row, stays queued
      • no stored sample → falls back to the full process_clip
  → scripts/retry_fingerprints.py [--run] [--all] [--limit N]
```

**Only the latest attempt counts.** "Has ever failed" would be wrong both
ways: a clip the provider later answered would never leave the queue and
would be re-asked forever, and a clip that answered once but hit an outage on
a later retry would never join it.

`retry_fingerprint` refuses clips that are no longer `unidentified`, so a
machine guess can never overwrite a song a user tagged by hand.

---

## 1c. Naming the concert first (bulk upload) ✅

```
POST /concerts/new  (or POST /api/concerts)         → services.concerts.create_concert
  • artist required; title defaults to artist, date defaults to today
  • eagerly creates the concert's playlist

GET/POST /concerts/{id}/upload  (or POST /api/concerts/{id}/clips, multi-file)
  → uploads.ingest_upload(..., concert_id=id) PER FILE
      • clip pre-assigned: Clip.concert_id set at creation
      • attached to the concert's playlist IMMEDIATELY — before the pipeline
        runs, so it lands there whether the clip later identifies, misses,
        or the fingerprint provider is unreachable
      • pipeline.organize.auto_group_into_concert short-circuits when
        clip.concert_id is already set: it never re-derives (or moves) the
        concert from the fingerprinted artist/date, so a confident match for
        a DIFFERENT artist (opener, cover, fingerprinting quirk) can't
        relocate the clip, and neither can a later manual tag
```

**Why name the show first:** the ordinary flow (§1) can only group a clip
once it's identified — a miss stays ungrouped until manually tagged one clip
at a time. Naming the concert up front fixes the grouping decision before any
audio is even fingerprinted, so a whole batch of clips from one night files
together regardless of per-clip identification outcome, and the manual-tag
form (§2) can pre-fill the artist from the concert — a miss then only costs
a song title, not an artist too.

Covered by `tests/test_manual_concerts.py`.

---

## 2. Manual tagging fallback ✅

```
unidentified clip
  → GET /clips/<id>/tag           (routers/web.tag_form)
  → POST /clips/<id>/tag          (services.clips.apply_manual_tag)
      • upsert Song(artist, title)
      • link clip (match_source=manual, status=manually_tagged)
      • organize() → concert + playlist
```

Every clip lands somewhere even when fingerprinting misses. If the clip
belongs to a concert named up front (§1c), the artist field is pre-filled
from `clip.concert.artist` — editable, not authoritative, so an opener or a
misnamed show can still override it — and submitting never moves the clip to
a different concert (organize's short-circuit again).

Covered by `test_upload_unidentified_then_manual_tag` and
`tests/test_manual_concerts.py`.

---

## 3. Auto-organization (grouping) ✅

```
identified / tagged clip
  → pipeline.organize.auto_group_into_concert
      • key = (uploader, artist, recorded date)
      • find or create Concert
      • ensure concert Playlist (services.playlists.ensure_concert_playlist)
      • add PlaylistItem
```

Same-artist clips on the same day form one concert; a different day starts a new
one. Phase 2 refines with venue/geo + collaborative membership.

---

## 4. Theater mode (playlist playback) ✅

```
concert card ▶ / "Play all · shuffle" → GET /concerts/<id>/play
  → 303 → GET /play/<playlist_id>   (routers/web.theater)
      • services/playback.build_queue → items w/ media / montage / thumb URLs
      • queue embedded in the page as JSON (</ escaped)
  → static/js/player.js (NhacPlayer)
      • SHUFFLE ON by default (persisted; Fisher-Yates, reshuffle on wrap)
      • autoplay; if the browser blocks it → animated "tap to start" overlay
      • screen = video only; mousemove/tap fades controls in, ~2.8s idle
        fades them (and the cursor) out
      • controls: play/pause · next · prev · shuffle · hype cut · mute ·
        fullscreen · drag-to-seek progress; keyboard (space/n/p/s/h/m/f/←/→)
      • cinematic track-intro card, blurred backdrop crossfade, eq bars,
        Media Session metadata for lock-screen controls
```

`/play/<playlist>?track=<clip>` starts at a specific clip (concert rows use
it). Local media is served at `/media` with **HTTP range support** so
scrubbing works. Single-clip page (`/clips/<id>`) keeps the simple player +
visualizer and links into the theater.

---

## 5. Excitement detection → hype cut ✅

```
process_clip step 4.5 (every upload; backfill: scripts/build_highlights.py)
  → analysis/excitement.compute_window_scores
      • video pass: fps=8 tiny-frame signalstats YAVG → |Δ luma| = FLASH
      • audio pass: astats per 0.5s window → RMS dB   = LOUDNESS
      • percentile-normalize per clip, blend 0.6·loud + 0.4·flash, smooth
  → select_highlights: greedy top windows → ~3.5s non-overlapping segments
      (~60% coverage, ≤10) → clip_highlights rows

POST /api/clips/<id>/montage   (or theater ⚡ button)
  → pipeline/montage.build_montage
      • video: trim+concat the highlight segments (hard cuts)
      • audio: the ORIGINAL track, continuous — music never stops while
        the visuals jump between the best moments; visuals loop if shorter
      • exports/hype_<clip>.mp4, cached on clips.montage_key
      • short clips (whole-clip highlight) reuse the raw file — no encode
```

Verified: on a synthetic quiet/dark → LOUD/FLASHING → quiet/dark video the
analyzer selects the middle section (score ≈ 1.0) and the montage renders
with continuous audio (`tests/test_excitement.py`, `tests/test_playback.py`).

---

## 6. Cleanest-audio selection ⛔ (Phase 2)

Groundwork done: `audio/ffmpeg.estimate_audio_quality` scores each clip
(volumedetect mean/peak; higher = cleaner) and stores
`clips.audio_quality_score`. Next: for a song with multiple contributed clips,
pick `max(audio_quality_score)` as the primary audio, and refine the heuristic
with a high-frequency crowd-noise / SNR proxy.

---

## 7. Multi-angle b-roll ⛔ (Phase 2)

```
inputs: N clips of the same concert-song
audio : the cleanest clip (workflow 6)
video : ffmpeg concat/xfade across angles, synced to that audio → exports/
```

The single-clip hype cut (workflow 5) already built the trim/concat/mux
machinery this needs — the remaining work is cross-clip sync.

---

## Status summary

| Workflow                        | State |
| ------------------------------- | ----- |
| 1 Upload→identify→organize      | ✅    |
| 1b Provider retry / dead letter | ✅    |
| 1c Name concert first (bulk)    | ✅    |
| 2 Manual tagging                | ✅    |
| 3 Auto-organization             | ✅    |
| 4 Theater mode + visualizer     | ✅    |
| 5 Excitement detection→hype cut | ✅    |
| 6 Cleanest-audio                | ⛔ (scoring stubbed in) |
| 7 Multi-angle b-roll            | ⛔    |
