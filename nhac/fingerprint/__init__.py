"""Fingerprint provider registry.

Selects the adapter from settings so the pipeline stays provider-agnostic.
Default is the offline ``mock`` provider, so the whole app works with no API key.
"""

from __future__ import annotations

from functools import lru_cache

from nhac.config import FingerprintProviderName, settings
from nhac.fingerprint.base import Fingerprinter, FingerprintMatch


@lru_cache
def get_fingerprinter() -> Fingerprinter:
    provider = settings.fingerprint_provider
    if provider is FingerprintProviderName.AUDD:
        from nhac.fingerprint.audd import AudDFingerprinter

        return AudDFingerprinter()
    if provider is FingerprintProviderName.ACOUSTID:
        from nhac.fingerprint.acoustid import AcoustIDFingerprinter

        return AcoustIDFingerprinter()
    from nhac.fingerprint.mock import MockFingerprinter

    return MockFingerprinter()


__all__ = ["Fingerprinter", "FingerprintMatch", "get_fingerprinter"]
