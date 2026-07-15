"""Offline mock fingerprinter — the MVP default.

Deterministic: the same audio file always maps to the same result, so demos are
stable. Picks from a small catalog of real songs (so playlists show variety) and
returns "no match" for a slice of inputs to exercise the manual-tag fallback.

Zero network, zero API key. Swap to AudD/AcoustID via NHAC_FINGERPRINT_PROVIDER.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from nhac.fingerprint.base import Fingerprinter, FingerprintMatch

# Small catalog of well-known tracks for believable demo output.
_CATALOG: list[dict[str, str]] = [
    {"title": "Coffee", "artist": "Beabadoobee", "album": "Loveworm"},
    {"title": "The Perfect Pair", "artist": "Beabadoobee", "album": "Beatopia"},
    {"title": "Lisztomania", "artist": "Phoenix", "album": "Wolfgang Amadeus Phoenix"},
    {"title": "1901", "artist": "Phoenix", "album": "Wolfgang Amadeus Phoenix"},
    {"title": "Redbone", "artist": "Childish Gambino", "album": "Awaken, My Love!"},
    {"title": "Electric Feel", "artist": "MGMT", "album": "Oracular Spectacular"},
    {"title": "Somebody Else", "artist": "The 1975", "album": "I Like It When You Sleep..."},
    {"title": "Motion Sickness", "artist": "Phoebe Bridgers", "album": "Stranger in the Alps"},
]


class MockFingerprinter(Fingerprinter):
    name = "mock"

    # ~1 in this many inputs returns no match (drives the manual-tag path).
    no_match_every = 6

    def identify(self, audio_path: Path) -> FingerprintMatch:
        digest = self._digest(audio_path)
        n = int(digest[:8], 16)

        if n % self.no_match_every == 0:
            return FingerprintMatch.no_match(
                raw={"provider": self.name, "reason": "simulated_miss"}
            )

        entry = _CATALOG[n % len(_CATALOG)]
        # Stable pseudo-confidence in [0.6, 0.95].
        confidence = round(0.6 + (int(digest[8:10], 16) / 255) * 0.35, 3)
        return FingerprintMatch(
            matched=True,
            title=entry["title"],
            artist=entry["artist"],
            album=entry["album"],
            confidence=confidence,
            external_ids={"mock_digest": digest[:12]},
            raw={"provider": self.name, "entry": entry, "confidence": confidence},
        )

    @staticmethod
    def _digest(audio_path: Path) -> str:
        h = hashlib.sha256()
        try:
            with audio_path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
        except OSError:
            h.update(str(audio_path).encode())
        return h.hexdigest()
