"""End-to-end upload → identify → organize, and the manual-tag fallback.

We monkeypatch the fingerprinter inside the pipeline to force each branch
deterministically (the mock's hash-based result can't be predicted from here).
"""

from __future__ import annotations

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
    def _apply(match: FingerprintMatch):
        monkeypatch.setattr(
            "nhac.pipeline.process_clip.get_fingerprinter", lambda: _Stub(match)
        )

    return _apply


def test_upload_identifies_and_organizes(client, sample_video, force_match):
    force_match(
        FingerprintMatch(
            matched=True, title="1901", artist="Phoenix", album="WAP", confidence=0.9
        )
    )
    resp = client.post(
        "/api/clips", files={"file": ("clip.mp4", sample_video, "video/mp4")}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["identified"] is True
    clip = body["clip"]
    assert clip["status"] == "identified"
    assert clip["song"]["title"] == "1901"
    assert clip["concert_id"]  # auto-grouped

    # Detail endpoint resolves a playable media URL.
    detail = client.get(f"/api/clips/{clip['id']}").json()
    assert detail["media_url"]

    # Concert now appears in the library and contains the clip.
    concerts = client.get("/api/concerts").json()
    assert any(c["artist"] == "Phoenix" for c in concerts)
    concert = client.get(f"/api/concerts/{clip['concert_id']}").json()
    assert len(concert["clips"]) >= 1


def test_upload_unidentified_then_manual_tag(client, sample_video, force_match):
    force_match(FingerprintMatch.no_match())
    resp = client.post(
        "/api/clips", files={"file": ("mystery.mp4", sample_video, "video/mp4")}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["identified"] is False
    clip = body["clip"]
    assert clip["status"] == "unidentified"
    assert clip["concert_id"] is None  # ungrouped until tagged

    tagged = client.post(
        f"/api/clips/{clip['id']}/tag",
        json={"artist": "MGMT", "title": "Electric Feel"},
    ).json()
    assert tagged["status"] == "manually_tagged"
    assert tagged["song"]["artist"] == "MGMT"
    assert tagged["concert_id"]  # grouped after tagging


def test_upload_rejects_bad_type(client):
    resp = client.post(
        "/api/clips", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert resp.status_code == 422
