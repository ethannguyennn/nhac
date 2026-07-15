# Notes for you (decisions I left open)

You said: _build the MVP, don't do anything risky, ask me later, move on._ Here's
what I built, and the calls I deliberately **did not** make on your behalf —
because they need your account, your money, or your product judgment. None of
these block the MVP; it runs today without them.

## What's done and verified ✅

- Full Python rewrite (FastAPI + Jinja2 + SQLAlchemy). The old TypeScript scaffold
  is gone.
- Working end-to-end loop: **upload → ffmpeg audio extract → fingerprint → identify
  → auto-organize into concert/playlist → play back with a visualizer**, plus the
  manual-tag fallback.
- Runs locally with **zero external accounts** (SQLite + local files + offline mock
  recognizer).
- Demo mode seeds real, playable sample concerts.
- `pytest` (7 tests) green; `ruff` clean; verified against a live server with real
  generated video (identify + manual-tag + media range serving all confirmed).

## Decisions for you (pick when you're back)

1. **Real song recognition.** Default is the offline **mock** (fake but
   deterministic matches — great for demos, not real IDs). To identify real songs,
   pick a provider and add a key:
   - **AudD** — easiest, paid with a small trial. `NHAC_FINGERPRINT_PROVIDER=audd` + `NHAC_AUDD_API_TOKEN`.
   - **AcoustID** — free/open, needs the `fpcalc` binary; sparser metadata.
   - _I did not sign up or enter payment info for either — that's yours to choose._
   - ⚠️ Verify current pricing/limits; they change.

2. **Storage.** Default is **local disk**. Cloudflare **R2** (S3-compatible, no
   egress fees) is wired behind `NHAC_STORAGE_BACKEND=s3`. Flip it when you have a
   bucket + keys. (Didn't create cloud resources for you.)

3. **Database.** Default **SQLite**. Change `NHAC_DATABASE_URL` to a Postgres URL
   for a hosted DB. Add Alembic before you depend on migrations.

4. **Auth / multi-user.** MVP is **single local user**. Real accounts are needed
   before other people use it or before collaborative concerts (Phase 2). It's
   isolated behind one dependency (`get_current_user`) so it's a clean add. Tell me
   which direction (email magic-link? OAuth? Supabase Auth?).

5. **Native mobile app?** I built a **mobile-first responsive web app** (open it in
   your phone browser — the fast path to "works on my phone"). A real React Native
   app can't be Python and is a bigger lift; say the word if you want it and I'll
   plan it as a separate client against the existing JSON API.

## Things I intentionally skipped as "risky"

- Creating third-party accounts / entering payment details.
- Provisioning cloud infra (R2 buckets, Postgres, hosting).
- Deploying anywhere public.
- Building auth I'd have to guess the requirements for.

## Suggested next session

Fastest path to a "real" MVP: **(1)** choose a fingerprint provider + key, **(2)**
decide local vs R2 storage, **(3)** decide if/what auth. I can wire all three
quickly once you've made the calls. See [ROADMAP.md](ROADMAP.md) Phase 1 tail.
