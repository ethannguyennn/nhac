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

# ffmpeg/ffprobe subprocess timeouts (seconds).
#
# Without these, a malformed, truncated, or pathologically large input can hang
# ffmpeg forever, which permanently wedges a threadpool worker — and in
# montage.py the hang happens while holding the per-clip build lock, so every
# later request for that clip deadlocks too.
#
# Values are deliberately GENEROUS: the goal is to make a hang finite, not to
# enforce a tight SLA. A legitimate 500 MB (MAX_UPLOAD_BYTES) upload should
# never hit these on any machine that can run the pipeline at all.
FFPROBE_TIMEOUT_SECONDS = 60  # header/metadata read only
FFMPEG_SAMPLE_TIMEOUT_SECONDS = 120  # short trim → thumbnail / audio sample
FFMPEG_ANALYSIS_TIMEOUT_SECONDS = 600  # full-video decode pass (excitement)
FFMPEG_RENDER_TIMEOUT_SECONDS = 900  # montage encode + mux
