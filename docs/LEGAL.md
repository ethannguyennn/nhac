# Legal & Copyright Notes

> Not legal advice — engineering guidance. Consult a professional before public
> launch or monetization.

## The stance

Nhạc is for people replaying **their own recordings of concerts they attended**,
for personal, non-commercial nostalgia and limited short-clip sharing. That's
closer to personal use than redistribution — but recording a live performance
still touches the performers' and songwriters' rights, so this is a genuine
**gray area**, not cleared.

## Guardrails already in the code

- **Personal-use disclaimer** shown on the upload page and in the footer:
  _"For personal use. You're responsible for the footage you upload and share."_
- **No mass-redistribution features.** No public firehose, no "download anyone's
  full set." Sharing (Phase 2) is limited to short highlight clips.
- **Private by design.** Single-user MVP; content isn't public. When multi-user
  arrives, keep clips visible only to the uploader + invited concert members.
- **Fingerprint = labeling only.** Recognition names a user's own clip; we never
  fetch or serve the original studio recording.
- **Easy deletion.** Cascade deletes in the schema make honoring takedowns simple.

## Third-party terms to review before launch

- **Fingerprint provider ToS** (AudD / AcoustID): allowed use of results,
  attribution, rate/commercial terms.
- **Social sharing APIs** (Instagram/TikTok, Phase 2): each platform's content +
  API ToS for posting user media.
- **App stores** (if you ship native): Apple/Google UGC + copyright policies
  require a report/takedown flow.

## If this grows up

Add a real Terms of Service + Privacy Policy, a DMCA/takedown process, clear
"you're responsible for your content" messaging, and legal review of any
monetization (which weakens the personal-use argument). Revisit before any
public or commercial launch.
