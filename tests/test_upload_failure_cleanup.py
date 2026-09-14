"""Regression tests: a pipeline crash must leave nothing half-finished.

Why this file exists: ``process_clip`` writes two DERIVED objects to storage
(``thumbnails/<id>.jpg``, then ``audio/<id>.mp3``) and records their keys on
the in-memory ``Clip``, but those keys are only persisted by a LATER
``session.commit()``. The failure handler calls ``session.rollback()``, so a
crash anywhere after a write — ffmpeg dying, disk full, a DB error while
upserting the song — discarded the key while the file stayed on disk.

The result was a true orphan: bytes in the bucket that no row references, that
no code path will ever read, delete, or even name. Nothing logged them either,
so a sweep job had nothing to sweep on. Every failed upload leaked.

Two guarantees are pinned here:

1. The clip reaches a TERMINAL state (``failed``) with the reason recorded —
   never stuck in ``processing``.
2. Storage matches the DB afterwards: derived objects this run wrote but the
   committed row does not reference are deleted, and anything that could not
   be deleted is logged by key so it can be swept later.

Crashes are injected at ``upsert_song`` / ``extract_audio_sample`` rather than
at the fingerprint provider on purpose: provider errors are slated to become a
soft ``unidentified`` fallback (TODO §1.2), which would silently defang these
tests. These two injection points stay genuinely fatal.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from nhac.audio import ffmpeg
from nhac.config import settings
from nhac.constants import (
    STORAGE_PREFIX_AUDIO,
    STORAGE_PREFIX_RAW,
    STORAGE_PREFIX_THUMBNAIL,
)
from nhac.db import SessionLocal
from nhac.enums import ClipStatus
from nhac.fingerprint.base import Fingerprinter, FingerprintMatch
from nhac.models import Clip
from nhac.storage import get_storage


class _Stub(Fingerprinter):
    name = "stub"

    def identify(self, audio_path: Path) -> FingerprintMatch:
        return FingerprintMatch(
            matched=True, title="1901", artist="Phoenix", confidence=0.9
        )


@pytest.fixture()
def stub_match(monkeypatch):
    """Force a confident match so the pipeline reaches the post-fingerprint
    stage where the DB-side crash is injected."""
    monkeypatch.setattr(
        "nhac.pipeline.process_clip.get_fingerprinter", lambda: _Stub()
    )


def _upload(client, sample_video, name="clip.mp4"):
    resp = client.post("/api/clips", files={"file": (name, sample_video, "video/mp4")})
    assert resp.status_code == 201, resp.text
    return resp.json()["clip"]


def _derived_keys(clip_id: str) -> tuple[str, str]:
    return (
        f"{STORAGE_PREFIX_THUMBNAIL}/{clip_id}.jpg",
        f"{STORAGE_PREFIX_AUDIO}/{clip_id}.mp3",
    )


def _db_clip(clip_id: str) -> Clip:
    with SessionLocal() as session:
        clip = session.get(Clip, clip_id)
        assert clip is not None
        session.expunge(clip)
        return clip


# ── Guarantee 1: terminal state, reason recorded ──


def test_crash_mid_pipeline_ends_in_failed_not_processing(
    client, sample_video, stub_match, monkeypatch
):
    """The stuck-forever case. A crash after fingerprinting must still commit a
    terminal status — ``processing`` means the UI spins for eternity."""
    monkeypatch.setattr(
        "nhac.pipeline.process_clip.upsert_song",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("disk full")),
    )

    clip = _upload(client, sample_video)
    assert clip["status"] == ClipStatus.FAILED.value

    row = _db_clip(clip["id"])
    assert row.status is ClipStatus.FAILED
    assert row.error_message and "disk full" in row.error_message


# ── Guarantee 2: no orphaned storage objects ──


def test_crash_after_both_artifacts_leaves_no_orphans(
    client, sample_video, stub_match, monkeypatch
):
    """Crash at the latest point: thumbnail AND audio sample are already on
    disk, and the rollback throws both keys away. Both files must go too."""
    monkeypatch.setattr(
        "nhac.pipeline.process_clip.upsert_song",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    clip = _upload(client, sample_video)
    thumb_key, audio_key = _derived_keys(clip["id"])
    storage = get_storage()

    row = _db_clip(clip["id"])
    assert row.thumbnail_key is None and row.audio_key is None  # rolled back
    assert not storage.exists(thumb_key), "orphaned thumbnail left in storage"
    assert not storage.exists(audio_key), "orphaned audio sample left in storage"


def test_crash_after_thumbnail_only_removes_the_thumbnail(
    client, sample_video, monkeypatch
):
    """Earlier crash: only the thumbnail exists yet. Cleanup must handle a
    partial set of writes, not assume both artifacts are present."""

    def _boom(*a, **kw):
        raise ffmpeg.FfmpegError("ffmpeg died")

    monkeypatch.setattr(ffmpeg, "extract_audio_sample", _boom)

    clip = _upload(client, sample_video)
    thumb_key, audio_key = _derived_keys(clip["id"])
    storage = get_storage()

    assert clip["status"] == ClipStatus.FAILED.value
    assert not storage.exists(thumb_key), "orphaned thumbnail left in storage"
    assert not storage.exists(audio_key)


def test_failure_keeps_the_raw_upload(client, sample_video, stub_match, monkeypatch):
    """The raw video is NOT a derived artifact — it's the user's footage, it's
    referenced by the committed row, and it's what any retry would re-read.
    Cleanup must never touch it."""
    monkeypatch.setattr(
        "nhac.pipeline.process_clip.upsert_song",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    clip = _upload(client, sample_video)
    row = _db_clip(clip["id"])

    assert row.raw_video_key == f"{STORAGE_PREFIX_RAW}/{clip['id']}.mp4"
    assert get_storage().exists(row.raw_video_key)


def test_undeletable_orphan_is_logged_by_key(
    client, sample_video, stub_match, monkeypatch, caplog
):
    """If the delete itself fails (locked file on Windows, S3 outage) the key
    must be logged so a sweep job can find it later — and the original failure
    must still be what the clip records, not the cleanup error."""
    monkeypatch.setattr(
        "nhac.pipeline.process_clip.upsert_song",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("original boom")),
    )

    storage = get_storage()

    def _refuse(key):
        raise OSError("file is locked")

    monkeypatch.setattr(storage, "delete", _refuse)

    with caplog.at_level(logging.WARNING):
        clip = _upload(client, sample_video)

    thumb_key, audio_key = _derived_keys(clip["id"])
    assert clip["status"] == ClipStatus.FAILED.value

    row = _db_clip(clip["id"])
    assert "original boom" in (row.error_message or ""), "cleanup error masked the cause"

    logged = caplog.text
    assert thumb_key in logged and audio_key in logged


# ── The other half: cleanup must not over-delete on success ──


def test_successful_upload_keeps_its_artifacts(client, sample_video, stub_match):
    """Guard against an over-eager cleanup: the happy path must still have a
    thumbnail and an audio sample, both referenced and both on disk."""
    clip = _upload(client, sample_video)
    assert clip["status"] == ClipStatus.IDENTIFIED.value

    row = _db_clip(clip["id"])
    storage = get_storage()
    assert row.thumbnail_key and storage.exists(row.thumbnail_key)
    assert row.audio_key and storage.exists(row.audio_key)


def test_clip_without_audio_stream_keeps_its_thumbnail(client, tmp_path):
    """A video-only clip ends UNIDENTIFIED — a non-crash early return that
    COMMITS. Its thumbnail is referenced and must survive."""
    from tests.conftest import _make_video

    path = _make_video(tmp_path / "silent.mp4")
    silent = tmp_path / "muted.mp4"
    subprocess.run(
        [settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error",
         "-i", str(path), "-an", "-c:v", "copy", "-y", str(silent)],
        check=True, capture_output=True,
    )

    clip = _upload(client, silent.read_bytes(), name="silent.mp4")
    assert clip["status"] == ClipStatus.UNIDENTIFIED.value

    row = _db_clip(clip["id"])
    assert row.thumbnail_key and get_storage().exists(row.thumbnail_key)
