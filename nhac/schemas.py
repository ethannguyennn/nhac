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


# ---- Playback / theater mode ----


class HighlightOut(ORMModel):
    """An exciting-moment segment within a clip (seconds from clip start)."""

    start_seconds: float
    end_seconds: float
    score: float


class QueueItemOut(BaseModel):
    """One playable track in the theater queue."""

    clip_id: str
    title: str
    artist: str | None = None
    media_url: str
    montage_url: str | None = None  # hype-cut, if rendered
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    highlights: list[HighlightOut] = Field(default_factory=list)


class QueueOut(BaseModel):
    playlist_id: str
    title: str
    items: list[QueueItemOut] = Field(default_factory=list)


class PlaylistSummaryOut(ORMModel):
    id: str
    type: PlaylistType
    title: str
    concert_id: str | None = None
    clip_count: int = 0


class MontageOut(BaseModel):
    clip_id: str
    montage_url: str
    built: bool
