"""AcoustID adapter (https://acoustid.org).

Free + open, MusicBrainz-backed. Needs the ``fpcalc`` (Chromaprint) binary on
PATH and NHAC_ACOUSTID_API_KEY. Install the extra: ``pip install -e ".[acoustid]"``.
Metadata is sparser than AudD (no artwork), but there's no cost.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from nhac.config import settings
from nhac.fingerprint.base import Fingerprinter, FingerprintMatch
from nhac.logging_config import get_logger

log = get_logger(__name__)

_LOOKUP_URL = "https://api.acoustid.org/v2/lookup"


class AcoustIDFingerprinter(Fingerprinter):
    name = "acoustid"

    def __init__(self) -> None:
        if not settings.acoustid_api_key:
            raise RuntimeError("NHAC_ACOUSTID_API_KEY is not set")
        self._key = settings.acoustid_api_key

    def identify(self, audio_path: Path) -> FingerprintMatch:
        try:
            import acoustid  # provided by the `acoustid` extra (pyacoustid)
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "pyacoustid not installed. Run: pip install -e \".[acoustid]\" "
                "and ensure the `fpcalc` binary is on PATH."
            ) from exc

        duration, fingerprint = acoustid.fingerprint_file(str(audio_path))
        params = {
            "client": self._key,
            "duration": int(duration),
            "fingerprint": fingerprint,
            "meta": "recordings+releasegroups",
        }
        resp = httpx.post(_LOOKUP_URL, data=params, timeout=30.0)
        resp.raise_for_status()
        payload = resp.json()

        results = payload.get("results") or []
        if not results:
            return FingerprintMatch.no_match(raw=payload)

        best = max(results, key=lambda r: r.get("score", 0))
        recordings = best.get("recordings") or []
        if not recordings:
            return FingerprintMatch.no_match(raw=payload)

        rec = recordings[0]
        artist = None
        if rec.get("artists"):
            artist = ", ".join(a.get("name", "") for a in rec["artists"]).strip(", ")

        return FingerprintMatch(
            matched=True,
            title=rec.get("title"),
            artist=artist,
            confidence=float(best.get("score", 0.0)),
            external_ids={"acoustid": best.get("id", ""), "mb_recording": rec.get("id", "")},
            raw=payload,
        )
