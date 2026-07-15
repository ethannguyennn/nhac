"""ffmpeg / ffprobe helpers: probe metadata, extract an audio sample, and a
Phase-2 audio-quality estimate.

Real, working implementations (ffmpeg is a hard dependency of the pipeline).
Kept sync + subprocess-based; the pipeline runs them in a threadpool so they
don't block the event loop.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nhac.config import settings
from nhac.constants import FINGERPRINT_SAMPLE_SECONDS, FINGERPRINT_SAMPLE_START_SECONDS
from nhac.logging_config import get_logger

log = get_logger(__name__)


class FfmpegError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool = False


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    log.debug("run: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FfmpegError(f"{cmd[0]} exited {proc.returncode}: {proc.stderr[-500:]}")
    return proc


def probe(input_path: Path) -> MediaInfo:
    """Read container/stream metadata with ffprobe."""
    cmd = [
        settings.ffprobe_bin,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    proc = _run(cmd)
    data = json.loads(proc.stdout or "{}")

    info = MediaInfo()
    fmt = data.get("format", {})
    if "duration" in fmt:
        try:
            info.duration_seconds = float(fmt["duration"])
        except (TypeError, ValueError):
            pass

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and info.width is None:
            info.width = stream.get("width")
            info.height = stream.get("height")
        if stream.get("codec_type") == "audio":
            info.has_audio = True
    return info


def extract_audio_sample(input_path: Path, output_path: Path) -> Path:
    """Extract a short mono MP3 sample for fingerprinting.

    Starts a few seconds in and grabs ~15s (constants) — cheaper per API call
    and skips the noisy intro.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(FINGERPRINT_SAMPLE_START_SECONDS),
        "-t",
        str(FINGERPRINT_SAMPLE_SECONDS),
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-b:a",
        "128k",
        "-y",
        str(output_path),
    ]
    _run(cmd)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise FfmpegError("audio sample extraction produced no output")
    return output_path


def extract_thumbnail(input_path: Path, output_path: Path, at_seconds: float = 1.0) -> Path | None:
    """Grab a single poster frame. Returns None on failure (non-fatal)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(at_seconds),
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        "-y",
        str(output_path),
    ]
    try:
        _run(cmd)
    except FfmpegError as exc:
        log.warning("thumbnail extraction failed: %s", exc)
        return None
    return output_path if output_path.exists() else None


def estimate_audio_quality(input_path: Path) -> float:
    """Phase-2 heuristic: higher = cleaner (less crowd noise / clipping).

    Uses ffmpeg's ``volumedetect`` for mean/max volume as a first-pass proxy.
    A fuller SNR/high-frequency-energy model comes later (see docs/WORKFLOWS.md).
    Returns a score roughly in [0, 1].
    """
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-i",
        str(input_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr or ""
    mean = _parse_db(stderr, r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB")
    peak = _parse_db(stderr, r"max_volume:\s*(-?\d+(?:\.\d+)?) dB")
    if mean is None:
        return 0.0
    # Louder mean volume + headroom below clipping → cleaner-ish. Normalize.
    # mean typically ranges ~ -40 (quiet/noisy) .. -10 (strong signal) dB.
    loudness = max(0.0, min(1.0, (mean + 40) / 30))
    headroom = 1.0 if peak is None else max(0.0, min(1.0, (-peak) / 6))
    return round(0.7 * loudness + 0.3 * headroom, 4)


def _parse_db(text: str, pattern: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None
