# TODO — path to "absolutely perfect"

A working checklist, not a spec. `- [ ]` boxes render as clickable checkboxes
in Obsidian — tick them there and the change lives in this file.

This is **additive** to [ROADMAP.md](ROADMAP.md) (phased build plan) and
[NOTES.md](NOTES.md) (decisions only you can make) — it doesn't repeat their
items, it covers what those two don't: correctness hardening, test gaps,
security, performance, UX polish, ops, and docs. Skim those two first so you
have the full picture; start here when you're ready to work a list top to
bottom.

Rough priority order top → bottom within each section; sections themselves
are roughly ordered by "matters before anyone but you uses this."

---

## 1. Correctness & robustness (do these regardless of scale)

- [x] **Upload failure cleanup** — DONE. Two halves; one already held, one
      leaked. *Terminal state* was fine: the handler rolls back, re-reads the
      clip and commits `failed` + `error_message`, so nothing sticks in
      `processing` — now pinned by a test rather than assumed. *Orphaned
      storage* was real: the thumbnail (step 2) and audio sample (step 3) are
      written to storage immediately, but their keys only reach the DB at a
      LATER commit, so the handler's `session.rollback()` threw the keys away
      while the files stayed on disk — bytes no row referenced and nothing
      would ever reclaim, or even name. `process_clip` now tracks the derived
      keys it writes and, *after* the terminal state is committed, deletes the
      ones the persisted row doesn't reference (`_discard_unreferenced`).
      The raw upload is never touched (it's the user's footage, and what any
      retry would re-read), and a key that can't be deleted is logged at
      WARNING *with the key* so a sweep job has something to work from.
      Pinned by `tests/test_upload_failure_cleanup.py` (7 tests; the 3 orphan
      ones verified to fail against pre-fix behaviour).
- [x] **Retry / dead-letter for fingerprint provider errors** — DONE. It did
      not crash the thread or 500 the uploader (the catch-all handler caught
      it), but it did something worse than either: it marked the clip
      **`failed`**. That's a dead end — no route to the manual-tag page the
      "we didn't recognize it" path offers — and because the handler rolls
      back, the orphan sweep then deleted the thumbnail AND the audio sample,
      i.e. the very sample any retry would need. One 503 from AudD
      permanently cost a good clip, and left no record that a provider was
      ever involved — the clip sat in the `failed` pile, unsweepable and
      indistinguishable from a genuine transcode failure.
      Three parts now: (1) `fingerprint/retry.py`'s `RetryingFingerprinter`,
      applied **in the registry** so every network provider inherits it,
      retries only what a retry could fix (timeouts, connection errors, 5xx,
      429) with exponential backoff (`FINGERPRINT_*` budgets in
      `constants.py`, ~1.5s worst case since it runs inline in the upload) and
      normalizes the rest into `FingerprintUnavailable`; a clean "no match" is
      an *answer* and is never retried. (2) `process_clip` degrades an
      unreachable provider to **`unidentified`** and **commits** instead of
      rolling back, so the derived artifacts survive. (3) the attempt is kept
      as a dead-letter `Recognition` row (`error`, plus `attempts`/`transient`
      in `raw_response`); `services.clips.list_provider_failures` is the
      queue and `scripts/retry_fingerprints.py` replays it through
      `process_clip.retry_fingerprint`, which re-sends the *stored* sample —
      no ffmpeg, no re-analysis. Only the **latest** attempt decides
      membership, so a clip leaves the queue once the provider answers (even
      with a miss) and rejoins it if a later retry hits an outage. A retry
      never overwrites a manual tag. Pinned by
      `tests/test_fingerprint_failures.py` (37 tests; the 13 pipeline/queue
      ones verified to fail against pre-fix behaviour).
- [x] **ffmpeg subprocess timeouts** — DONE. All 4 call sites
      (`audio/ffmpeg.py` `_run` + `estimate_audio_quality`,
      `analysis/excitement.py` `_run_metadata_pass`, `pipeline/montage.py`
      `_run_ffmpeg`) ran with no timeout; a hung ffmpeg wedged a threadpool
      worker permanently, and in montage.py it hung *while holding the
      per-clip lock*, deadlocking that clip for every later request.
      Budgets now live in `constants.py` (`FF*_TIMEOUT_SECONDS`, deliberately
      generous). Each timeout degrades into the module's existing error path,
      so a clip reaches a terminal `failed` state instead of stuck
      `processing`. Pinned by `tests/test_ffmpeg_timeouts.py` (9 tests,
      verified to fail against pre-fix behaviour).
- [ ] **Concurrent uploads of the exact same file** (double-tap submit on
      mobile): confirm this doesn't create two `Clip` rows for one physical
      upload, or if it does, that it's harmless (two clips, same song, fine)
      rather than a storage-key collision.
- [ ] **`organize`'s concert-grouping window edge cases**: two clips exactly
      `CONCERT_GROUPING_WINDOW_MINUTES` apart, clips uploaded out of
      chronological order, a clip whose `recorded_at` is missing/defaults to
      upload time — add regression tests for each (`docs/WORKFLOWS.md` should
      already trace the intended behavior; verify tests match it).
- [ ] **Partial montage builds**: if `build_montage` dies partway (ffmpeg OOM,
      disk full mid-render), confirm the per-clip lock releases and
      `montage_key` isn't left pointing at a truncated/missing file.
- [ ] **Timezone consistency**: `recorded_at`, `created_at`, concert
      `performed_on` — confirm everything is stored/compared in one timezone
      (UTC) and only converted for display; a mixed-timezone bug would quietly
      break concert grouping.
- [ ] **SQLite concurrent-write behavior under real load**: confirm the
      pipeline's own DB session + the request session don't deadlock under
      SQLite's single-writer model once more than a couple of uploads land at
      once (this is the concrete reason to move to Postgres before more than
      one person uses this — see [NOTES.md](NOTES.md) #3).

## 2. Test coverage gaps

- [ ] Storage backend tests for `s3`/R2 adapter (currently only exercised
      manually, if at all — `local` is what the suite covers).
- [ ] `organize` edge cases from section 1 above, as explicit test cases.
- [~] Fingerprint provider adapters (`audd.py`, `acoustid.py`) — timeout /
      5xx / 429 / 4xx / malformed-response handling is covered at the
      `RetryingFingerprinter` boundary every provider is wrapped in
      (`tests/test_fingerprint_failures.py`). Still untested: each adapter's
      own **response parsing** (AudD's `apple_music` artwork rewrite and
      spotify/apple id extraction, AcoustID's best-score pick and artist
      join) — mock the HTTP layer and assert the `FingerprintMatch` they
      build.
- [ ] Upload rejection paths: oversized file, disallowed MIME/extension,
      corrupt video ffmpeg can't probe — confirm each returns a clean 4xx with
      a useful message, not a 500.
- [ ] `estimate_audio_quality` — currently best-effort/unfinished per
      [ROADMAP.md](ROADMAP.md) Phase 2; needs tests once it's finished.
- [ ] Web-page tests (not just `/api/...`): upload form submission,
      tag form submission, theater mode page render — via `TestClient` against
      `routers/web.py`, per the testing convention in `CLAUDE.md`.
- [ ] A regression test that pins the Windows path-race fix in
      `LocalStorage._path` (`resolve()`-free lexical path handling) — the
      montage lock has one; the path bug it was chasing might not.
- [ ] CI wiring so all of the above actually runs on every push (see §5).

## 3. Security & hardening (before this leaves your machine)

- [ ] **Rotate `NHAC_SECRET_KEY`** off the checked-in default
      (`dev-insecure-change-me`) — confirm nothing currently depends on the
      literal dev value, then document that production requires a real
      secret via `.env`.
- [ ] **Rate-limit uploads and the fingerprint-provider path** — a paid
      provider (AudD) means an abusive or buggy client can run up your bill;
      add a per-user/per-IP cap before wiring a real key.
- [ ] **Validate video content, not just extension/MIME header** — `constants.py`
      checks `ALLOWED_VIDEO_MIME`/`ALLOWED_VIDEO_EXT`, both client-supplied and
      spoofable. Confirm `ffprobe` is the actual gate (a non-video file should
      fail at probe, not get stored and served back as "video").
- [ ] **CORS policy** — confirm FastAPI's CORS middleware (if any) is scoped
      correctly once this is reachable from a real domain instead of
      `127.0.0.1`.
- [ ] **CSRF on the server-rendered POST forms** (`/upload`, `/clips/{id}/tag`)
      — fine for single-local-user today, a real gap the moment auth exists.
- [ ] **Presigned URL expiry** on the S3/R2 backend — confirm short-lived, not
      accidentally permanent.
- [ ] Re-run `security-review` (the skill in this environment) once auth and a
      real fingerprint provider are wired — do it again post-auth, not just now.

## 4. Performance & scale (see also ROADMAP's "Cross-cutting backlog")

- [ ] Move upload processing off the inline threadpool to a real queue+worker
      once volume ever makes uploads feel slow (ROADMAP already flags this —
      this entry is the "you'll know it's time when uploads start queueing
      visibly in the UI" trigger condition, worth writing down).
- [ ] Add a transcode/poster-tuning pass so theater mode doesn't serve full
      original-resolution video to a phone on cellular.
- [ ] Cache/memoize repeat fingerprint lookups (same audio hash) instead of
      re-hitting a paid provider — cheap win once a real provider is wired.
- [ ] Add DB indexes for the query patterns `services/concerts.py` and
      `services/playback.py` actually use (recorded_at range scans, playlist
      joins) — profile once real data volume exists, don't guess now.
- [ ] Load-test the montage endpoint — it's ffmpeg-bound and synchronous per
      clip; confirm concurrent montage builds for *different* clips don't
      starve the threadpool (the existing lock only serializes same-clip
      builds, by design).

## 5. DevOps / CI / observability

- [ ] **Correction:** CI already exists (`.github/workflows/ci.yml` — installs
      ffmpeg, runs `ruff check .` + `pytest`). ROADMAP lists it as todo and an
      earlier draft of this file repeated that; both were wrong. The real gap
      is narrower: it triggers only on `push: [main]` and `pull_request`, so
      work on a feature branch like `awesomeness` runs no CI until it's PR'd
      or merged. Widen the trigger (e.g. `push: [main, '**']`) if you want
      branch coverage.
- [ ] Alembic migrations, replacing the `create_all` + `_ensure_added_columns`
      shim in `db.py` — fine for dev, a real risk the first time a column
      needs backfilling instead of just defaulting.
- [ ] Structured logging with request IDs so a failed pipeline run in
      production logs can be traced end-to-end (upload → probe → fingerprint →
      organize) in one grep.
- [ ] Basic uptime/error alerting once this is deployed anywhere reachable by
      other people (even a free tier — Sentry, or a health-check ping).
- [ ] Document (or automate) a backup strategy for `var/nhac.sqlite3` +
      `var/media` before this holds footage you'd be sad to lose.

## 6. UX polish & accessibility

- [ ] Keyboard navigation audit of theater mode beyond the documented shortcuts
      — tab order through controls, visible focus states.
- [ ] Screen-reader pass: alt text on thumbnails/artwork, ARIA labels on the
      icon-only player controls (play/pause, shuffle, hype-cut toggle).
- [ ] `prefers-reduced-motion` coverage check — CLAUDE.md/ROADMAP mention it
      landed for the UI animation pass; confirm it also covers the
      flash/strobe visual effects in theater mode specifically (that's the
      one place a missed check is an actual accessibility/safety issue, not
      just a nicety — flashing effects can trigger photosensitive seizures).
- [ ] Empty/error states: no concerts yet, upload fails, fingerprint times out,
      clip stuck unidentified — confirm each has a real message, not a blank
      screen or raw stack trace.
- [ ] Upload progress feedback for large files on slow mobile connections
      (currently blocks until the pipeline finishes — see the "live clip-status
      updates" item in ROADMAP's cross-cutting backlog; call out here because
      it's as much a UX bug as an architecture one).
- [ ] Cross-browser/device pass: Safari iOS video/audio quirks (autoplay
      restrictions, fullscreen API differences) specifically, since this is
      mobile-first and iOS is the strictest target.

## 7. Documentation

- [ ] Add a `CONTRIBUTING.md` or expand `README.md` if anyone besides you will
      ever touch this repo.
- [ ] `docs/WORKFLOWS.md` status table — sweep it against this list once items
      here get done, so it stays the accurate "what's real vs planned" source.
- [ ] API docs: FastAPI gives you `/docs` for free — confirm response models
      have useful `description`s so that's actually usable as reference, not
      just schema names.
- [ ] Runbook for "the server won't start" / "montage build fails" /
      "fingerprint provider errors" — the kind of thing we just debugged live;
      worth capturing so it's not rediscovered from scratch next time.

## 8. Legal / compliance follow-through

(Tracking pointer only — the real content lives in [LEGAL.md](LEGAL.md),
which already states the stance and guardrails. Listed here so it isn't
missed in an "absolutely perfect" pass.)

- [ ] Confirm the personal-use disclaimer is still surfaced prominently at
      first upload (ROADMAP flags this as outstanding).
- [ ] Review the chosen fingerprint provider's ToS once picked (§ NOTES.md #1)
      for allowed-use and attribution requirements.
- [ ] Revisit LEGAL.md's third-party-terms section before any Phase 2
      short-clip/social-sharing feature ships.

---

## Not on this list on purpose

Anything already tracked as an explicit **owner decision** in
[NOTES.md](NOTES.md) (real fingerprint provider, storage backend, DB engine,
real auth, native mobile app) isn't duplicated here — those are choices, not
engineering todos, and redoing them as checkboxes would just hide whose call
they are.
