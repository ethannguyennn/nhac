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

Covered by `tests/test_upload_flow.py::test_upload_identifies_and_organizes`.

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

Every clip lands somewhere even when fingerprinting misses. Covered by
`test_upload_unidentified_then_manual_tag`.

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
| 2 Manual tagging                | ✅    |
| 3 Auto-organization             | ✅    |
| 4 Theater mode + visualizer     | ✅    |
| 5 Excitement detection→hype cut | ✅    |
| 6 Cleanest-audio                | ⛔ (scoring stubbed in) |
| 7 Multi-angle b-roll            | ⛔    |
