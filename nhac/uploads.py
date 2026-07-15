"""Upload orchestration shared by the web form and the JSON API.

    validate → store raw bytes → run the pipeline (in a threadpool) → refresh.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from nhac.constants import ALLOWED_VIDEO_EXT, MAX_UPLOAD_BYTES, STORAGE_PREFIX_RAW
from nhac.models import Clip
from nhac.pipeline.process_clip import ProcessResult, process_clip
from nhac.services.clips import create_clip, get_clip
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

    clip = create_clip(
        session,
        uploader_id=uploader_id,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(data),
    )

    storage = get_storage()
    raw_key = f"{STORAGE_PREFIX_RAW}/{clip.id}{ext}"
    storage.save_bytes(raw_key, data, content_type=content_type)
    clip.raw_video_key = raw_key
    session.commit()

    # Pipeline runs in its own session/thread; refresh ours afterwards.
    result = await run_in_threadpool(process_clip, clip.id)
    session.expire_all()
    refreshed = get_clip(session, clip.id) or clip
    return refreshed, result
