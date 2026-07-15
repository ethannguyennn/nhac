# Legal & Copyright Notes

> Not legal advice — engineering guidance. Consult a professional before public
> launch or monetization.

## The stance

Nhạc is for people replaying **their own recordings of concerts they attended**,
for personal, non-commercial nostalgia and limited short-clip sharing. That's
closer to personal use than redistribution — but recording a live performance
still involves the performer's and songwriters' rights, so this is a genuine
**gray area**, not a cleared one.

## Guardrails we build in

- **Personal-use disclaimer at the point of upload** (stubbed in the mobile
  `upload` screen and web `App`): _"For personal use. You're responsible for the
  footage you upload and share."_ Keep it visible.
- **No mass-redistribution features.** No public firehose of full sets, no
  "download anyone's full concert." Sharing is limited to **short highlight
  clips** (Phase 2), which leans toward fair-use-ish territory.
- **Private by default.** Clips are visible to the uploader (and invited concert
  members in Phase 2), not the public. Enforced by RLS in `0002_rls.sql`.
- **Fingerprint metadata only.** We use recognition to *label* a user's own clip
  (artist/title), not to fetch or serve the original studio recording.
- **Takedown-friendly.** Keep deletion simple (cascade deletes are in the schema)
  so we can honor removal requests quickly.

## Third-party terms to review before launch

- **Fingerprint provider ToS** (AudD/ACRCloud/AcoustID): confirm allowed use of
  results, attribution, and rate/commercial terms.
- **Social sharing APIs** (Instagram/TikTok, Phase 2): each has its own content
  and API ToS for posting user media — review per platform before shipping
  export.
- **App stores:** Apple/Google both have UGC + copyright policy requirements
  (report/takedown flow, moderation). Budget for a basic reporting mechanism.

## If this grows up

Consider: a real Terms of Service + Privacy Policy, a DMCA/takedown process and
registered agent, clearer messaging that users are responsible for their
content, and legal review of any monetization (which weakens personal-use
arguments). Revisit this doc before any public/commercial launch.
