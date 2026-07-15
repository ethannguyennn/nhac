# Decisions (lightweight ADRs)

Records of choices already made, with rationale and things to re-verify.
⚠️ **Pricing/limits below are directional and change often — confirm current
terms on each provider's site before you commit or launch.**

---

## ADR-001 — Split storage: Supabase (metadata) + Cloudflare R2 (video)

**Decision:** Postgres/metadata/auth in Supabase; raw video and derived media in
Cloudflare R2 (S3-compatible).

**Why:** Supabase's free storage (~1 GB) is a non-starter for video. R2's draw is
**no egress fees** (big deal for video playback) and an S3-compatible API. Clients
upload directly via pre-signed URLs so large files never transit our API.

**Verify:** R2 free-tier storage GB + Class A/B operation caps; Supabase free DB
size/row limits. **Alternatives:** AWS S3 (egress $$), Backblaze B2, Supabase
Storage (rejected: cap + egress).

---

## ADR-002 — Fingerprinting, not AI/LLM, for song ID

**Decision:** Audio-fingerprinting service. Default adapter: **AudD**. Interface
supports **ACRCloud** and **AcoustID** behind one `FingerprintClient`.

**Why:** Fingerprinting is the right tool (fast, cheap, deterministic) and
matches the "~90% is fine" bar. LLM audio models are overkill, pricier, and
explicitly out of scope.

**Trade-offs to verify (confirm current terms):**

| Provider     | Model                | Notes                                                             |
| ------------ | -------------------- | ----------------------------------------------------------------- |
| **AudD**     | paid, small trial    | Simplest REST; returns Apple/Spotify metadata + artwork. MVP pick.|
| **ACRCloud** | free dev tier + paid | Generous recognition catalog; HMAC-signed requests.               |
| **AcoustID** | free / donation      | Open, MusicBrainz-backed; needs Chromaprint (`fpcalc`) client-side; metadata sparser. |

**Cost control:** send a ~15s sample, not the full track; cache repeat matches;
rate-limit. Switching provider = add an adapter + change `FINGERPRINT_PROVIDER`.

---

## ADR-003 — Expo / React Native for mobile

**Decision:** Expo (managed) + Expo Router. **Why:** concert footage lives on
phones; team knows the stack; OTA updates and easy device testing. Web app is a
lightweight companion, not the primary surface.

---

## ADR-004 — Node + Express API owns the pipeline

**Decision:** A small stateful Express service (not pure serverless) runs upload
orchestration + ffmpeg + fingerprinting.

**Why:** ffmpeg needs a real runtime; a long-lived process is simpler than an
ffmpeg Lambda layer for MVP. Revisit with a queue+worker at scale (see
ARCHITECTURE "Scaling the pipeline"). **Hosting candidates to price:** Railway,
Render, Fly.io, a small VPS — verify free/hobby tiers + whether ffmpeg is
available or must be bundled.

---

## ADR-005 — No Spotify integration

**Decision:** Standalone player; no Spotify upload/library sync. **Why:** Spotify's
API does not support uploading user audio/video, and it adds copyright exposure
for zero MVP benefit. We may read public metadata/artwork later, nothing more.

---

## ADR-006 — Inline processing now, queue later

**Decision:** `uploads/complete` runs `processClip` inline for MVP.
**Why:** simplest thing that works at low volume. **Migration trigger:** when
uploads back up or ffmpeg contends for CPU → return `202`, enqueue, process in a
worker, push status via Realtime.

---

## ADR-007 — TypeScript everywhere + shared package

**Decision:** One `@nhac/shared` package for types/enums/constants/DTOs, consumed
by API, web, and mobile. **Why:** the API contract can't silently drift across
clients; enums map 1:1 to DB CHECK/enum types.

---

## Open questions

- Final fingerprint provider after a real-world accuracy bake-off on live concert
  audio (crowd noise hurts recognition — test before committing).
- API host + whether ffmpeg ships in that environment.
- Do we transcode/thumbnail on upload, or lazily on first playback?
