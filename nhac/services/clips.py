"""Clip service — create, fetch, and manual tagging."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from nhac.enums import ClipStatus, MatchSource
from nhac.models import Clip, Recognition
from nhac.services.songs import upsert_song


def create_clip(
    session: Session,
    *,
    uploader_id: str,
    original_filename: str,
    content_type: str | None,
    size_bytes: int | None,
    raw_video_key: str | None = None,
    concert_id: str | None = None,
) -> Clip:
    """``concert_id`` set means the user already named the show (see
    ``uploads.ingest_upload``) — the clip is pre-assigned rather than left for
    ``pipeline.organize.auto_group_into_concert`` to infer from the fingerprint."""
    clip = Clip(
        uploader_id=uploader_id,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        raw_video_key=raw_video_key,
        concert_id=concert_id,
        recorded_at=datetime.now(UTC),
        status=ClipStatus.UPLOADING,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return clip


def get_clip(session: Session, clip_id: str) -> Clip | None:
    stmt = (
        select(Clip)
        .where(Clip.id == clip_id)
        .options(selectinload(Clip.song), selectinload(Clip.concert))
    )
    return session.scalar(stmt)


def list_provider_failures(
    session: Session, *, transient_only: bool = False, limit: int | None = None
) -> list[Clip]:
    """Clips still untagged because the fingerprint provider never answered.

    The dead-letter queue. A provider outage otherwise hides inside the
    ``unidentified`` pile, indistinguishable from songs it genuinely didn't
    recognize — this separates the two by looking for a ``Recognition`` row
    with ``error`` set.

    Only the LATEST attempt counts. "Has ever failed" would be wrong in both
    directions: a clip the provider later answered (even with a miss) would
    never leave the queue and would be re-asked on every sweep forever, and a
    clip that answered once but hit an outage on a later retry would never
    join it. The most recent attempt is the only one describing the clip's
    situation now.

    ``transient_only`` keeps just the ones worth retrying automatically
    (timeouts, 5xx, rate limits) and skips the ones that need a human first —
    a rejected API key will reject the retry too. It reads the flag off that
    same latest attempt, so a clip whose outage has turned into a
    configuration problem drops out of the automated sweep.
    """
    latest_attempt = (
        select(func.max(Recognition.created_at))
        .where(Recognition.clip_id == Clip.id)
        .correlate(Clip)
        .scalar_subquery()
    )
    dead_letter = [
        Recognition.clip_id == Clip.id,
        Recognition.created_at == latest_attempt,
        Recognition.error.is_not(None),
    ]
    if transient_only:
        dead_letter.append(
            Recognition.raw_response["transient"].as_boolean().is_(True)
        )

    stmt = (
        select(Clip)
        .where(Clip.status == ClipStatus.UNIDENTIFIED, exists().where(*dead_letter))
        .options(selectinload(Clip.song))
        .order_by(Clip.created_at.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).unique())


def apply_manual_tag(
    session: Session, clip: Clip, *, artist: str, title: str, album: str | None = None
) -> Clip:
    """Manual fallback when fingerprinting misses."""
    song = upsert_song(session, title=title, artist=artist, album=album)
    clip.song_id = song.id
    clip.match_source = MatchSource.MANUAL
    clip.match_confidence = None
    clip.manual_artist = artist
    clip.manual_title = title
    clip.status = ClipStatus.MANUALLY_TAGGED
    session.flush()

    # Now that we know the artist, group it.
    from nhac.pipeline.organize import auto_group_into_concert

    auto_group_into_concert(session, clip)
    session.commit()
    session.refresh(clip)
    return clip
