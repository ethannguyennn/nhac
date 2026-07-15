"""AudD adapter (https://docs.audd.io).

Simple REST: POST the audio file + token, get back Apple/Spotify metadata. Set
NHAC_FINGERPRINT_PROVIDER=audd and NHAC_AUDD_API_TOKEN. Verify current free-tier
limits before relying on it (see docs/DECISIONS.md).
"""

from __future__ import annotations

from pathlib import Path

import httpx

from nhac.config import settings
from nhac.fingerprint.base import Fingerprinter, FingerprintMatch
from nhac.logging_config import get_logger

log = get_logger(__name__)

_ENDPOINT = "https://api.audd.io/"


class AudDFingerprinter(Fingerprinter):
    name = "audd"

    def __init__(self) -> None:
        if not settings.audd_api_token:
            raise RuntimeError("NHAC_AUDD_API_TOKEN is not set")
        self._token = settings.audd_api_token

    def identify(self, audio_path: Path) -> FingerprintMatch:
        with audio_path.open("rb") as fh:
            files = {"file": (audio_path.name, fh, "audio/mpeg")}
            data = {"api_token": self._token, "return": "apple_music,spotify"}
            resp = httpx.post(_ENDPOINT, data=data, files=files, timeout=30.0)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("status") != "success" or not payload.get("result"):
            return FingerprintMatch.no_match(raw=payload)

        r = payload["result"]
        apple = r.get("apple_music") or {}
        artwork = (apple.get("artwork") or {}).get("url")
        if artwork:
            artwork = artwork.replace("{w}x{h}", "600x600")

        external: dict[str, str] = {}
        if (r.get("spotify") or {}).get("id"):
            external["spotify"] = r["spotify"]["id"]
        if apple.get("id"):
            external["apple_music"] = apple["id"]

        return FingerprintMatch(
            matched=True,
            title=r.get("title"),
            artist=r.get("artist"),
            album=r.get("album"),
            isrc=r.get("isrc"),
            artwork_url=artwork,
            confidence=0.8,  # AudD returns no numeric score; a hit is fairly confident
            external_ids=external,
            raw=payload,
        )
