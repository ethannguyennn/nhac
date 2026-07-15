"""The core per-clip pipeline.

    raw video (storage)
      → probe metadata (ffprobe)
      → extract short audio sample (ffmpeg)
      → fingerprint (provider)
      → upsert Song + link Clip, log Recognition
      → auto-group into concert + playlist
      → status = identified | unidentified | failed

Runs synchronously and opens its OWN DB session, so the FastAPI route can call
it inside a threadpool without sharing a request-scoped session across threads.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from nhac.audio import ffmpeg
from nhac.constants import (
    MIN_MATCH_CONFIDENCE,
    STORAGE_PREFIX_AUDIO,
    STORAGE_PREFIX_THUMBNAIL,
)
from nhac.db import SessionLocal
from nhac.enums import ClipStatus, MatchSource
from nhac.fingerprint import get_fingerprinter
from nhac.logging_config import get_logger
from nhac.models import Clip, Recognition
from nhac.pipeline.organize import auto_group_into_concert
from nhac.services.songs import upsert_song
from nhac.storage import get_storage

log = get_logger(__name__)


@dataclass
class ProcessResult:
    clip_id: str
    status: ClipStatus
    identified: bool
    song_title: str | None = None
    song_artist: str | None = None
    confidence: float | None = None
    message: str = ""


def process_clip(clip_id: str) -> ProcessResult:
    session = SessionLocal()
    storage = get_storage()
    tmp_dir = Path(tempfile.mkdtemp(prefix="nhac_"))
    try:
        clip = session.get(Clip, clip_id)
        if clip is None:
            return ProcessResult(clip_id, ClipStatus.FAILED, False, message="clip not found")
        if not clip.raw_video_key:
            clip.status = ClipStatus.FAILED
            clip.error_message = "no raw video stored"
            session.commit()
            return ProcessResult(clip_id, ClipStatus.FAILED, False, message="no raw video")

        clip.status = ClipStatus.PROCESSING
        session.commit()

        raw_path = storage.open_local_path(clip.raw_video_key)

        # 1. Probe metadata.
        try:
            info = ffmpeg.probe(raw_path)
            clip.duration_seconds = info.duration_seconds
            clip.width, clip.height = info.width, info.height
        except ffmpeg.FfmpegError as exc:
            log.warning("probe failed for %s: %s", clip_id, exc)
            info = ffmpeg.MediaInfo()

        # 2. Thumbnail (best-effort poster frame).
        thumb_tmp = tmp_dir / "thumb.jpg"
        if ffmpeg.extract_thumbnail(raw_path, thumb_tmp):
            key = f"{STORAGE_PREFIX_THUMBNAIL}/{clip.id}.jpg"
            storage.save_file(key, thumb_tmp, content_type="image/jpeg")
            clip.thumbnail_key = key

        # 3. Extract audio sample.
        if not info.has_audio:
            log.info("clip %s has no audio stream", clip_id)
            clip.status = ClipStatus.UNIDENTIFIED
            session.commit()
            return ProcessResult(
                clip_id, ClipStatus.UNIDENTIFIED, False, message="no audio stream"
            )

        audio_tmp = tmp_dir / "sample.mp3"
        ffmpeg.extract_audio_sample(raw_path, audio_tmp)
        audio_key = f"{STORAGE_PREFIX_AUDIO}/{clip.id}.mp3"
        storage.save_file(audio_key, audio_tmp, content_type="audio/mpeg")
        clip.audio_key = audio_key

        # 4. Best-effort audio quality score (Phase-2 groundwork).
        try:
            clip.audio_quality_score = ffmpeg.estimate_audio_quality(audio_tmp)
        except Exception as exc:  # noqa: BLE001 - non-fatal
            log.debug("quality estimate failed: %s", exc)

        # 5. Fingerprint.
        fingerprinter = get_fingerprinter()
        log.info("fingerprinting %s via %s", clip_id, fingerprinter.name)
        match = fingerprinter.identify(audio_tmp)

        # 6. Log the recognition attempt.
        recognition = Recognition(
            clip_id=clip.id,
            provider=fingerprinter.name,
            confidence=match.confidence,
            raw_response=match.raw,
        )
        session.add(recognition)

        # 7. Decide outcome.
        confident = match.matched and (match.confidence or 0) >= MIN_MATCH_CONFIDENCE
        if confident and match.title and match.artist:
            song = upsert_song(
                session,
                title=match.title,
                artist=match.artist,
                album=match.album,
                artwork_url=match.artwork_url,
                isrc=match.isrc,
                external_ids=match.external_ids,
            )
            recognition.matched_song_id = song.id
            clip.song_id = song.id
            clip.match_source = MatchSource.FINGERPRINT
            clip.match_confidence = match.confidence
            clip.status = ClipStatus.IDENTIFIED
            auto_group_into_concert(session, clip)
            session.commit()
            log.info("identified %s → %s — %s", clip_id, match.artist, match.title)
            return ProcessResult(
                clip_id,
                ClipStatus.IDENTIFIED,
                True,
                song_title=match.title,
                song_artist=match.artist,
                confidence=match.confidence,
                message="identified",
            )

        clip.status = ClipStatus.UNIDENTIFIED
        session.commit()
        log.info("no confident match for %s — awaiting manual tag", clip_id)
        return ProcessResult(
            clip_id, ClipStatus.UNIDENTIFIED, False, message="no confident match"
        )

    except Exception as exc:  # noqa: BLE001 - record failure, don't crash the request
        log.exception("pipeline failed for %s", clip_id)
        session.rollback()
        clip = session.get(Clip, clip_id)
        if clip is not None:
            clip.status = ClipStatus.FAILED
            clip.error_message = str(exc)[:500]
            session.commit()
        return ProcessResult(clip_id, ClipStatus.FAILED, False, message=str(exc))
    finally:
        session.close()
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)
