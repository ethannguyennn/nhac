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

# Fingerprint provider network behavior.
#
# `audd` and `acoustid` are HTTP calls to someone else's server, so they fail
# in ways the clip is not responsible for: a timeout, a 502 from a proxy, a
# rate-limit burst. Those get a bounded retry with exponential backoff; when
# the budget runs out the clip degrades to the manual-tag path rather than
# failing (see pipeline/process_clip.py).
#
# The retry happens INLINE in the upload request, so the worst-case added
# latency (sum of the backoffs below) must stay small enough that a user
# holding a phone doesn't give up: 0.5s + 1.0s = 1.5s at the default budget.
FINGERPRINT_HTTP_TIMEOUT_SECONDS = 30.0
FINGERPRINT_MAX_ATTEMPTS = 3
FINGERPRINT_RETRY_BASE_DELAY_SECONDS = 0.5
FINGERPRINT_RETRY_MAX_DELAY_SECONDS = 4.0

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
