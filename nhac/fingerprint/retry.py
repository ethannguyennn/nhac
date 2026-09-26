"""Bounded retry + error classification around a fingerprint provider.

``audd`` and ``acoustid`` are network calls, and network calls fail for
reasons that have nothing to do with the clip: a dropped connection, a 502
from someone's load balancer, a burst over the rate limit. Left unhandled,
one of those blips propagated out of ``identify()`` and through
``process_clip``'s catch-all handler, which marked the clip ``failed`` AND
(because that path rolls back) deleted its thumbnail and audio sample as
orphans. A user lost a perfectly good clip to a hiccup on someone else's
server, and never even got offered the manual-tag fallback.

This wrapper sits between the pipeline and the provider and does two things:

* **retries what's worth retrying** — timeouts, connection errors, 5xx, 429 —
  with exponential backoff, and
* **normalizes everything it can't fix into ``FingerprintUnavailable``**,
  tagged with the attempt count and whether a later retry could plausibly
  work, so the caller has exactly one exception type to degrade on and the
  dead-letter row has something to sweep on.

A clean "no match" is an answer, not a failure: it returns immediately and is
never retried (retrying would just burn paid API calls to be told the same
thing).

No jitter: this runs inline in one user's upload on a single-user app, so
there is no thundering herd to spread out, and deterministic delays keep the
tests honest. Add jitter here if this ever moves behind a queue with many
workers.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx

from nhac.constants import (
    FINGERPRINT_MAX_ATTEMPTS,
    FINGERPRINT_RETRY_BASE_DELAY_SECONDS,
    FINGERPRINT_RETRY_MAX_DELAY_SECONDS,
)
from nhac.fingerprint.base import (
    Fingerprinter,
    FingerprintMatch,
    FingerprintUnavailable,
)
from nhac.logging_config import get_logger

log = get_logger(__name__)

# Retry-worthy HTTP statuses: 429 (slow down) plus anything 5xx (their side).
_RETRYABLE_STATUSES = frozenset({429})


def is_transient(exc: BaseException) -> bool:
    """Would waiting and asking again plausibly produce a different answer?"""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status in _RETRYABLE_STATUSES
    if isinstance(exc, httpx.TransportError):
        # Covers timeouts, connect/read/write/pool errors and DNS failures.
        return True
    if isinstance(exc, FingerprintUnavailable):
        return exc.transient
    # Anything else (a 4xx, a malformed payload, a missing fpcalc binary) is a
    # bug or a misconfiguration; hammering it just wastes the upload's time.
    return False


def _describe(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} from {exc.request.url}"
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class RetryingFingerprinter(Fingerprinter):
    """Wraps a provider with bounded retries; raises ``FingerprintUnavailable``."""

    def __init__(
        self,
        inner: Fingerprinter,
        *,
        max_attempts: int = FINGERPRINT_MAX_ATTEMPTS,
        base_delay: float = FINGERPRINT_RETRY_BASE_DELAY_SECONDS,
        max_delay: float = FINGERPRINT_RETRY_MAX_DELAY_SECONDS,
    ) -> None:
        self._inner = inner
        self._max_attempts = max(1, max_attempts)
        self._base_delay = base_delay
        self._max_delay = max_delay
        self.name = inner.name  # stay transparent: recognitions record the real provider

    @property
    def inner(self) -> Fingerprinter:
        return self._inner

    def _delay_for(self, attempt: int) -> float:
        """Exponential backoff for the wait AFTER ``attempt`` (1-based)."""
        return min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)

    def identify(self, audio_path: Path) -> FingerprintMatch:
        last: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._inner.identify(audio_path)
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                last = exc
                transient = is_transient(exc)
                if not transient or attempt == self._max_attempts:
                    raise FingerprintUnavailable(
                        f"{self.name} unavailable after {attempt} attempt(s) "
                        f"({_describe(exc)})",
                        provider=self.name,
                        attempts=attempt,
                        transient=transient,
                    ) from exc
                delay = self._delay_for(attempt)
                log.warning(
                    "fingerprint attempt %d/%d failed (%s); retrying in %.2fs",
                    attempt, self._max_attempts, _describe(exc), delay,
                )
                time.sleep(delay)
        raise AssertionError(f"unreachable: loop exhausted without raising ({last!r})")
