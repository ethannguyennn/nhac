"""Concert service — reads for the library/detail views."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from nhac.enums import ClipStatus
from nhac.models import Clip, Concert

# Stage-light palette a concert's accent color is deterministically drawn
# from (by hashing its id) — gives the library visual variety without
# storing a color per concert.
_GLOW_PALETTE = ("#e0a458", "#ff3d9a", "#8b5cf6", "#34e0e8", "#c96f6f")


def concert_glow(concert_id: str) -> str:
    """A stable accent color for this concert, e.g. for hero tints/stamps."""
    return _GLOW_PALETTE[zlib.crc32(concert_id.encode()) % len(_GLOW_PALETTE)]


@dataclass
class LibraryStats:
    show_count: int
    clip_count: int
    total_duration_label: str
    unidentified_count: int
    last_upload_label: str | None


def get_library_stats(session: Session, owner_id: str) -> LibraryStats:
    """Aggregate counts for the library page's stat bar / ticker."""
    show_count = (
        session.scalar(select(func.count(Concert.id)).where(Concert.owner_id == owner_id)) or 0
    )
    clip_count, total_seconds, last_upload = session.execute(
        select(
            func.count(Clip.id),
            func.coalesce(func.sum(Clip.duration_seconds), 0.0),
            func.max(Clip.created_at),
        ).where(Clip.uploader_id == owner_id)
    ).one()
    unidentified_count = (
        session.scalar(
            select(func.count(Clip.id)).where(
                Clip.uploader_id == owner_id, Clip.status == ClipStatus.UNIDENTIFIED
            )
        )
        or 0
    )
    return LibraryStats(
        show_count=show_count,
        clip_count=clip_count or 0,
        total_duration_label=_format_duration(total_seconds or 0),
        unidentified_count=unidentified_count,
        last_upload_label=_relative_time(last_upload) if last_upload else None,
    )


def _format_duration(total_seconds: float) -> str:
    minutes = int(total_seconds // 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def _relative_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    seconds = (datetime.now(UTC) - dt).total_seconds()
    if seconds < 3600:
        return "just now" if seconds < 300 else f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hr ago"
    days = int(seconds // 86400)
    return "1 day ago" if days == 1 else f"{days} days ago"


def list_concerts(session: Session, owner_id: str) -> list[Concert]:
    """Concerts owned by the user plus any demo concerts, newest first."""
    stmt = (
        select(Concert)
        .where((Concert.owner_id == owner_id) | (Concert.is_demo.is_(True)))
        .options(selectinload(Concert.clips))
        .order_by(Concert.created_at.desc())
    )
    return list(session.scalars(stmt).unique())


def get_concert(session: Session, concert_id: str) -> Concert | None:
    stmt = (
        select(Concert)
        .where(Concert.id == concert_id)
        .options(selectinload(Concert.clips).selectinload(Clip.song))
    )
    return session.scalar(stmt)


def list_unidentified_clips(session: Session, owner_id: str) -> list[Clip]:
    """Clips awaiting a manual tag (fingerprinting missed)."""
    stmt = (
        select(Clip)
        .where(Clip.uploader_id == owner_id, Clip.status == ClipStatus.UNIDENTIFIED)
        .order_by(Clip.created_at.desc())
    )
    return list(session.scalars(stmt))
