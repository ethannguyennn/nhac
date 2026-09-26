"""Fingerprint provider registry.

Selects the adapter from settings so the pipeline stays provider-agnostic.
Default is the offline ``mock`` provider, so the whole app works with no API key.

Network-backed providers are wrapped in ``RetryingFingerprinter`` here rather
than inside each adapter, so retry/backoff policy lives in one place and a new
provider gets it for free. ``mock`` is local and deterministic — retrying it
would only ever repeat the same answer — so it is returned bare.
"""

from __future__ import annotations

from functools import lru_cache

from nhac.config import FingerprintProviderName, settings
from nhac.fingerprint.base import (
    Fingerprinter,
    FingerprintMatch,
    FingerprintUnavailable,
)
from nhac.fingerprint.retry import RetryingFingerprinter


@lru_cache
def get_fingerprinter() -> Fingerprinter:
    provider = settings.fingerprint_provider
    if provider is FingerprintProviderName.AUDD:
        from nhac.fingerprint.audd import AudDFingerprinter

        return RetryingFingerprinter(AudDFingerprinter())
    if provider is FingerprintProviderName.ACOUSTID:
        from nhac.fingerprint.acoustid import AcoustIDFingerprinter

        return RetryingFingerprinter(AcoustIDFingerprinter())
    from nhac.fingerprint.mock import MockFingerprinter

    return MockFingerprinter()


__all__ = [
    "FingerprintMatch",
    "FingerprintUnavailable",
    "Fingerprinter",
    "RetryingFingerprinter",
    "get_fingerprinter",
]
