"""Playlist queue API, theater page, and hype-cut montage rendering."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nhac.fingerprint.base import Fingerprinter, FingerprintMatch


class _Stub(Fingerprinter):
    name = "stub"

    def __init__(self, match: FingerprintMatch):
        self._match = match

    def identify(self, audio_path: Path) -> FingerprintMatch:
        return self._match


@pytest.fixture()
def force_match(monkeypatch):
    def _apply(title: str, artist: str):
        match = FingerprintMatch(
            matched=True, title=title, artist=artist, confidence=0.9
        )
        monkeypatch.setattr(
            "nhac.pipeline.process_clip.get_fingerprinter", lambda: _Stub(match)
        )

    return _apply


def _upload(client, video_bytes: bytes, name: str = "clip.mp4") -> dict:
    resp = client.post("/api/clips", files={"file": (name, video_bytes, "video/mp4")})
    assert resp.status_code == 201, resp.text
    return resp.json()["clip"]


def test_queue_and_theater_page(client, sample_video, force_match):
    force_match("Lisztomania", "Phoenix")
    clip_a = _upload(client, sample_video, "a.mp4")
    force_match("1901", "Phoenix")
    clip_b = _upload(client, sample_video, "b.mp4")

    # Same artist, same day → same concert.
    concert_id = clip_a["concert_id"]
    assert concert_id and clip_b["concert_id"] == concert_id

    playlists = client.get("/api/playlists").json()
    playlist = next(p for p in playlists if p["concert_id"] == concert_id)
    assert playlist["clip_count"] >= 2

    queue = client.get(f"/api/playlists/{playlist['id']}/queue").json()
    ids = {item["clip_id"] for item in queue["items"]}
    assert {clip_a["id"], clip_b["id"]} <= ids
    for item in queue["items"]:
        assert item["media_url"].startswith("/media/")
        assert item["title"]

    # Theater page renders with the embedded queue + player bootstrap.
    page = client.get(f"/play/{playlist['id']}")
    assert page.status_code == 200
    assert "NhacPlayer.init" in page.text
    assert "queue-data" in page.text
    # Custom <video> has no native `controls`, so the buffering spinner is
    # the only stall feedback the user gets — must always be present.
    assert 'id="buffering"' in page.text

    # Concert convenience route drops you into the same theater.
    resp = client.get(f"/concerts/{concert_id}/play")
    assert resp.status_code == 200
    assert f"/play/{playlist['id']}" in str(resp.url)


def test_queue_exposes_highlights_for_progress_bar_marks(client, flashy_video, force_match):
    """The theater's progress-bar tick marks read queue item `highlights`."""
    force_match("Somebody Else", "The 1975")
    clip = _upload(client, flashy_video, "highlights.mp4")

    playlists = client.get("/api/playlists").json()
    playlist = next(p for p in playlists if p["concert_id"] == clip["concert_id"])
    queue = client.get(f"/api/playlists/{playlist['id']}/queue").json()
    item = next(i for i in queue["items"] if i["clip_id"] == clip["id"])

    assert item["highlights"], "expected at least one highlight segment"
    duration = item["duration_seconds"]
    prev_end = -1.0
    for h in item["highlights"]:
        assert 0.0 <= h["start_seconds"] < h["end_seconds"] <= duration + 0.05
        assert h["start_seconds"] >= prev_end  # chronological, non-overlapping
        assert 0.0 <= h["score"] <= 1.0
        prev_end = h["end_seconds"]

    # And the theater page actually embeds them for player.js to render.
    page = client.get(f"/play/{playlist['id']}")
    assert '"highlights"' in page.text


def test_concert_page_links_theater(client, sample_video, force_match):
    force_match("Electric Feel", "MGMT")
    clip = _upload(client, sample_video)
    page = client.get(f"/concerts/{clip['concert_id']}")
    assert page.status_code == 200
    assert "Play all" in page.text
    assert "/play/" in page.text


def test_montage_short_clip_reuses_original(client, sample_video, force_match):
    """A 3s clip IS the highlight — no re-encode, montage == raw video."""
    force_match("Coffee", "Beabadoobee")
    clip = _upload(client, sample_video)
    resp = client.post(f"/api/clips/{clip['id']}/montage")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["built"] is False
    detail = client.get(f"/api/clips/{clip['id']}").json()
    assert data["montage_url"] == detail["media_url"]


def test_montage_renders_for_flashy_clip(client, flashy_video, force_match):
    """A 9s clip with a hype middle gets a real cut-down montage render."""
    from nhac.audio import ffmpeg
    from nhac.storage import get_storage

    force_match("Redbone", "Childish Gambino")
    clip = _upload(client, flashy_video, "flashy.mp4")

    resp = client.post(f"/api/clips/{clip['id']}/montage")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["built"] is True
    assert "exports/hype_" in data["montage_url"]

    # The rendered file exists, has audio, and spans (about) the full song.
    key = data["montage_url"].split("/media/", 1)[1]
    path = get_storage().open_local_path(key)
    info = ffmpeg.probe(path)
    assert info.has_audio
    assert (info.duration_seconds or 0) > 5

    # Second request is a cache hit, not a rebuild.
    again = client.post(f"/api/clips/{clip['id']}/montage").json()
    assert again["built"] is False
    assert again["montage_url"] == data["montage_url"]

    # The queue now advertises the montage for the theater's hype mode.
    playlists = client.get("/api/playlists").json()
    playlist = next(p for p in playlists if p["concert_id"] == clip["concert_id"])
    queue = client.get(f"/api/playlists/{playlist['id']}/queue").json()
    item = next(i for i in queue["items"] if i["clip_id"] == clip["id"])
    assert item["montage_url"] == data["montage_url"]


def test_concurrent_montage_requests_dont_race(client, flashy_video, force_match):
    """Regression test.

    Firing several simultaneous montage builds for the SAME clip used to
    intermittently 500 on Windows: LocalStorage._path's safety check called
    Path.resolve() on the target, which raced with a sibling thread's
    mkdir() of the same not-yet-existing `exports/` directory and could
    transiently (and incorrectly) reject a perfectly safe key. Fixed by
    making the safety check pure-lexical (no filesystem I/O) and by
    serializing concurrent builds per-clip so only one ffmpeg render happens.
    """
    force_match("1901", "Phoenix")
    clip = _upload(client, flashy_video, "concurrent.mp4")

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [
            pool.submit(client.post, f"/api/clips/{clip['id']}/montage")
            for _ in range(5)
        ]
        responses = [f.result() for f in futures]

    for resp in responses:
        assert resp.status_code == 200, resp.text

    bodies = [r.json() for r in responses]
    montage_urls = {b["montage_url"] for b in bodies}
    assert len(montage_urls) == 1, "all concurrent callers must agree on one montage"
    # Exactly one caller should have actually rendered it; the rest joined
    # the in-flight build or hit the cache.
    assert sum(1 for b in bodies if b["built"]) == 1
