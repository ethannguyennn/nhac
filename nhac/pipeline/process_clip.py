"""The core per-clip pipeline.

    raw video (storage)
      → probe metadata (ffprobe)
      → extract short audio sample (ffmpeg)
      → fingerprint (provider; unreachable ⇒ unidentified, not failed)
      → upsert Song + link Clip, log Recognition
      → auto-group into concert + playlist
      → status = identified | unidentified | failed

Runs synchronously and opens its OWN DB session, so the FastAPI route can call
it inside a threadpool without sharing a request-scoped session across threads.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nhac.analysis.excitement import analyze_and_store
from nhac.audio import ffmpeg
from nhac.constants import (
    MIN_MATCH_CONFIDENCE,
    STORAGE_PREFIX_AUDIO,
    STORAGE_PREFIX_THUMBNAIL,
)
from nhac.db import SessionLocal
from nhac.enums import ClipStatus, MatchSource
from nhac.fingerprint import get_fingerprinter
from nhac.fingerprint.base import Fingerprinter, FingerprintUnavailable
from nhac.logging_config import get_logger
from nhac.models import Clip, Recognition
from nhac.pipeline.organize import auto_group_into_concert
from nhac.services.songs import upsert_song
from nhac.storage import get_storage

log = get_logger(__name__)


def _discard_unreferenced(storage, keys: list[str], clip: Clip | None) -> None:
    """Delete derived artifacts this run wrote that the clip row doesn't point at.

    The failure path rolls the session back, which throws away the in-memory
    ``thumbnail_key``/``audio_key`` assignments while their files stay in
    storage — leaving orphans that no row references and nothing would ever
    reclaim. Call this only AFTER the terminal state is committed, so ``clip``
    reflects what
    actually persisted and a key that did survive the rollback is kept.

    Deletion is best-effort by design: a key we can't remove is logged (at
    WARNING, with the key) so a sweep job has something to work from, and the
    original pipeline failure stays the reason recorded on the clip.
    """
    referenced = set()
    if clip is not None:
        referenced = {
            clip.raw_video_key,
            clip.audio_key,
            clip.thumbnail_key,
            clip.montage_key,
        }
    for key in keys:
        if key in referenced:
            continue
        try:
            storage.delete(key)
            log.info("discarded orphaned storage object %s", key)
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask the cause
            log.warning("orphaned storage object left behind: %s (%s)", key, exc)


def _record_provider_failure(
    session, clip: Clip, fingerprinter: Fingerprinter, exc: Exception
) -> ProcessResult:
    """Degrade an unreachable provider to the manual-tag path.

    A provider error says nothing about the clip: the footage is fine, the
    audio sample is fine, we just couldn't ask anyone what the song is. The
    honest terminal state is therefore ``unidentified`` (the same state a
    genuine miss produces), which routes the uploader to
    ``/clips/<id>/tag`` — not ``failed``, which is a dead end offering them
    nothing.

    This COMMITS rather than rolling back, which also keeps the derived
    artifacts: the thumbnail and audio sample stay referenced by the row, so
    the tag page has a poster frame and a later retry has a sample to re-send
    without re-running ffmpeg.

    The attempt is kept as a dead-letter ``Recognition`` row (``error`` set)
    so an outage is a queryable backlog rather than a silent pile of
    "unidentified" clips indistinguishable from real misses.
    """
    if isinstance(exc, FingerprintUnavailable):
        transient, attempts = exc.transient, exc.attempts
    else:
        # An adapter that raised something the retry wrapper never saw (a bare
        # provider, or a bug in one). Assume retryable: a false "retry me" only
        # costs one later API call, a false "give up" loses the clip's identity.
        transient, attempts = True, 1
    reason = f"{type(exc).__name__}: {exc}"

    session.add(
        Recognition(
            clip_id=clip.id,
            provider=fingerprinter.name,
            confidence=None,
            error=reason[:500],
            raw_response={
                "error": reason,
                "error_type": type(exc).__name__,
                "attempts": attempts,
                "transient": transient,
                "failed_at": datetime.now(UTC).isoformat(),
            },
        )
    )
    clip.status = ClipStatus.UNIDENTIFIED
    clip.error_message = reason[:500]
    session.commit()
    log.warning(
        "fingerprint provider %s unavailable for %s after %d attempt(s) "
        "(transient=%s); falling back to manual tagging: %s",
        fingerprinter.name, clip.id, attempts, transient, exc,
    )
    return ProcessResult(
        clip.id,
        ClipStatus.UNIDENTIFIED,
        False,
        message="song service unavailable - tag it manually",
    )


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
    # Derived objects written to storage during this run. Their keys only reach
    # the DB on a later commit, so on failure these are what leaks.
    derived_keys: list[str] = []
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
            derived_keys.append(key)
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
        derived_keys.append(audio_key)
        clip.audio_key = audio_key

        # 4. Best-effort audio quality score (Phase-2 groundwork).
        try:
            clip.audio_quality_score = ffmpeg.estimate_audio_quality(audio_tmp)
        except Exception as exc:  # noqa: BLE001 - non-fatal
            log.debug("quality estimate failed: %s", exc)

        # 4.5 Excitement analysis → highlights (powers the hype-cut montage
        # and "jump to the good part"). Non-fatal: a clip without highlights
        # still identifies and plays normally.
        try:
            analyze_and_store(session, clip, raw_path)
        except Exception as exc:  # noqa: BLE001 - non-fatal
            log.warning("excitement analysis failed for %s: %s", clip_id, exc)

        # 5. Fingerprint. A provider that can't be reached is NOT a clip
        # failure — see _record_provider_failure. The catch is deliberately
        # broad: every exception out of a third-party adapter (network,
        # malformed payload, missing fpcalc binary, bad key) is a problem with
        # the provider, not with this clip, and none of them should cost the
        # user their upload.
        fingerprinter = get_fingerprinter()
        log.info("fingerprinting %s via %s", clip_id, fingerprinter.name)
        try:
            match = fingerprinter.identify(audio_tmp)
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the clip
            return _record_provider_failure(session, clip, fingerprinter, exc)

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
        _discard_unreferenced(storage, derived_keys, clip)
        return ProcessResult(clip_id, ClipStatus.FAILED, False, message=str(exc))
    finally:
        session.close()
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def retry_fingerprint(clip_id: str) -> ProcessResult:
    """Re-run ONLY identification for a clip a provider outage left untagged.

    Cheap on purpose: it re-sends the audio sample already in storage, so it
    skips probe, thumbnail, and the (expensive) full-video excitement pass
    that ``process_clip`` would redo. That sample survives a provider failure
    precisely because ``_record_provider_failure`` commits instead of rolling
    back.

    Refuses clips a user has already tagged or that identified some other way
    — re-fingerprinting those could silently overwrite a human's answer with a
    machine's. Clips whose sample is missing fall back to the full pipeline.
    """
    session = SessionLocal()
    try:
        clip = session.get(Clip, clip_id)
        if clip is None:
            return ProcessResult(clip_id, ClipStatus.FAILED, False, message="clip not found")
        if clip.status is not ClipStatus.UNIDENTIFIED:
            return ProcessResult(
                clip_id, clip.status, clip.song_id is not None, message="not awaiting a retry"
            )
        if not clip.audio_key:
            return process_clip(clip_id)  # no sample to re-send; redo the lot

        storage = get_storage()
        if not storage.exists(clip.audio_key):
            return process_clip(clip_id)

        audio_path = storage.open_local_path(clip.audio_key)
        fingerprinter = get_fingerprinter()
        log.info("retrying fingerprint for %s via %s", clip_id, fingerprinter.name)
        try:
            match = fingerprinter.identify(audio_path)
        except Exception as exc:  # noqa: BLE001 - same degradation as the pipeline
            return _record_provider_failure(session, clip, fingerprinter, exc)

        recognition = Recognition(
            clip_id=clip.id,
            provider=fingerprinter.name,
            confidence=match.confidence,
            raw_response=match.raw,
        )
        session.add(recognition)

        confident = match.matched and (match.confidence or 0) >= MIN_MATCH_CONFIDENCE
        if not (confident and match.title and match.artist):
            # The provider answered this time; a miss is now a real miss, so
            # clear the outage breadcrumb and leave it to manual tagging.
            clip.error_message = None
            session.commit()
            return ProcessResult(
                clip_id, ClipStatus.UNIDENTIFIED, False, message="no confident match"
            )

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
        clip.error_message = None
        auto_group_into_concert(session, clip)
        session.commit()
        log.info("retry identified %s -> %s - %s", clip_id, match.artist, match.title)
        return ProcessResult(
            clip_id,
            ClipStatus.IDENTIFIED,
            True,
            song_title=match.title,
            song_artist=match.artist,
            confidence=match.confidence,
            message="identified on retry",
        )
    finally:
        session.close()
