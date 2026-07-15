"""Pydantic schemas — API request/response shapes (the wire contract)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from nhac.enums import ClipStatus, MatchSource, PlaylistType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SongOut(ORMModel):
    id: str
    title: str
    artist: str
    album: str | None = None
    artwork_url: str | None = None


class ClipOut(ORMModel):
    id: str
    concert_id: str | None = None
    status: ClipStatus
    original_filename: str | None = None
    duration_seconds: float | None = None
    recorded_at: datetime | None = None
    match_source: MatchSource | None = None
    match_confidence: float | None = None
    manual_artist: str | None = None
    manual_title: str | None = None
    song: SongOut | None = None
    created_at: datetime


class ClipDetailOut(ClipOut):
    """Adds a resolved, playable media URL."""

    media_url: str | None = None


class ConcertOut(ORMModel):
    id: str
    title: str
    artist: str | None = None
    venue: str | None = None
    city: str | None = None
    performed_on: date | None = None
    cover_image_url: str | None = None
    is_demo: bool = False


class ConcertWithClipsOut(ConcertOut):
    clips: list[ClipOut] = Field(default_factory=list)


class PlaylistOut(ORMModel):
    id: str
    type: PlaylistType
    title: str
    description: str | None = None
    concert_id: str | None = None


# ---- Requests ----


class TagClipIn(BaseModel):
    artist: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    album: str | None = Field(default=None, max_length=300)


class UploadResultOut(BaseModel):
    clip: ClipOut
    identified: bool
    message: str
