"""Playback service — builds the play queue the theater player consumes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from nhac.models import Clip, Playlist, PlaylistItem
from nhac.schemas import HighlightOut, QueueItemOut, QueueOut
from nhac.storage import get_storage


def get_playlist(session: Session, playlist_id: str) -> Playlist | None:
    stmt = (
        select(Playlist)
        .where(Playlist.id == playlist_id)
        .options(
            selectinload(Playlist.items).selectinload(PlaylistItem.clip).selectinload(Clip.song),
            selectinload(Playlist.items)
            .selectinload(PlaylistItem.clip)
            .selectinload(Clip.highlights),
        )
    )
    return session.scalar(stmt)


def build_queue(playlist: Playlist) -> QueueOut:
    """Resolve a playlist into playable queue items (skips media-less clips)."""
    storage = get_storage()
    items: list[QueueItemOut] = []
    for item in playlist.items:  # already ordered by position
        clip = item.clip
        if clip is None or not clip.raw_video_key:
            continue
        items.append(
            QueueItemOut(
                clip_id=clip.id,
                title=clip.display_title,
                artist=clip.display_artist,
                media_url=storage.url_for(clip.raw_video_key),
                montage_url=(
                    storage.url_for(clip.montage_key) if clip.montage_key else None
                ),
                thumbnail_url=(
                    storage.url_for(clip.thumbnail_key) if clip.thumbnail_key else None
                ),
                duration_seconds=clip.duration_seconds,
                # Highlight segments power the progress-bar tick marks in the
                # theater — "jump to the good part" without building a montage.
                highlights=[
                    HighlightOut.model_validate(h)
                    for h in sorted(clip.highlights, key=lambda h: h.start_seconds)
                ],
            )
        )
    return QueueOut(playlist_id=playlist.id, title=playlist.title, items=items)


def list_playlists(session: Session, owner_id: str) -> list[Playlist]:
    stmt = (
        select(Playlist)
        .where(Playlist.owner_id == owner_id)
        .options(selectinload(Playlist.items))
        .order_by(Playlist.created_at.desc())
    )
    return list(session.scalars(stmt).unique())
