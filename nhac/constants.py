"""Cross-cutting constants."""

from __future__ import annotations

# Object-storage key prefixes (folders) inside the media bucket / dir.
STORAGE_PREFIX_RAW = "raw"
STORAGE_PREFIX_AUDIO = "audio"
STORAGE_PREFIX_THUMBNAIL = "thumbnails"
STORAGE_PREFIX_EXPORT = "exports"

# Minimum fingerprint confidence (0–1) to auto-accept a match.
MIN_MATCH_CONFIDENCE = 0.5

# Clips recorded within this many minutes are candidates for the same concert.
CONCERT_GROUPING_WINDOW_MINUTES = 6 * 60

# Upload limits (MVP).
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB per clip
ALLOWED_VIDEO_MIME = ("video/mp4", "video/quicktime", "video/webm")
ALLOWED_VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")

# Short sample sent to the fingerprinter (trimming saves cost + skips the intro).
FINGERPRINT_SAMPLE_SECONDS = 15
FINGERPRINT_SAMPLE_START_SECONDS = 5
