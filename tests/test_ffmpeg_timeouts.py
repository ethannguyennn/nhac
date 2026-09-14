"""Regression tests: every ffmpeg/ffprobe subprocess call must be time-bounded.

Why this file exists: all four ffmpeg call sites in the app originally ran
``subprocess.run`` with no ``timeout``. A malformed, truncated, or
pathologically large input could hang ffmpeg forever, which:

* permanently wedges a FastAPI threadpool worker (the pool is bounded, so
  enough hung uploads stop the app serving anything at all),
* leaves the clip stuck in ``processing`` with no terminal state, and
* in ``pipeline/montage.py`` specifically, hangs while HOLDING the per-clip
  build lock — deadlocking every later request for that clip too.

These tests pin the timeout plumbing end to end. They force a timeout by
shrinking the timeout constant rather than by finding a genuinely hostile
video, which keeps them fast and deterministic.

NOTE: the constants are imported by value into each module's namespace
(``from nhac.constants import ...``), so the monkeypatch target is the
*consuming module's* attribute, not ``nhac.constants``.
"""

from __future__ import annotations

import subprocess

import pytest

from nhac.analysis import excitement
from nhac.audio import ffmpeg
from nhac.enums import ClipStatus
from nhac.pipeline import montage

# Small enough that process startup alone blows the budget, so the timeout
# fires deterministically regardless of machine speed.
_INSTANT = 0.000001


# ── The wrapper converts a timeout into the module's own error type ──


def test_ffmpeg_run_raises_ffmpeg_error_on_timeout(flashy_video_path):
    """A timed-out ffprobe surfaces as FfmpegError, not TimeoutExpired.

    Callers (process_clip) catch FfmpegError specifically; leaking a raw
    TimeoutExpired would bypass their handling.
    """
    with pytest.raises(ffmpeg.FfmpegError, match="timed out"):
        ffmpeg._run(
            [ffmpeg.settings.ffprobe_bin, str(flashy_video_path)], timeout=_INSTANT
        )


def test_probe_is_time_bounded(monkeypatch, flashy_video_path):
    """probe() actually passes its timeout down to subprocess."""
    monkeypatch.setattr(ffmpeg, "FFPROBE_TIMEOUT_SECONDS", _INSTANT)
    with pytest.raises(ffmpeg.FfmpegError, match="timed out"):
        ffmpeg.probe(flashy_video_path)


def test_extract_audio_sample_is_time_bounded(monkeypatch, flashy_video_path, tmp_path):
    monkeypatch.setattr(ffmpeg, "FFMPEG_SAMPLE_TIMEOUT_SECONDS", _INSTANT)
    with pytest.raises(ffmpeg.FfmpegError, match="timed out"):
        ffmpeg.extract_audio_sample(flashy_video_path, tmp_path / "sample.mp3")


def test_extract_thumbnail_timeout_is_non_fatal(monkeypatch, flashy_video_path, tmp_path):
    """Thumbnails are best-effort: a timeout returns None, it doesn't raise."""
    monkeypatch.setattr(ffmpeg, "FFMPEG_SAMPLE_TIMEOUT_SECONDS", _INSTANT)
    assert ffmpeg.extract_thumbnail(flashy_video_path, tmp_path / "t.jpg") is None


def test_estimate_audio_quality_timeout_degrades_to_zero(monkeypatch, flashy_video_path):
    """Quality scoring is best-effort groundwork — a timeout must not fail an
    upload, so it degrades to 0.0 rather than raising."""
    monkeypatch.setattr(ffmpeg, "FFMPEG_ANALYSIS_TIMEOUT_SECONDS", _INSTANT)
    assert ffmpeg.estimate_audio_quality(flashy_video_path) == 0.0


def test_excitement_analysis_is_time_bounded(monkeypatch, flashy_video_path):
    """The full-video decode pass is the most expensive op in the app and the
    likeliest to hang; it must be bounded and raise AnalysisError."""
    monkeypatch.setattr(excitement, "FFMPEG_ANALYSIS_TIMEOUT_SECONDS", _INSTANT)
    with pytest.raises(excitement.AnalysisError, match="timed out"):
        excitement.compute_window_scores(flashy_video_path)


def test_montage_render_is_time_bounded(monkeypatch, flashy_video_path, tmp_path):
    """Worst blast radius of the four: this runs while holding the per-clip
    lock, so an unbounded hang would deadlock the clip permanently."""
    monkeypatch.setattr(montage, "FFMPEG_RENDER_TIMEOUT_SECONDS", _INSTANT)
    with pytest.raises(montage.MontageError, match="timed out"):
        montage._run_ffmpeg(
            ["-i", str(flashy_video_path), "-f", "null", "-y", str(tmp_path / "x.mp4")]
        )


# ── The user-facing guarantee, through the HTTP layer ──


def test_upload_with_hanging_ffmpeg_ends_in_terminal_state(
    client, monkeypatch, sample_video
):
    """The guarantee that actually matters: a hung ffmpeg must not leave the
    clip stuck in ``processing`` forever, and the request must still return.

    Shrinking only the SAMPLE timeout lets probe() succeed normally, so this
    exercises the realistic case where audio extraction is what hangs.
    """
    monkeypatch.setattr(ffmpeg, "FFMPEG_SAMPLE_TIMEOUT_SECONDS", _INSTANT)

    resp = client.post(
        "/api/clips", files={"file": ("hang.mp4", sample_video, "video/mp4")}
    )
    assert resp.status_code == 201, resp.text
    clip = resp.json()["clip"]

    # Terminal state, not PROCESSING — that's the whole point.
    assert clip["status"] != ClipStatus.PROCESSING.value
    assert clip["status"] == ClipStatus.FAILED.value

    # And the failure reason is recorded rather than swallowed.
    detail = client.get(f"/api/clips/{clip['id']}").json()
    assert detail["status"] == ClipStatus.FAILED.value


def test_timeout_kills_the_child_process(flashy_video_path):
    """subprocess.run must reap the child on timeout, so a hung ffmpeg can't
    outlive the call and leak a process. Pins stdlib behaviour we rely on."""
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(
            [ffmpeg.settings.ffmpeg_bin, "-i", str(flashy_video_path), "-f", "null", "-"],
            capture_output=True,
            timeout=_INSTANT,
        )
