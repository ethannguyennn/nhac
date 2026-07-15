"""Canonical status/enum values shared across the DB, services, and API."""

from __future__ import annotations

from enum import Enum


class ClipStatus(str, Enum):
    """Lifecycle of an uploaded clip as it moves through the pipeline."""

    UPLOADING = "uploading"  # row created, file not yet stored
    PROCESSING = "processing"  # stored, queued for extraction + fingerprinting
    IDENTIFIED = "identified"  # confident fingerprint match
    UNIDENTIFIED = "unidentified"  # ran but no confident match → manual tag
    MANUALLY_TAGGED = "manually_tagged"  # user supplied the song
    FAILED = "failed"  # extraction/transcode/provider error


class MatchSource(str, Enum):
    FINGERPRINT = "fingerprint"
    MANUAL = "manual"
    INHERITED = "inherited"  # copied from another clip in the same song group


class ConcertRole(str, Enum):
    OWNER = "owner"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


class PlaylistType(str, Enum):
    CONCERT = "concert"  # auto: all clips from one concert
    GREATEST_HITS = "greatest_hits"  # auto: favorites across concerts
    CUSTOM = "custom"  # user-curated
