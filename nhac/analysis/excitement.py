"""Excitement detection: find the most hype moments in a concert clip.

Two cheap ffmpeg passes, no ML:

* **Flash signal** — sample luma (``signalstats`` YAVG) at ~8 fps on a tiny
  scaled frame; big frame-to-frame luma jumps = strobes / stage lights /
  pyro / camera pointed at the light show.
* **Loudness signal** — per-0.5s RMS level (``astats``); loud windows =
  drops, choruses, the crowd losing it.

Both series are percentile-normalized per clip (a dim phone video can still
have *relatively* exciting moments), blended, lightly smoothed, and the top
non-overlapping windows are grown into highlight segments.

Everything here is pure computation + subprocess: no DB, no FastAPI. The
``analyze_and_store`` helper at the bottom is the one DB-aware convenience
used by the pipeline.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from nhac.config import settings
from nhac.logging_config import get_logger

log = get_logger(__name__)

# Analysis resolution. 0.5s windows are fine-grained enough to catch a strobe
# burst but coarse enough to keep the series tiny even for long clips.
WINDOW_SECONDS = 0.5
_LUMA_FPS = 8  # luma samples per second (video pass)

# Blend weights: crowds are the truer hype signal; lights confirm it.
_WEIGHT_LOUDNESS = 0.6
_WEIGHT_FLASH = 0.4

# Segment selection defaults.
DEFAULT_SEGMENT_SECONDS = 3.5
DEFAULT_MAX_SEGMENTS = 10
DEFAULT_TARGET_COVERAGE = 0.6  # aim to keep ~60% of the clip in the hype cut
_MIN_SEGMENT_GAP = 0.75  # don't butt two segments right against each other


@dataclass
class Highlight:
    """One exciting segment of a clip (seconds from clip start)."""

    start: float
    end: float
    score: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class AnalysisError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# ffmpeg metadata extraction
# ---------------------------------------------------------------------------

_PTS_RE = re.compile(r"pts_time:(\d+(?:\.\d+)?)")


def _run_metadata_pass(args: list[str]) -> str:
    """Run ffmpeg with a ``metadata=print:file=-`` filter; return stdout."""
    cmd = [settings.ffmpeg_bin, "-hide_banner", "-nostats", "-loglevel", "error", *args]
    log.debug("analysis pass: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AnalysisError(f"ffmpeg analysis pass failed: {proc.stderr[-400:]}")
    return proc.stdout or ""


def _parse_metadata(text: str, key: str) -> list[tuple[float, float]]:
    """Parse ``metadata=print`` output into (pts_time, value) pairs."""
    prefix = f"{key}="
    out: list[tuple[float, float]] = []
    pts: float | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("frame:"):
            m = _PTS_RE.search(line)
            pts = float(m.group(1)) if m else None
        elif pts is not None and line.startswith(prefix):
            raw = line[len(prefix) :]
            try:
                out.append((pts, float(raw)))  # float() handles "-inf" too
            except ValueError:
                continue
    return out


def _luma_series(video_path: Path) -> list[tuple[float, float]]:
    """(time, average-luma) samples at ~_LUMA_FPS on a tiny frame."""
    vf = (
        f"fps={_LUMA_FPS},scale=160:-2,signalstats,"
        "metadata=print:key=lavfi.signalstats.YAVG:file=-"
    )
    text = _run_metadata_pass(["-i", str(video_path), "-vf", vf, "-an", "-f", "null", "-"])
    return _parse_metadata(text, "lavfi.signalstats.YAVG")


def _rms_series(video_path: Path) -> list[tuple[float, float]]:
    """(time, RMS dB) per WINDOW_SECONDS window. Empty if no audio stream."""
    samples_per_window = int(8000 * WINDOW_SECONDS)
    af = (
        f"aresample=8000,asetnsamples=n={samples_per_window},"
        "astats=metadata=1:reset=1,"
        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"
    )
    try:
        text = _run_metadata_pass(
            ["-i", str(video_path), "-af", af, "-vn", "-f", "null", "-"]
        )
    except AnalysisError:
        return []  # e.g. clip without an audio stream — flash-only analysis
    series = _parse_metadata(text, "lavfi.astats.Overall.RMS_level")
    # Clamp silence (-inf) to a sane floor so normalization stays finite.
    return [(t, max(v, -70.0)) for t, v in series]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def _normalize(values: dict[int, float]) -> dict[int, float]:
    """Scale a metric to [0, 1] using p10..p95 (robust to outliers)."""
    if not values:
        return {}
    ordered = sorted(values.values())
    lo, hi = _percentile(ordered, 0.10), _percentile(ordered, 0.95)
    span = hi - lo
    if span <= 1e-9:
        return {k: 0.5 for k in values}  # flat signal → neutral everywhere
    return {k: min(1.0, max(0.0, (v - lo) / span)) for k, v in values.items()}


def compute_window_scores(video_path: Path) -> list[tuple[float, float]]:
    """Score each WINDOW_SECONDS window: [(window_start, score 0..1), ...].

    Runs the two ffmpeg passes and blends flash + loudness. Windows are
    returned in chronological order.
    """
    luma = _luma_series(video_path)
    rms = _rms_series(video_path)
    if not luma and not rms:
        raise AnalysisError("no analyzable video or audio stream")

    # Flash metric per window: mean |Δ luma| between consecutive samples.
    flash_sum: dict[int, float] = {}
    flash_n: dict[int, int] = {}
    for (_t0, v0), (t1, v1) in zip(luma, luma[1:], strict=False):
        w = int(t1 // WINDOW_SECONDS)
        flash_sum[w] = flash_sum.get(w, 0.0) + abs(v1 - v0)
        flash_n[w] = flash_n.get(w, 0) + 1
    flash = {w: flash_sum[w] / flash_n[w] for w in flash_sum}

    # Loudness metric per window: mean RMS dB of samples landing in it.
    loud_sum: dict[int, float] = {}
    loud_n: dict[int, int] = {}
    for t, v in rms:
        w = int(t // WINDOW_SECONDS)
        loud_sum[w] = loud_sum.get(w, 0.0) + v
        loud_n[w] = loud_n.get(w, 0) + 1
    loud = {w: loud_sum[w] / loud_n[w] for w in loud_sum}

    flash_norm = _normalize(flash)
    loud_norm = _normalize(loud)

    windows = sorted(set(flash_norm) | set(loud_norm))
    raw: dict[int, float] = {}
    for w in windows:
        parts: list[tuple[float, float]] = []
        if w in loud_norm:
            parts.append((_WEIGHT_LOUDNESS, loud_norm[w]))
        if w in flash_norm:
            parts.append((_WEIGHT_FLASH, flash_norm[w]))
        total_weight = sum(wt for wt, _ in parts)
        raw[w] = sum(wt * val for wt, val in parts) / total_weight

    # Light smoothing (3-window moving average) so a single noisy window
    # doesn't win over a sustained loud/flashy passage.
    scores: list[tuple[float, float]] = []
    for w in windows:
        neighborhood = [raw[x] for x in (w - 1, w, w + 1) if x in raw]
        scores.append((w * WINDOW_SECONDS, sum(neighborhood) / len(neighborhood)))
    return scores


# ---------------------------------------------------------------------------
# Segment selection
# ---------------------------------------------------------------------------


def select_highlights(
    scores: list[tuple[float, float]],
    clip_duration: float,
    *,
    segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
    max_segments: int = DEFAULT_MAX_SEGMENTS,
    target_coverage: float = DEFAULT_TARGET_COVERAGE,
) -> list[Highlight]:
    """Greedy pick of top-scoring windows grown into non-overlapping segments.

    Returns highlights sorted chronologically (montage order). Short clips
    are returned whole — a 6-second clip IS the highlight.
    """
    if clip_duration <= segment_seconds * 2:
        return [Highlight(0.0, max(clip_duration, 0.1), 1.0)]
    if not scores:
        return [Highlight(0.0, clip_duration, 0.0)]

    target_total = min(clip_duration * target_coverage, clip_duration)
    chosen: list[Highlight] = []
    total = 0.0

    for center_start, score in sorted(scores, key=lambda s: s[1], reverse=True):
        if len(chosen) >= max_segments or total >= target_total:
            break
        center = center_start + WINDOW_SECONDS / 2
        start = max(0.0, center - segment_seconds / 2)
        end = min(clip_duration, start + segment_seconds)
        start = max(0.0, end - segment_seconds)  # re-clamp near the tail

        if any(
            start < h.end + _MIN_SEGMENT_GAP and end > h.start - _MIN_SEGMENT_GAP
            for h in chosen
        ):
            continue
        chosen.append(Highlight(round(start, 3), round(end, 3), round(score, 4)))
        total += end - start

    if not chosen:  # pathological scoring — fall back to the clip itself
        return [Highlight(0.0, clip_duration, 0.0)]
    return sorted(chosen, key=lambda h: h.start)


def analyze_video(video_path: Path, clip_duration: float | None = None) -> list[Highlight]:
    """Full analysis convenience: score windows, then select highlights."""
    scores = compute_window_scores(video_path)
    if clip_duration is None:
        clip_duration = (scores[-1][0] + WINDOW_SECONDS) if scores else 0.0
    return select_highlights(scores, clip_duration)


# ---------------------------------------------------------------------------
# DB glue (used by the pipeline / backfill script)
# ---------------------------------------------------------------------------


def analyze_and_store(session: Session, clip, video_path: Path) -> list[Highlight]:
    """Analyze ``video_path`` and replace ``clip``'s stored highlights.

    Flushes but does not commit — the caller owns the transaction.
    """
    from nhac.models import ClipHighlight

    highlights = analyze_video(video_path, clip.duration_seconds)
    clip.highlights.clear()
    for h in highlights:
        clip.highlights.append(
            ClipHighlight(start_seconds=h.start, end_seconds=h.end, score=h.score)
        )
    session.flush()
    log.info("excitement: %s → %d highlight(s)", clip.id, len(highlights))
    return highlights
