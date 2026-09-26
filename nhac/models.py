"""SQLAlchemy ORM models — the persistent domain.

``clips`` is the hub: it references a ``song`` (once identified) and a
``concert`` (once grouped). Every fingerprint attempt is logged in
``recognitions`` for debugging/audit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nhac.db import Base
from nhac.enums import ClipStatus, ConcertRole, MatchSource, PlaylistType


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)

    concerts: Mapped[list[Concert]] = relationship(back_populates="owner")
    clips: Mapped[list[Clip]] = relationship(back_populates="uploader")


class Song(Base, TimestampMixin):
    __tablename__ = "songs"
    __table_args__ = (UniqueConstraint("title", "artist", name="uq_song_title_artist"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(300), index=True)
    artist: Mapped[str] = mapped_column(String(300), index=True)
    album: Mapped[str | None] = mapped_column(String(300))
    artwork_url: Mapped[str | None] = mapped_column(Text)
    isrc: Mapped[str | None] = mapped_column(String(32))
    external_ids: Mapped[dict] = mapped_column(JSON, default=dict)

    clips: Mapped[list[Clip]] = relationship(back_populates="song")


class Concert(Base, TimestampMixin):
    __tablename__ = "concerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    artist: Mapped[str | None] = mapped_column(String(300))
    venue: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(200))
    performed_on: Mapped[date | None] = mapped_column(Date)
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped[User] = relationship(back_populates="concerts")
    clips: Mapped[list[Clip]] = relationship(back_populates="concert")
    members: Mapped[list[ConcertMember]] = relationship(
        back_populates="concert", cascade="all, delete-orphan"
    )

    @property
    def cover_thumbnail_key(self) -> str | None:
        """First clip thumbnail available, used as a stand-in cover image."""
        for clip in self.clips:
            if clip.thumbnail_key:
                return clip.thumbnail_key
        return None


class ConcertMember(Base, TimestampMixin):
    __tablename__ = "concert_members"

    concert_id: Mapped[str] = mapped_column(
        ForeignKey("concerts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ConcertRole] = mapped_column(
        Enum(ConcertRole, native_enum=False), default=ConcertRole.CONTRIBUTOR
    )

    concert: Mapped[Concert] = relationship(back_populates="members")


class Clip(Base, TimestampMixin):
    __tablename__ = "clips"
    __table_args__ = (
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="ck_clip_confidence_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    concert_id: Mapped[str | None] = mapped_column(
        ForeignKey("concerts.id", ondelete="SET NULL"), index=True
    )
    uploader_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ClipStatus] = mapped_column(
        Enum(ClipStatus, native_enum=False), default=ClipStatus.UPLOADING, index=True
    )

    # Storage keys (resolved to URLs by the storage backend)
    raw_video_key: Mapped[str | None] = mapped_column(Text)
    audio_key: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    # Rendered "hype cut" montage of the clip's most exciting moments.
    montage_key: Mapped[str | None] = mapped_column(Text)

    # Media metadata
    original_filename: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(100))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)

    # Song match
    song_id: Mapped[str | None] = mapped_column(
        ForeignKey("songs.id", ondelete="SET NULL"), index=True
    )
    match_source: Mapped[MatchSource | None] = mapped_column(
        Enum(MatchSource, native_enum=False)
    )
    match_confidence: Mapped[float | None] = mapped_column(Float)
    manual_artist: Mapped[str | None] = mapped_column(String(300))
    manual_title: Mapped[str | None] = mapped_column(String(300))

    # Phase 2 — cleanest-audio ranking
    audio_quality_score: Mapped[float | None] = mapped_column(Float)

    error_message: Mapped[str | None] = mapped_column(Text)

    uploader: Mapped[User] = relationship(back_populates="clips")
    concert: Mapped[Concert | None] = relationship(back_populates="clips")
    song: Mapped[Song | None] = relationship(back_populates="clips")
    recognitions: Mapped[list[Recognition]] = relationship(
        back_populates="clip", cascade="all, delete-orphan"
    )
    highlights: Mapped[list[ClipHighlight]] = relationship(
        back_populates="clip",
        cascade="all, delete-orphan",
        order_by="ClipHighlight.start_seconds",
    )

    @property
    def display_title(self) -> str:
        if self.song:
            return self.song.title
        if self.manual_title:
            return self.manual_title
        return self.original_filename or "Untitled clip"

    @property
    def display_artist(self) -> str | None:
        if self.song:
            return self.song.artist
        return self.manual_artist


class ClipHighlight(Base, TimestampMixin):
    """An "exciting moment" inside a clip, found by nhac.analysis.excitement.

    Scored from flashing stage lights (luma deltas) + crowd/PA loudness (RMS).
    Used to render the "hype cut" montage and to seek to the good parts.
    """

    __tablename__ = "clip_highlights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clip_id: Mapped[str] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), index=True
    )
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float, default=0.0)

    clip: Mapped[Clip] = relationship(back_populates="highlights")


class Recognition(Base, TimestampMixin):
    """One recognition ATTEMPT, successful or not.

    A row with ``error`` set is a dead letter: the provider never answered
    (timeout, 5xx, rate limit, bad key), so the clip fell back to manual
    tagging. ``services/clips.list_provider_failures`` reads these, and
    ``scripts/retry_fingerprints.py`` retries them off the stored audio
    sample. Keeping the attempt (rather than only successes) is what makes a
    provider outage recoverable instead of invisible.
    """

    __tablename__ = "recognitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    clip_id: Mapped[str] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    matched_song_id: Mapped[str | None] = mapped_column(
        ForeignKey("songs.id", ondelete="SET NULL")
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    raw_response: Mapped[dict | None] = mapped_column(JSON)
    # Set only when the provider could not be asked at all. Deliberately NOT
    # indexed: the dead-letter sweep reaches these through the already-indexed
    # ``clip_id``, and db.py's column shim can add columns to an existing dev
    # DB but not indexes — an index here would exist on fresh databases and
    # quietly not on older ones.
    error: Mapped[str | None] = mapped_column(Text)

    clip: Mapped[Clip] = relationship(back_populates="recognitions")


class Playlist(Base, TimestampMixin):
    __tablename__ = "playlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    concert_id: Mapped[str | None] = mapped_column(ForeignKey("concerts.id", ondelete="CASCADE"))
    type: Mapped[PlaylistType] = mapped_column(
        Enum(PlaylistType, native_enum=False), default=PlaylistType.CUSTOM
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[PlaylistItem]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistItem.position",
    )


class PlaylistItem(Base, TimestampMixin):
    __tablename__ = "playlist_items"
    __table_args__ = (
        UniqueConstraint("playlist_id", "clip_id", name="uq_playlist_clip"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    playlist_id: Mapped[str] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), index=True
    )
    clip_id: Mapped[str] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    playlist: Mapped[Playlist] = relationship(back_populates="items")
    clip: Mapped[Clip] = relationship()


class Favorite(Base, TimestampMixin):
    __tablename__ = "favorites"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    clip_id: Mapped[str] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True
    )
    stars: Mapped[int] = mapped_column(Integer, default=5)
