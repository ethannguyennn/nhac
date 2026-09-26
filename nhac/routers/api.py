"""JSON API under /api. Mirrors the web flow for programmatic clients / tests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from nhac.deps import get_current_user, get_session
from nhac.models import User
from nhac.pipeline.montage import MontageError, build_montage
from nhac.schemas import (
    ClipDetailOut,
    ClipOut,
    ConcertCreateIn,
    ConcertOut,
    ConcertWithClipsOut,
    MontageOut,
    PlaylistSummaryOut,
    QueueOut,
    TagClipIn,
    UploadResultOut,
)
from nhac.services import clips as clip_service
from nhac.services import concerts as concert_service
from nhac.services import playback as playback_service
from nhac.storage import get_storage
from nhac.uploads import UploadError, ingest_upload

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "nhac"}


@router.post("/clips", response_model=UploadResultOut, status_code=201)
async def upload_clip(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UploadResultOut:
    data = await file.read()
    try:
        clip, result = await ingest_upload(
            session,
            uploader_id=user.id,
            filename=file.filename or "clip.mp4",
            content_type=file.content_type,
            data=data,
        )
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResultOut(
        clip=ClipOut.model_validate(clip),
        identified=result.identified,
        message=result.message,
    )


@router.get("/clips/{clip_id}", response_model=ClipDetailOut)
def get_clip(
    clip_id: str,
    session: Session = Depends(get_session),
) -> ClipDetailOut:
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip not found")
    out = ClipDetailOut.model_validate(clip)
    if clip.raw_video_key:
        out.media_url = get_storage().url_for(clip.raw_video_key)
    return out


@router.post("/clips/{clip_id}/tag", response_model=ClipOut)
def tag_clip(
    clip_id: str,
    body: TagClipIn,
    session: Session = Depends(get_session),
) -> ClipOut:
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip not found")
    clip = clip_service.apply_manual_tag(
        session, clip, artist=body.artist, title=body.title, album=body.album
    )
    return ClipOut.model_validate(clip)


@router.get("/concerts", response_model=list[ConcertOut])
def list_concerts(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ConcertOut]:
    concerts = concert_service.list_concerts(session, user.id)
    return [ConcertOut.model_validate(c) for c in concerts]


@router.post("/concerts", response_model=ConcertOut, status_code=201)
def create_concert(
    body: ConcertCreateIn,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConcertOut:
    """Name a show before any clip exists for it (see docs/WORKFLOWS.md §1b)."""
    concert = concert_service.create_concert(
        session,
        owner_id=user.id,
        artist=body.artist,
        title=body.title,
        venue=body.venue,
        city=body.city,
        performed_on=body.performed_on,
    )
    return ConcertOut.model_validate(concert)


@router.get("/concerts/{concert_id}", response_model=ConcertWithClipsOut)
def get_concert(
    concert_id: str,
    session: Session = Depends(get_session),
) -> ConcertWithClipsOut:
    concert = concert_service.get_concert(session, concert_id)
    if concert is None:
        raise HTTPException(status_code=404, detail="concert not found")
    return ConcertWithClipsOut.model_validate(concert)


@router.post("/concerts/{concert_id}/clips", response_model=list[UploadResultOut], status_code=201)
async def upload_clips_to_concert(
    concert_id: str,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[UploadResultOut]:
    """Bulk-add clips to a concert the user already named.

    Each file goes through the same pipeline as a single upload (probe,
    thumbnail, fingerprint, excitement analysis) — the only difference is
    grouping is fixed up front instead of inferred, so a clip lands here
    whether it identifies, misses, or the fingerprint provider is
    unreachable. Processed sequentially (not concurrently): the pipeline
    already runs each file in a threadpool, and doing several ffmpeg decodes
    at once on one request would just contend for the same CPU.
    """
    results: list[UploadResultOut] = []
    for file in files:
        data = await file.read()
        try:
            clip, result = await ingest_upload(
                session,
                uploader_id=user.id,
                filename=file.filename or "clip.mp4",
                content_type=file.content_type,
                data=data,
                concert_id=concert_id,
            )
        except UploadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        results.append(
            UploadResultOut(
                clip=ClipOut.model_validate(clip),
                identified=result.identified,
                message=result.message,
            )
        )
    return results


# ---- Playback / theater mode ----


@router.get("/playlists", response_model=list[PlaylistSummaryOut])
def list_playlists(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[PlaylistSummaryOut]:
    playlists = playback_service.list_playlists(session, user.id)
    return [
        PlaylistSummaryOut(
            id=p.id,
            type=p.type,
            title=p.title,
            concert_id=p.concert_id,
            clip_count=len(p.items),
        )
        for p in playlists
    ]


@router.get("/playlists/{playlist_id}/queue", response_model=QueueOut)
def get_playlist_queue(
    playlist_id: str,
    session: Session = Depends(get_session),
) -> QueueOut:
    playlist = playback_service.get_playlist(session, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="playlist not found")
    return playback_service.build_queue(playlist)


@router.post("/clips/{clip_id}/montage", response_model=MontageOut)
async def create_montage(
    clip_id: str,
    session: Session = Depends(get_session),
) -> MontageOut:
    """Build (or return the cached) hype-cut montage for a clip.

    Runs ffmpeg in a threadpool; the montage builder manages its own DB
    session, so this route only re-reads the result.
    """
    clip = clip_service.get_clip(session, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip not found")
    try:
        result = await run_in_threadpool(build_montage, clip_id)
    except MontageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MontageOut(
        clip_id=clip_id,
        montage_url=get_storage().url_for(result.montage_key),
        built=result.built,
    )
