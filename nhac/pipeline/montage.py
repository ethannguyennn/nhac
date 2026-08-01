"""Hype-cut montage rendering.

Given a clip's stored highlights, render a single mp4 where:

* **video** = the highlight segments hard-cut together in chronological order
  (hard cuts read as intentional montage; crossfades read as a slideshow), and
* **audio** = the clip's ORIGINAL audio, continuous — the music keeps playing
  while the visuals jump between the best moments.

If the montage visuals are shorter than the song, they loop until the audio
ends. Output goes to ``exports/hype_<clip>.mp4`` and is cached on
``clip.montage_key`` — building twice is a no-op.

Opens its own DB session (like ``process_clip``) so it can run inside a
threadpool from a request, or from a script. Concurrent requests for the SAME
clip (e.g. a client double-tapping the hype button, or the theater's
background pre-build racing an explicit request) are serialized per-clip so
only one ffmpeg render happens — the rest wait and then get the cached result.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from nhac.analysis.excitement import Highlight, analyze_and_store
from nhac.audio import ffmpeg as ff
from nhac.config import settings
from nhac.constants import STORAGE_PREFIX_EXPORT
from nhac.db import SessionLocal
from nhac.logging_config import get_logger
from nhac.models import Clip
from nhac.storage import get_storage

# Per-clip build locks so concurrent requests don't redundantly re-encode
# (wasteful) or race on writing the same destination file (unsafe on some
# platforms/filesystems). Guarded by _locks_guard since the dict itself is
# shared across threadpool worker threads.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(clip_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(clip_id)
        if lock is None:
            lock = threading.Lock()
            _locks[clip_id] = lock
        return lock

log = get_logger(__name__)

# If a single highlight already covers ~the whole clip (short videos), a
# montage would be identical to the original — reuse the raw key instead of
# burning an encode.
_WHOLE_CLIP_THRESHOLD = 0.95


class MontageError(RuntimeError):
    pass


@dataclass
class MontageResult:
    clip_id: str
    montage_key: str
    built: bool  # False when it already existed / raw was reused


def _run_ffmpeg(args: list[str]) -> None:
    cmd = [settings.ffmpeg_bin, "-hide_banner", "-nostats", "-loglevel", "error", *args]
    log.debug("montage: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MontageError(f"ffmpeg failed: {proc.stderr[-500:]}")


def _render_video_montage(src: Path, highlights: list[Highlight], out: Path) -> None:
    """Concat the highlight segments (video only) into ``out``."""
    parts: list[str] = []
    labels: list[str] = []
    for i, h in enumerate(highlights):
        parts.append(
            f"[0:v]trim=start={h.start:.3f}:end={h.end:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        labels.append(f"[v{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(highlights)}:v=1:a=0[vout]"
    _run_ffmpeg(
        [
            "-i", str(src),
            "-filter_complex", graph,
            "-map", "[vout]",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-y", str(out),
        ]
    )


def _mux_looped_video_with_audio(
    video_only: Path, audio_src: Path, target_duration: float, out: Path
) -> None:
    """Loop the montage visuals under the clip's continuous audio track."""
    info = ff.probe(video_only)
    montage_len = info.duration_seconds or 0.0
    loops = 0
    if montage_len > 0 and montage_len < target_duration:
        loops = math.ceil(target_duration / montage_len) - 1
    _run_ffmpeg(
        [
            "-fflags", "+genpts",
            "-stream_loop", str(loops),
            "-i", str(video_only),
            "-i", str(audio_src),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "160k",
            "-t", f"{target_duration:.3f}",
            "-movflags", "+faststart",
            "-y", str(out),
        ]
    )


def build_montage(clip_id: str, *, force: bool = False) -> MontageResult:
    """Build (or fetch the cached) hype-cut montage for a clip.

    Serialized per-clip: a second caller that arrives while a build is
    already in flight blocks on the lock, then — once it acquires it — sees
    the now-committed ``montage_key`` and takes the cheap cache-hit path
    instead of rendering (or racing) a second time.
    """
    with _lock_for(clip_id):
        return _build_montage_locked(clip_id, force=force)


def _build_montage_locked(clip_id: str, *, force: bool) -> MontageResult:
    session = SessionLocal()
    storage = get_storage()
    tmp_dir = Path(tempfile.mkdtemp(prefix="nhac_montage_"))
    try:
        clip = session.get(Clip, clip_id)
        if clip is None:
            raise MontageError("clip not found")
        if clip.montage_key and not force and storage.exists(clip.montage_key):
            return MontageResult(clip_id, clip.montage_key, built=False)
        if not clip.raw_video_key:
            raise MontageError("clip has no stored video")

        raw_path = storage.open_local_path(clip.raw_video_key)
        info = ff.probe(raw_path)
        duration = clip.duration_seconds or info.duration_seconds or 0.0
        if duration <= 0:
            raise MontageError("clip has no measurable duration")

        # Ensure highlights exist (older clips predate the analyzer).
        highlights = [
            Highlight(h.start_seconds, h.end_seconds, h.score) for h in clip.highlights
        ]
        if not highlights:
            highlights = analyze_and_store(session, clip, raw_path)
            session.commit()

        covered = sum(h.duration for h in highlights)
        if len(highlights) == 1 and covered >= duration * _WHOLE_CLIP_THRESHOLD:
            # The whole clip IS the highlight — montage would be a re-encode.
            clip.montage_key = clip.raw_video_key
            session.commit()
            return MontageResult(clip_id, clip.montage_key, built=False)

        video_only = tmp_dir / "montage_v.mp4"
        _render_video_montage(raw_path, highlights, video_only)

        final = tmp_dir / "hype.mp4"
        if info.has_audio:
            _mux_looped_video_with_audio(video_only, raw_path, duration, final)
        else:
            final = video_only  # nothing to keep playing — visuals only

        key = f"{STORAGE_PREFIX_EXPORT}/hype_{clip.id}.mp4"
        storage.save_file(key, final, content_type="video/mp4")
        clip.montage_key = key
        session.commit()
        log.info(
            "montage: %s → %s (%d segments, %.1fs covered)",
            clip_id, key, len(highlights), covered,
        )
        return MontageResult(clip_id, key, built=True)
    finally:
        session.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)
