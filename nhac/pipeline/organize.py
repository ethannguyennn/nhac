"""Auto-organization: group a clip into a concert + its playlist.

MVP heuristic: a clip joins (or forms) a concert keyed by
(uploader, artist, recorded date). Same-artist clips recorded on the same day
land in one concert; a different day starts a new one. Phase 2 adds
venue/geo + collaborative membership.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhac.logging_config import get_logger
from nhac.models import Clip, Concert
from nhac.services.playlists import add_clip_to_playlist, ensure_concert_playlist

log = get_logger(__name__)


def auto_group_into_concert(session: Session, clip: Clip) -> str | None:
    """Attach ``clip`` to a concert (creating one if needed). Returns concert id.

    No-ops if the clip has no known artist yet (stays ungrouped until tagged).
    """
    artist = clip.display_artist
    if not artist:
        log.info("clip %s has no artist yet; leaving ungrouped", clip.id)
        return None

    performed_on: date = (clip.recorded_at.date() if clip.recorded_at else date.today())

    concert = session.scalar(
        select(Concert).where(
            Concert.owner_id == clip.uploader_id,
            Concert.artist == artist,
            Concert.performed_on == performed_on,
        )
    )
    if concert is None:
        concert = Concert(
            owner_id=clip.uploader_id,
            title=artist,
            artist=artist,
            performed_on=performed_on,
        )
        session.add(concert)
        session.flush()
        log.info("created concert %s for %s (%s)", concert.id, artist, performed_on)

    clip.concert_id = concert.id
    session.flush()

    playlist = ensure_concert_playlist(session, concert)
    add_clip_to_playlist(session, playlist, clip.id)
    return concert.id
