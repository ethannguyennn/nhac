"""Upload orchestration shared by the web form and the JSON API.

    validate → store raw bytes → run the pipeline (in a threadpool) → refresh.

Passing ``concert_id`` is the "I already know which show this was" path
(``services.concerts.create_concert``): the clip is attached to that concert
and playlist immediately, BEFORE the pipeline runs, so it lands there
regardless of whether fingerprinting later identifies, misses, or the
provider is unreachable. Without it, grouping instead falls to
``pipeline.organize.auto_group_into_concert`` inferring artist + date from
the fingerprint match once the pipeline completes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from nhac.constants import ALLOWED_VIDEO_EXT, MAX_UPLOAD_BYTES, STORAGE_PREFIX_RAW
from nhac.models import Clip, Concert
from nhac.pipeline.process_clip import ProcessResult, process_clip
from nhac.services.clips import create_clip, get_clip
from nhac.services.playlists import add_clip_to_playlist, ensure_concert_playlist
from nhac.storage import get_storage


class UploadError(ValueError):
    """Raised for client-fixable upload problems (bad type / too big)."""


async def ingest_upload(
    session: Session,
    *,
    uploader_id: str,
    filename: str,
    content_type: str | None,
    data: bytes,
    concert_id: str | None = None,
) -> tuple[Clip, ProcessResult]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise UploadError(
            f"Unsupported file type '{ext or filename}'. Allowed: {', '.join(ALLOWED_VIDEO_EXT)}"
        )
    if len(data) == 0:
        raise UploadError("Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    concert: Concert | None = None
    if concert_id is not None:
        concert = session.get(Concert, concert_id)
        if concert is None:
            raise UploadError("Concert not found.")
        if concert.owner_id != uploader_id:
            raise UploadError("Concert not found.")  # don't reveal it exists

    clip = create_clip(
        session,
        uploader_id=uploader_id,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        concert_id=concert_id,
    )

    storage = get_storage()
    raw_key = f"{STORAGE_PREFIX_RAW}/{clip.id}{ext}"
    storage.save_bytes(raw_key, data, content_type=content_type)
    clip.raw_video_key = raw_key
    if concert is not None:
        # Attach to the playlist NOW, independent of how the pipeline below
        # turns out — a provider miss or outage still belongs at this show.
        playlist = ensure_concert_playlist(session, concert)
        add_clip_to_playlist(session, playlist, clip.id)
    session.commit()

    # Pipeline runs in its own session/thread; refresh ours afterwards.
    result = await run_in_threadpool(process_clip, clip.id)
    session.expire_all()
    refreshed = get_clip(session, clip.id) or clip
    return refreshed, result
