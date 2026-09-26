"""Fingerprinter interface + normalized result type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FingerprintMatch:
    """Provider-independent recognition result."""

    matched: bool
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    isrc: str | None = None
    artwork_url: str | None = None
    confidence: float | None = None  # 0–1, normalized
    external_ids: dict[str, str] = field(default_factory=dict)
    raw: dict | None = None  # provider payload, stored for audit/debug

    @classmethod
    def no_match(cls, raw: dict | None = None) -> FingerprintMatch:
        return cls(matched=False, raw=raw)


class FingerprintUnavailable(RuntimeError):
    """The provider could not be asked, so the song is still unknown.

    Deliberately NOT the same thing as ``FingerprintMatch.no_match()``: a
    no-match is an answer ("we listened, we don't know this one"), while this
    is the absence of an answer (timeout, 5xx, rate limit, bad API key,
    missing ``fpcalc`` binary). The clip itself is fine, so callers degrade to
    the manual-tag path instead of failing it — see
    ``pipeline/process_clip.py``.

    ``transient`` says whether a later retry has any chance: a 503 yes, a 401
    not until someone fixes the key. It is recorded on the dead-letter
    ``Recognition`` row so a sweep job can tell "retry this" from "page the
    owner".
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        attempts: int = 1,
        transient: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.attempts = attempts
        self.transient = transient


class Fingerprinter(ABC):
    name: str = "base"

    @abstractmethod
    def identify(self, audio_path: Path) -> FingerprintMatch:
        """Identify a song from a local audio sample file."""
