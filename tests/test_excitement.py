"""Excitement analysis: pure selection logic + real ffmpeg integration."""

from __future__ import annotations

from nhac.analysis.excitement import analyze_video, select_highlights


def test_short_clip_is_its_own_highlight():
    highlights = select_highlights([], clip_duration=5.0)
    assert len(highlights) == 1
    assert highlights[0].start == 0.0
    assert highlights[0].end == 5.0


def test_selection_picks_peaks_in_chronological_order():
    # 20s clip in 0.5s windows: strong peak around t=5–6.5, weaker at t=15.
    scores = []
    for w in range(40):
        s = 0.1
        if w in (10, 11, 12):
            s = 1.0
        if w == 30:
            s = 0.8
        scores.append((w * 0.5, s))

    highlights = select_highlights(
        scores, 20.0, segment_seconds=3.0, max_segments=2, target_coverage=0.3
    )
    assert len(highlights) == 2
    # Chronological order and no overlap.
    assert highlights[0].start < highlights[1].start
    assert highlights[0].end <= highlights[1].start
    # Both peaks are covered.
    assert any(h.start <= 5.5 <= h.end for h in highlights)
    assert any(h.start <= 15.25 <= h.end for h in highlights)


def test_selection_respects_max_segments():
    scores = [(w * 0.5, (w % 7) / 7) for w in range(120)]  # 60s of noisy scores
    highlights = select_highlights(scores, 60.0, max_segments=4, target_coverage=0.9)
    assert 1 <= len(highlights) <= 4


def test_flashy_loud_section_wins(flashy_video_path):
    """End-to-end: the analyzer must find the loud+strobing middle third."""
    highlights = analyze_video(flashy_video_path, clip_duration=9.0)
    assert highlights, "expected at least one highlight"
    best = max(highlights, key=lambda h: h.score)
    center = (best.start + best.end) / 2
    # The exciting section runs 3s–6s; allow generous margins for windowing.
    assert 2.0 <= center <= 7.0, f"best highlight centered at {center:.2f}s"
