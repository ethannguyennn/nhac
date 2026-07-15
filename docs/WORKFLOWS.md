# Workflows

End-to-end pipelines, with the exact files/functions that implement each step.
`TODO` marks glue that's stubbed in the scaffold.

---

## 1. Upload → identify → organize (MVP core)

```
CLIENT                         API                          EXTERNAL
──────                         ───                          ────────
pick video
  │  POST /clips/uploads ─────▶ createUpload()
  │                            • validate (zod)
  │                            • make clipId + storage key
  │                            • presign R2 PUT      ──────▶ Cloudflare R2
  │  ◀── { clipId, uploadUrl } ┘  • TODO insert clip row (status=uploading)
  │
  │  PUT file ─────────────────────────────────────────────▶ R2 (raw/…)
  │
  │  POST /clips/uploads/complete ─▶ processClip(clipId)
  │                                • status=processing
  │                                • TODO download raw from R2
  │                                • extractAudioSample() (ffmpeg) ─┐
  │                                • fingerprint identify() ────────┼─▶ AudD/…
  │                                • upsert Song, link Clip         │
  │                                • write Recognition row          │
  │                                • autoGroupIntoConcert()         │
  │  ◀── 202 { identified } ───────┘  • status=identified|unidentified
  │
  └─ if !identified → prompt manual tag → POST /clips/:id/tag
```

**Files:** `services/api/src/routes/clips.ts` → `pipeline/processClip.ts` →
`providers/fingerprint/*` → `pipeline/organize.ts`. Audio via `lib/ffmpeg.ts`,
storage via `lib/storage.ts`.

**Why a short sample?** We send ~15s (`FINGERPRINT_SAMPLE_SECONDS`) starting a
few seconds in — cheaper per API call and skips the noisy intro. Tune in
`packages/shared/src/constants.ts`.

**Decision gate:** accept the match only if
`confidence ≥ MIN_MATCH_CONFIDENCE` (0.5). Below that → `unidentified` → manual
tag. This is the ~90%-not-100% philosophy in code.

---

## 2. Manual tagging fallback

```
unidentified clip
  → user types artist + title (client)
  → POST /clips/:id/tag
      • upsert Song(artist, title)
      • link clip (match_source = manual, status = manually_tagged)
      • autoGroupIntoConcert(clip)
```

Ensures every clip lands in a playlist even when fingerprinting misses. **File:**
`clips.ts` `POST /:id/tag` (DB writes are TODO).

---

## 3. Auto-organization (grouping)

```
identified/tagged clip
  → autoGroupIntoConcert(clipId)
      • find uploader's concert whose clips are within
        CONCERT_GROUPING_WINDOW_MINUTES (6h) of this clip's recorded_at
      • else create a new Concert (title from artist)
      • set clip.concert_id
      • ensure concert Playlist (type=concert) exists → add PlaylistItem
```

**File:** `pipeline/organize.ts`. Group-by-song within a concert is a read-time
`GROUP BY song_id`. Phase 2 adds venue/geo + collaborative membership.

---

## 4. Playback

```
GET /clips/:id → ClipWithSong + presigned playback URL (createPresignedDownload)
client renders <Video> (expo-av / <video>) + warm visualizer behind it
```

**Files:** `apps/mobile/app/player/[clipId].tsx`, `apps/web` grid (TODO),
`lib/storage.ts` `createPresignedDownload()`.

---

## 5. Cleanest-audio selection (Phase 2)

For a song with multiple contributed clips, pick the least-noisy audio as the
primary track:

```
for each candidate clip:
  ffmpeg: extract audio
  estimateAudioQuality():
    • volumedetect → mean/max volume, clipping
    • high-frequency energy proxy → crowd-noise estimate
    • combine → audio_quality_score (higher = cleaner)
choose max(audio_quality_score) as the concert-song primary audio
```

**File:** `lib/ffmpeg.ts` `estimateAudioQuality()` (throws — not implemented).
Persist to `clips.audio_quality_score`.

---

## 6. Multi-angle b-roll (Phase 2)

```
inputs: N clips of the same concert-song
audio:  the cleanest clip (workflow 5)
video:  ffmpeg concat/xfade cutting between angles, synced to that audio
output: single edited clip → R2 exports/… → shareable
```

Sync uses the fingerprint match offset (or a manual anchor) to align angles.
This is the most complex Phase-2 item; prototype offline before wiring to UI.

---

## Status legend

| Symbol | Meaning                                             |
| ------ | --------------------------------------------------- |
| ✅      | Implemented in scaffold                             |
| 🟡     | Wired but stubbed (`TODO` in code)                  |
| ⛔      | Phase 2 — intentionally not built yet               |

| Workflow                     | State |
| ---------------------------- | ----- |
| 1 Upload→identify→organize   | 🟡    |
| 2 Manual tagging             | 🟡    |
| 3 Auto-organization          | 🟡    |
| 4 Playback                   | 🟡    |
| 5 Cleanest-audio             | ⛔    |
| 6 Multi-angle b-roll         | ⛔    |
