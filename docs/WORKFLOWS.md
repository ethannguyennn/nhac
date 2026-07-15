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

## 4. Playback ✅

```
GET /clips/<id>  (routers/web.clip_player)
  → <video src=media_url(raw_video_key)> + poster=thumbnail
  → static/js/app.js draws an audio-reactive visualizer (Web Audio API)
```

Local media is served by StaticFiles at `/media` with **HTTP range support**, so
scrubbing works. Remote backends resolve to presigned/public URLs.

---

## 5. Cleanest-audio selection ⛔ (Phase 2)

Groundwork done: `audio/ffmpeg.estimate_audio_quality` scores each clip
(volumedetect mean/peak; higher = cleaner) and stores
`clips.audio_quality_score`. Next: for a song with multiple contributed clips,
pick `max(audio_quality_score)` as the primary audio, and refine the heuristic
with a high-frequency crowd-noise / SNR proxy.

---

## 6. Multi-angle b-roll ⛔ (Phase 2)

```
inputs: N clips of the same concert-song
audio : the cleanest clip (workflow 5)
video : ffmpeg concat/xfade across angles, synced to that audio → exports/
```

Most complex Phase-2 item; prototype offline before wiring to UI.

---

## Status summary

| Workflow                     | State |
| ---------------------------- | ----- |
| 1 Upload→identify→organize   | ✅    |
| 2 Manual tagging             | ✅    |
| 3 Auto-organization          | ✅    |
| 4 Playback + visualizer      | ✅    |
| 5 Cleanest-audio             | ⛔ (scoring stubbed in) |
| 6 Multi-angle b-roll         | ⛔    |
