"""Concert service — reads for the library/detail views."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from nhac.enums import ClipStatus
from nhac.models import Clip, Concert


def list_concerts(session: Session, owner_id: str) -> list[Concert]:
    """Concerts owned by the user plus any demo concerts, newest first."""
    stmt = (
        select(Concert)
        .where((Concert.owner_id == owner_id) | (Concert.is_demo.is_(True)))
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
