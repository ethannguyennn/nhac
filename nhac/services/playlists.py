"""Playlist service — auto-managed concert playlists."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhac.enums import PlaylistType
from nhac.models import Concert, Playlist, PlaylistItem


def ensure_concert_playlist(session: Session, concert: Concert) -> Playlist:
    """Get (or create) the single auto playlist for a concert."""
    playlist = session.scalar(
        select(Playlist).where(
            Playlist.concert_id == concert.id, Playlist.type == PlaylistType.CONCERT
        )
    )
    if playlist is None:
        playlist = Playlist(
            owner_id=concert.owner_id,
            concert_id=concert.id,
            type=PlaylistType.CONCERT,
            title=concert.title,
        )
        session.add(playlist)
        session.flush()
    return playlist


def add_clip_to_playlist(session: Session, playlist: Playlist, clip_id: str) -> None:
    exists = session.scalar(
        select(PlaylistItem).where(
            PlaylistItem.playlist_id == playlist.id, PlaylistItem.clip_id == clip_id
        )
    )
    if exists:
        return
    next_pos = (
        session.scalar(
            select(func.coalesce(func.max(PlaylistItem.position), -1)).where(
                PlaylistItem.playlist_id == playlist.id
            )
        )
        + 1
    )
    session.add(PlaylistItem(playlist_id=playlist.id, clip_id=clip_id, position=next_pos))
    session.flush()
