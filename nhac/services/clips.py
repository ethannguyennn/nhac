"""Clip service — create, fetch, and manual tagging."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from nhac.enums import ClipStatus, MatchSource
from nhac.models import Clip
from nhac.services.songs import upsert_song


def create_clip(
    session: Session,
    *,
    uploader_id: str,
    original_filename: str,
    content_type: str | None,
    size_bytes: int | None,
    raw_video_key: str | None = None,
) -> Clip:
    clip = Clip(
        uploader_id=uploader_id,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        raw_video_key=raw_video_key,
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
