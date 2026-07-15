"""Song service — dedupe canonical tracks by (title, artist)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhac.models import Song


def upsert_song(
    session: Session,
    *,
    title: str,
    artist: str,
    album: str | None = None,
    artwork_url: str | None = None,
    isrc: str | None = None,
    external_ids: dict | None = None,
) -> Song:
    title = title.strip()
    artist = artist.strip()
    song = session.scalar(
        select(Song).where(Song.title == title, Song.artist == artist)
    )
    if song is None:
        song = Song(
            title=title,
            artist=artist,
            album=album,
            artwork_url=artwork_url,
            isrc=isrc,
            external_ids=external_ids or {},
        )
        session.add(song)
        session.flush()
    else:
        # Backfill any newly-available metadata.
        song.album = song.album or album
        song.artwork_url = song.artwork_url or artwork_url
        song.isrc = song.isrc or isrc
        if external_ids:
            merged = dict(song.external_ids or {})
            merged.update(external_ids)
            song.external_ids = merged
    return song
