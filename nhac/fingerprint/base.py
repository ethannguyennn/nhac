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


class Fingerprinter(ABC):
    name: str = "base"

    @abstractmethod
    def identify(self, audio_path: Path) -> FingerprintMatch:
        """Identify a song from a local audio sample file."""
